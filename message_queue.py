#!/usr/bin/env python3
"""
メッセージキュー（ファイルベース）

通信障害時にデータをローカルに保存し、復旧後に再送する機能を提供。
子機（MQTT送信）と中継機（Oracle送信）の両方で使用可能。

使用方法:
    queue = FileQueue("queue/pending.jsonl")

    # データ追加
    queue.add({"key": "value"})

    # 送信処理（成功したら自動削除）
    def send_func(data):
        return some_api_call(data)  # True/False を返す

    queue.process(send_func)
"""

import json
import os
import threading
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class QueuedMessage:
    """キューに保存するメッセージ"""
    id: str
    data: dict
    created_at: str
    retry_count: int = 0


class FileQueue:
    """ファイルベースのメッセージキュー"""

    def __init__(self, queue_file: str, max_retries: int = 100):
        """
        Args:
            queue_file: キューファイルのパス
            max_retries: 最大リトライ回数（超えたら破棄）
        """
        self.queue_file = queue_file
        self.max_retries = max_retries
        self.lock = threading.Lock()
        self._message_counter = 0

        # ディレクトリ作成
        queue_dir = os.path.dirname(queue_file)
        if queue_dir:
            os.makedirs(queue_dir, exist_ok=True)

        # 既存のキューを読み込んでカウンター初期化
        existing = self._load_all()
        if existing:
            self._message_counter = max(int(m.id.split('_')[-1]) for m in existing) + 1

    def _generate_id(self) -> str:
        """ユニークなメッセージIDを生成"""
        self._message_counter += 1
        return f"msg_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._message_counter}"

    def add(self, data: dict) -> str:
        """メッセージをキューに追加

        Args:
            data: 保存するデータ

        Returns:
            メッセージID
        """
        with self.lock:
            msg = QueuedMessage(
                id=self._generate_id(),
                data=data,
                created_at=datetime.now().isoformat(),
                retry_count=0
            )

            with open(self.queue_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(msg), ensure_ascii=False) + '\n')

            return msg.id

    def _load_all(self) -> List[QueuedMessage]:
        """キューの全メッセージを読み込み"""
        messages = []

        if not os.path.exists(self.queue_file):
            return messages

        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            data = json.loads(line)
                            messages.append(QueuedMessage(**data))
                        except (json.JSONDecodeError, TypeError):
                            continue
        except Exception:
            pass

        return messages

    def _save_all(self, messages: List[QueuedMessage]):
        """全メッセージをファイルに書き戻す"""
        with open(self.queue_file, 'w', encoding='utf-8') as f:
            for msg in messages:
                f.write(json.dumps(asdict(msg), ensure_ascii=False) + '\n')

    def remove(self, message_id: str) -> bool:
        """メッセージをキューから削除

        Args:
            message_id: 削除するメッセージのID

        Returns:
            削除成功したかどうか
        """
        with self.lock:
            messages = self._load_all()
            original_count = len(messages)
            messages = [m for m in messages if m.id != message_id]

            if len(messages) < original_count:
                self._save_all(messages)
                return True
            return False

    def get_pending(self, limit: int = 10) -> List[QueuedMessage]:
        """保留中のメッセージを取得

        Args:
            limit: 取得する最大件数

        Returns:
            メッセージのリスト
        """
        with self.lock:
            messages = self._load_all()
            return messages[:limit]

    def get_count(self) -> int:
        """キュー内のメッセージ数を取得"""
        with self.lock:
            return len(self._load_all())

    def increment_retry(self, message_id: str) -> bool:
        """リトライ回数をインクリメント

        Args:
            message_id: メッセージID

        Returns:
            まだリトライ可能かどうか（max_retries未満）
        """
        with self.lock:
            messages = self._load_all()

            for msg in messages:
                if msg.id == message_id:
                    msg.retry_count += 1

                    if msg.retry_count >= self.max_retries:
                        # 最大リトライ回数を超えたら削除
                        messages = [m for m in messages if m.id != message_id]
                        self._save_all(messages)
                        return False

                    self._save_all(messages)
                    return True

            return False

    def process_one(self, send_func: Callable[[dict], bool]) -> Optional[bool]:
        """キューから1件処理

        Args:
            send_func: 送信関数（data を受け取り、成功時True、失敗時Falseを返す）

        Returns:
            処理結果（True=成功, False=失敗, None=キューが空）
        """
        pending = self.get_pending(limit=1)

        if not pending:
            return None

        msg = pending[0]

        try:
            success = send_func(msg.data)

            if success:
                self.remove(msg.id)
                return True
            else:
                self.increment_retry(msg.id)
                return False
        except Exception as e:
            self.increment_retry(msg.id)
            return False

    def process_all(self, send_func: Callable[[dict], bool],
                    delay_between: float = 0.1) -> Dict[str, int]:
        """キューの全メッセージを処理

        Args:
            send_func: 送信関数
            delay_between: 送信間隔（秒）

        Returns:
            処理結果の統計 {"success": n, "failed": n, "total": n}
        """
        stats = {"success": 0, "failed": 0, "total": 0}

        while True:
            result = self.process_one(send_func)

            if result is None:
                break

            stats["total"] += 1
            if result:
                stats["success"] += 1
            else:
                stats["failed"] += 1
                # 失敗したら一旦止める（連続失敗を避ける）
                break

            if delay_between > 0:
                time.sleep(delay_between)

        return stats

    def clear(self):
        """キューをクリア"""
        with self.lock:
            if os.path.exists(self.queue_file):
                os.remove(self.queue_file)


class QueuedSender:
    """キュー付き送信クラス（リアルタイム送信 + バックグラウンド再送）"""

    def __init__(self, queue: FileQueue, send_func: Callable[[dict], bool],
                 retry_interval: float = 5.0):
        """
        Args:
            queue: FileQueueインスタンス
            send_func: 送信関数
            retry_interval: 再送チェック間隔（秒）
        """
        self.queue = queue
        self.send_func = send_func
        self.retry_interval = retry_interval

        self._running = False
        self._retry_thread = None

        # 統計
        self.stats = {
            "sent": 0,
            "queued": 0,
            "retried": 0,
            "failed": 0
        }

    def start(self):
        """バックグラウンド再送スレッドを開始"""
        if self._running:
            return

        self._running = True
        self._retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
        self._retry_thread.start()

    def stop(self):
        """バックグラウンド再送スレッドを停止"""
        self._running = False
        if self._retry_thread:
            self._retry_thread.join(timeout=2.0)

    def _retry_loop(self):
        """バックグラウンドで定期的にキューを処理"""
        while self._running:
            try:
                pending_count = self.queue.get_count()

                if pending_count > 0:
                    result = self.queue.process_one(self.send_func)
                    if result:
                        self.stats["retried"] += 1
                        print(f"[Queue] 再送成功 (残り: {pending_count - 1}件)")

            except Exception as e:
                pass

            time.sleep(self.retry_interval)

    def send(self, data: dict) -> bool:
        """データを送信（失敗時はキューに保存）

        Args:
            data: 送信するデータ

        Returns:
            即座に送信成功したかどうか
        """
        try:
            # まずリアルタイム送信を試みる
            success = self.send_func(data)

            if success:
                self.stats["sent"] += 1
                return True
            else:
                # 失敗したらキューに追加
                self.queue.add(data)
                self.stats["queued"] += 1
                return False

        except Exception as e:
            # エラー時もキューに追加
            self.queue.add(data)
            self.stats["queued"] += 1
            self.stats["failed"] += 1
            return False

    def get_stats(self) -> dict:
        """統計情報を取得"""
        return {
            **self.stats,
            "pending": self.queue.get_count()
        }


# テスト用
if __name__ == "__main__":
    import tempfile

    # テスト用の一時ファイル
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        test_file = f.name

    print(f"テストファイル: {test_file}")

    # キュー作成
    queue = FileQueue(test_file)

    # メッセージ追加
    id1 = queue.add({"test": "data1"})
    id2 = queue.add({"test": "data2"})
    print(f"追加: {id1}, {id2}")
    print(f"キュー内: {queue.get_count()}件")

    # メッセージ取得
    pending = queue.get_pending()
    print(f"保留中: {[m.id for m in pending]}")

    # 送信処理（テスト用に常に成功）
    def test_send(data):
        print(f"  送信: {data}")
        return True

    stats = queue.process_all(test_send)
    print(f"処理結果: {stats}")
    print(f"キュー内: {queue.get_count()}件")

    # クリーンアップ
    os.remove(test_file)
    print("テスト完了")
