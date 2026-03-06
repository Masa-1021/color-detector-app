#!/usr/bin/env python3
"""
設備稼働状況モジュール
色検知から設備の稼働状況を判定し、MQTT/Oracleに送信する

稼働状況コード:
  1: 運転準備（緑点滅）
  2: 自動運転（緑点灯）
  3: 通過運転（黄点灯）
  14: 異常中（赤点灯）
  16: 段換中（黄点滅）
"""

import json
import time
import os
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from collections import deque
from enum import IntEnum

# MQTT（オプション）
try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False

# ファイルベースキュー
try:
    from message_queue import FileQueue
    HAS_FILE_QUEUE = True
except ImportError:
    HAS_FILE_QUEUE = False


# =============================================================================
# 定数・列挙型
# =============================================================================

class EquipmentStatusCode(IntEnum):
    """設備稼働状況コード"""
    UNKNOWN = 0         # 不明
    READY = 1           # 運転準備（緑点滅）
    AUTO_RUN = 2        # 自動運転（緑点灯）
    PASS_THROUGH = 3    # 通過運転（黄点灯）
    ERROR = 14          # 異常中（赤点灯）
    CHANGEOVER = 16     # 段換中（黄点滅）


# 状態名の日本語マッピング
STATUS_NAMES_JP = {
    EquipmentStatusCode.UNKNOWN: "不明",
    EquipmentStatusCode.READY: "運転準備",
    EquipmentStatusCode.AUTO_RUN: "自動運転",
    EquipmentStatusCode.PASS_THROUGH: "通過運転",
    EquipmentStatusCode.ERROR: "異常中",
    EquipmentStatusCode.CHANGEOVER: "段換中",
}

# 状態の表示色（BGR）
STATUS_COLORS_BGR = {
    EquipmentStatusCode.UNKNOWN: (128, 128, 128),    # グレー
    EquipmentStatusCode.READY: (0, 255, 0),          # 緑
    EquipmentStatusCode.AUTO_RUN: (0, 200, 0),       # 濃い緑
    EquipmentStatusCode.PASS_THROUGH: (0, 255, 255), # 黄
    EquipmentStatusCode.ERROR: (0, 0, 255),          # 赤
    EquipmentStatusCode.CHANGEOVER: (0, 200, 200),   # 濃い黄
}


# =============================================================================
# データクラス
# =============================================================================

@dataclass
class BlinkConfig:
    """点滅検出設定"""
    window_ms: int = 2000       # 監視ウィンドウ（ミリ秒）
    min_changes: int = 3        # 点滅と判定する最小変化回数
    min_interval_ms: int = 100  # 最小点滅間隔（ミリ秒）
    max_interval_ms: int = 1500 # 最大点滅間隔（ミリ秒）


@dataclass
class StationConfig:
    """ステーション設定"""
    sta_no1: str = ""  # 工場コード
    sta_no2: str = ""  # ラインコード
    sta_no1_options: list = field(default_factory=list)  # STA_NO1選択肢


@dataclass
class RegionConfig:
    """領域設定（拡張版）"""
    id: int
    name: str
    x: int
    y: int
    width: int
    height: int
    threshold: int = 30
    sta_no3: str = ""      # 設備コード
    enabled: bool = True


@dataclass
class MQTTConfig:
    """MQTT設定"""
    broker: str = "localhost"
    port: int = 1883
    topic: str = "equipment/status"
    client_id: str = "color_detector"
    username: str = ""
    password: str = ""
    enabled: bool = False


@dataclass
class OracleConfig:
    """Oracle Database設定"""
    enabled: bool = False
    dsn: str = "eqstatusdb_low"              # TNS名 (tnsnames.oraに定義)
    user: str = "ADMIN"
    password: str = ""
    wallet_dir: str = "/home/pi/oracle_wallet"
    wallet_password: str = ""
    use_wallet: bool = True
    table_name: str = "HF1RCM01"
    # 接続プール設定
    pool_min: int = 1
    pool_max: int = 5
    pool_increment: int = 1


@dataclass
class EquipmentConfig:
    """全体設定"""
    version: str = "2.0"
    station: StationConfig = field(default_factory=StationConfig)
    mqtt: MQTTConfig = field(default_factory=MQTTConfig)
    oracle: OracleConfig = field(default_factory=OracleConfig)
    blink: BlinkConfig = field(default_factory=BlinkConfig)
    regions: List[RegionConfig] = field(default_factory=list)


@dataclass
class StatusMessage:
    """MQTT/DB送信メッセージ"""
    mk_date: str           # YYYYMMDDhhmmss
    sta_no1: str
    sta_no2: str
    sta_no3: str
    t1_status: int
    color_name: str = ""
    is_blinking: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# =============================================================================
# BlinkDetector クラス
# =============================================================================

class BlinkDetector:
    """点滅検出器"""

    def __init__(self, config: BlinkConfig = None):
        self.config = config or BlinkConfig()
        # 領域ごとの色履歴: {region_id: deque([(timestamp_ms, color_name), ...])}
        self.history: Dict[int, deque] = {}
        # 領域ごとの現在の状態
        self.current_state: Dict[int, Tuple[str, bool]] = {}  # (color_name, is_blinking)

    def add_sample(self, region_id: int, color_name: str, timestamp_ms: int = None):
        """色サンプルを追加"""
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)

        if region_id not in self.history:
            self.history[region_id] = deque(maxlen=200)

        self.history[region_id].append((timestamp_ms, color_name))

        # 古いサンプルを削除
        self._cleanup_old_samples(region_id, timestamp_ms)

    def _cleanup_old_samples(self, region_id: int, current_time_ms: int):
        """古いサンプルを削除"""
        cutoff = current_time_ms - self.config.window_ms * 2
        history = self.history[region_id]
        while history and history[0][0] < cutoff:
            history.popleft()

    def get_state(self, region_id: int) -> Tuple[str, bool]:
        """
        領域の現在の状態を取得

        Returns:
            (dominant_color, is_blinking): 支配的な色と点滅フラグ
        """
        if region_id not in self.history or not self.history[region_id]:
            return ("unknown", False)

        history = self.history[region_id]
        now = history[-1][0]
        window_start = now - self.config.window_ms

        # ウィンドウ内のサンプルを取得
        samples = [(t, c) for t, c in history if t >= window_start]

        if len(samples) < 2:
            return (samples[-1][1] if samples else "unknown", False)

        # 色の出現回数をカウント
        color_counts: Dict[str, int] = {}
        for _, color in samples:
            color_counts[color] = color_counts.get(color, 0) + 1

        # 支配的な色を特定（黒/不明以外で最も多い色）
        dominant_color = "unknown"
        max_count = 0
        for color, count in color_counts.items():
            if color not in ("black", "unknown", "gray") and count > max_count:
                dominant_color = color
                max_count = count

        # 点滅判定: 色の変化回数をカウント
        changes = 0
        prev_color = None
        change_intervals = []
        prev_time = None

        for t, c in samples:
            if prev_color is not None and c != prev_color:
                changes += 1
                if prev_time is not None:
                    change_intervals.append(t - prev_time)
                prev_time = t
            prev_color = c

        # 点滅判定
        is_blinking = False
        if changes >= self.config.min_changes:
            # 変化間隔が適切な範囲内かチェック
            if change_intervals:
                avg_interval = sum(change_intervals) / len(change_intervals)
                if self.config.min_interval_ms <= avg_interval <= self.config.max_interval_ms:
                    is_blinking = True

        self.current_state[region_id] = (dominant_color, is_blinking)
        return (dominant_color, is_blinking)

    def reset(self, region_id: int = None):
        """履歴をリセット"""
        if region_id is None:
            self.history.clear()
            self.current_state.clear()
        else:
            self.history.pop(region_id, None)
            self.current_state.pop(region_id, None)


# =============================================================================
# EquipmentStatusManager クラス
# =============================================================================

class EquipmentStatusManager:
    """設備稼働状況管理"""

    def __init__(self, config: EquipmentConfig = None):
        self.config = config or EquipmentConfig()
        self.blink_detector = BlinkDetector(self.config.blink)

        # 領域ごとの現在の状態
        self.current_status: Dict[int, EquipmentStatusCode] = {}
        # 領域ごとの前回の状態（変化検出用）
        self.prev_status: Dict[int, EquipmentStatusCode] = {}
        # 状態変化時のコールバック
        self.on_status_change = None

    def update(self, region_id: int, color_name: str, timestamp_ms: int = None) -> Optional[EquipmentStatusCode]:
        """
        色情報を更新し、稼働状況を判定

        Returns:
            状態が変化した場合は新しい状態、変化なしならNone
        """
        # 点滅検出器に色を追加
        self.blink_detector.add_sample(region_id, color_name, timestamp_ms)

        # 現在の状態を取得
        dominant_color, is_blinking = self.blink_detector.get_state(region_id)

        # 稼働状況コードに変換
        new_status = self._determine_status(dominant_color, is_blinking)
        self.current_status[region_id] = new_status

        # 状態変化を検出
        prev = self.prev_status.get(region_id)
        if prev != new_status:
            self.prev_status[region_id] = new_status
            if self.on_status_change and prev is not None:
                self.on_status_change(region_id, prev, new_status)
            return new_status

        return None

    def _determine_status(self, color_name: str, is_blinking: bool) -> EquipmentStatusCode:
        """色と点滅状態から稼働状況を判定"""

        # 赤 → 異常（点滅関係なし）
        if color_name == "red":
            return EquipmentStatusCode.ERROR

        # 黄/オレンジ
        if color_name in ("yellow", "orange"):
            if is_blinking:
                return EquipmentStatusCode.CHANGEOVER  # 段換中
            else:
                return EquipmentStatusCode.PASS_THROUGH  # 通過運転

        # 緑
        if color_name == "green":
            if is_blinking:
                return EquipmentStatusCode.READY  # 運転準備
            else:
                return EquipmentStatusCode.AUTO_RUN  # 自動運転

        return EquipmentStatusCode.UNKNOWN

    def get_status(self, region_id: int) -> EquipmentStatusCode:
        """現在の稼働状況を取得"""
        return self.current_status.get(region_id, EquipmentStatusCode.UNKNOWN)

    def get_status_name(self, region_id: int) -> str:
        """現在の稼働状況名（日本語）を取得"""
        status = self.get_status(region_id)
        return STATUS_NAMES_JP.get(status, "不明")

    def get_status_color(self, region_id: int) -> Tuple[int, int, int]:
        """現在の稼働状況の表示色（BGR）を取得"""
        status = self.get_status(region_id)
        return STATUS_COLORS_BGR.get(status, (128, 128, 128))

    def create_message(self, region_id: int, region_config: RegionConfig) -> StatusMessage:
        """送信用メッセージを作成"""
        status = self.get_status(region_id)
        color, is_blinking = self.blink_detector.get_state(region_id)

        return StatusMessage(
            mk_date=datetime.now().strftime("%Y%m%d%H%M%S"),
            sta_no1=self.config.station.sta_no1,
            sta_no2=self.config.station.sta_no2,
            sta_no3=region_config.sta_no3,
            t1_status=int(status),
            color_name=color,
            is_blinking=is_blinking
        )


# =============================================================================
# MQTTPublisher クラス（ネットワーク障害対応版・ファイルキュー永続化）
# =============================================================================

class MQTTPublisher:
    """MQTT送信（自動再接続・オフラインキュー対応・ファイル永続化）"""

    # オフラインキューの最大サイズ
    MAX_QUEUE_SIZE = 10000

    def __init__(self, config: MQTTConfig, queue_dir: str = None):
        self.config = config
        self.client = None
        self.connected = False

        # ファイルベースキュー（永続化）
        if queue_dir is None:
            queue_dir = os.path.join(os.path.dirname(__file__), "queue")
        queue_file = os.path.join(queue_dir, "pending_mqtt.jsonl")

        if HAS_FILE_QUEUE:
            self.file_queue = FileQueue(queue_file, max_retries=self.MAX_QUEUE_SIZE)
            self._use_file_queue = True
        else:
            self.file_queue = None
            self._use_file_queue = False
            print("Warning: FileQueue not available. Using memory-only queue.")

        # メモリキュー（FileQueue未使用時のフォールバック）
        self.memory_queue: deque = deque(maxlen=self.MAX_QUEUE_SIZE)
        self.queue_overflow_count = 0

        # 再接続設定
        self.reconnect_delay = 5  # 再接続間隔（秒）
        self.last_reconnect_attempt = 0
        self.reconnect_count = 0

        # バックグラウンド再送スレッド
        self._retry_thread = None
        self._retry_running = False
        self._retry_interval = 5.0  # 再送チェック間隔（秒）

        # 統計
        self.stats = {
            "sent": 0,
            "queued": 0,
            "queue_sent": 0,
            "failed": 0,
            "reconnects": 0
        }

        if not HAS_MQTT:
            print("Warning: paho-mqtt not installed. MQTT disabled.")
            return

        if not config.enabled:
            return

        self._setup_client()

    def _setup_client(self):
        """MQTTクライアントをセットアップ"""
        self.client = mqtt.Client(
            client_id=self.config.client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )

        if self.config.username:
            self.client.username_pw_set(self.config.username, self.config.password)

        # 自動再接続を有効化
        self.client.reconnect_delay_set(min_delay=1, max_delay=60)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """接続時のコールバック"""
        if reason_code == 0:
            was_disconnected = not self.connected
            self.connected = True

            if was_disconnected and self.reconnect_count > 0:
                print(f"MQTT reconnected to {self.config.broker}:{self.config.port}")
                self.stats["reconnects"] += 1
                # キューに溜まったメッセージを送信（バックグラウンドで処理）
                pending = self._get_queue_size()
                if pending > 0:
                    print(f"  Pending messages in queue: {pending}")
            else:
                print(f"MQTT connected to {self.config.broker}:{self.config.port}")
                # 起動時にキューにデータがあれば表示
                pending = self._get_queue_size()
                if pending > 0:
                    print(f"  Resuming {pending} pending messages from queue")

            self.reconnect_count += 1
        else:
            print(f"MQTT connection failed: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """切断時のコールバック"""
        self.connected = False
        if reason_code != 0:
            print(f"MQTT disconnected unexpectedly: {reason_code}")
            print(f"  Offline queue enabled. Messages will be stored locally.")
        else:
            print("MQTT disconnected gracefully")

    def _get_queue_size(self) -> int:
        """キューのサイズを取得"""
        if self._use_file_queue and self.file_queue:
            return self.file_queue.get_count()
        return len(self.memory_queue)

    def _add_to_queue(self, topic: str, payload: str):
        """キューにメッセージを追加"""
        if self._use_file_queue and self.file_queue:
            self.file_queue.add({"topic": topic, "payload": payload})
        else:
            if len(self.memory_queue) >= self.MAX_QUEUE_SIZE:
                self.queue_overflow_count += 1
            self.memory_queue.append((topic, payload))
        self.stats["queued"] += 1

    def _process_one_from_queue(self) -> bool:
        """キューから1件送信を試みる。成功時True、キュー空または失敗時False"""
        if not self.connected or not self.client:
            return False

        if self._use_file_queue and self.file_queue:
            pending = self.file_queue.get_pending(limit=1)
            if not pending:
                return False

            msg = pending[0]
            topic = msg.data.get("topic", "")
            payload = msg.data.get("payload", "")

            try:
                result = self.client.publish(topic, payload, qos=1)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    self.file_queue.remove(msg.id)
                    self.stats["queue_sent"] += 1
                    return True
                else:
                    return False
            except Exception:
                return False
        else:
            # メモリキュー
            if not self.memory_queue:
                return False

            topic, payload = self.memory_queue.popleft()
            try:
                result = self.client.publish(topic, payload, qos=1)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    self.stats["queue_sent"] += 1
                    return True
                else:
                    self.memory_queue.appendleft((topic, payload))
                    return False
            except Exception:
                self.memory_queue.appendleft((topic, payload))
                return False

    def _retry_loop(self):
        """バックグラウンドでキューを定期的に処理"""
        while self._retry_running:
            try:
                if self.connected and self._get_queue_size() > 0:
                    success = self._process_one_from_queue()
                    if success:
                        remaining = self._get_queue_size()
                        print(f"[Queue] Retry sent successfully (remaining: {remaining})")
            except Exception:
                pass
            time.sleep(self._retry_interval)

    def _start_retry_thread(self):
        """再送スレッドを開始"""
        if self._retry_thread is not None:
            return
        self._retry_running = True
        import threading
        self._retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
        self._retry_thread.start()

    def _stop_retry_thread(self):
        """再送スレッドを停止"""
        self._retry_running = False
        if self._retry_thread:
            self._retry_thread.join(timeout=2.0)
            self._retry_thread = None

    def connect(self) -> bool:
        """MQTTブローカーに接続"""
        if not self.client or not self.config.enabled:
            return False

        try:
            self.client.connect(self.config.broker, self.config.port, keepalive=60)
            self.client.loop_start()

            # バックグラウンド再送スレッドを開始
            self._start_retry_thread()

            # 接続完了を待つ
            for _ in range(10):
                if self.connected:
                    return True
                time.sleep(0.1)
            return self.connected
        except Exception as e:
            print(f"MQTT connection error: {e}")
            return False

    def publish(self, message: StatusMessage, subtopic: str = "") -> bool:
        """
        メッセージを送信（オフライン時はキューに蓄積・ファイル永続化）

        Returns:
            True: 送信成功またはキューに追加成功
            False: 送信失敗かつキュー追加も失敗
        """
        topic = self.config.topic
        if subtopic:
            topic = f"{topic}/{subtopic}"

        payload = message.to_json()

        # オンライン時は直接送信を試みる（リアルタイム）
        if self.client and self.connected:
            try:
                result = self.client.publish(topic, payload, qos=1)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    self.stats["sent"] += 1
                    return True
            except Exception as e:
                print(f"MQTT publish error: {e}")

        # オフライン時またはエラー時はキューに追加（ファイル永続化）
        self._add_to_queue(topic, payload)
        return True  # キューに追加成功

    def try_reconnect(self):
        """再接続を試みる（定期的に呼び出す）"""
        if self.connected or not self.client:
            return

        now = time.time()
        if now - self.last_reconnect_attempt < self.reconnect_delay:
            return

        self.last_reconnect_attempt = now
        try:
            self.client.reconnect()
        except Exception as e:
            pass  # 再接続失敗は無視（loop_startが自動で再試行）

    def get_queue_size(self) -> int:
        """オフラインキューのサイズを取得"""
        return self._get_queue_size()

    def get_stats(self) -> Dict:
        """統計情報を取得"""
        return {
            **self.stats,
            "queue_size": self._get_queue_size(),
            "queue_overflow": self.queue_overflow_count,
            "connected": self.connected,
            "file_queue_enabled": self._use_file_queue
        }

    def disconnect(self):
        """切断"""
        # 再送スレッドを停止
        self._stop_retry_thread()

        if self.client:
            # 残っているメッセージを可能な限り送信
            if self.connected:
                sent = 0
                while self._get_queue_size() > 0 and sent < 100:
                    if not self._process_one_from_queue():
                        break
                    sent += 1
                if sent > 0:
                    print(f"MQTT: Flushed {sent} messages before disconnect")

            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False

        # 統計を表示
        stats = self.get_stats()
        print(f"MQTT stats: sent={stats['sent']}, queued={stats['queued']}, "
              f"queue_sent={stats['queue_sent']}, failed={stats['failed']}, "
              f"reconnects={stats['reconnects']}, pending={stats['queue_size']}")

        if stats['queue_size'] > 0:
            print(f"  Note: {stats['queue_size']} messages saved in queue (will be sent on next startup)")


# =============================================================================
# LocalLogger クラス
# =============================================================================

class LocalStatusLogger:
    """ローカルファイルへのログ保存"""

    def __init__(self, log_dir: str = "./equipment_logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self._current_date = None
        self._file_handle = None

    def _get_log_file(self) -> str:
        """今日のログファイルパスを取得"""
        today = datetime.now().strftime("%Y%m%d")
        return os.path.join(self.log_dir, f"status_{today}.jsonl")

    def log(self, message: StatusMessage):
        """メッセージをログに記録"""
        today = datetime.now().strftime("%Y%m%d")

        # 日付が変わったらファイルを切り替え
        if self._current_date != today:
            if self._file_handle:
                self._file_handle.close()
            self._current_date = today
            self._file_handle = open(self._get_log_file(), 'a', encoding='utf-8')

        self._file_handle.write(message.to_json() + '\n')
        self._file_handle.flush()

    def close(self):
        """ファイルを閉じる"""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None


# =============================================================================
# 設定ファイル読み書き
# =============================================================================

def load_equipment_config(filepath: str) -> EquipmentConfig:
    """設定ファイルを読み込み"""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    config = EquipmentConfig(
        version=data.get("version", "2.0"),
        station=StationConfig(**data.get("station", {})),
        mqtt=MQTTConfig(**data.get("mqtt", {})),
        oracle=OracleConfig(**data.get("oracle", {})),
        blink=BlinkConfig(**data.get("blink_detection", {})),
        regions=[RegionConfig(**r) for r in data.get("regions", [])]
    )
    return config


def save_equipment_config(config: EquipmentConfig, filepath: str):
    """設定ファイルを保存"""
    data = {
        "version": config.version,
        "created": datetime.now().isoformat(),
        "station": asdict(config.station),
        "mqtt": asdict(config.mqtt),
        "oracle": asdict(config.oracle),
        "blink_detection": asdict(config.blink),
        "regions": [asdict(r) for r in config.regions]
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =============================================================================
# テスト
# =============================================================================

if __name__ == "__main__":
    # テスト: 点滅検出
    print("=== 点滅検出テスト ===\n")

    detector = BlinkDetector(BlinkConfig(window_ms=2000, min_changes=3))

    # 緑点灯をシミュレート
    print("1. 緑点灯（安定）:")
    for i in range(20):
        detector.add_sample(1, "green", i * 100)
    color, blink = detector.get_state(1)
    print(f"   色: {color}, 点滅: {blink}")

    # 緑点滅をシミュレート
    print("\n2. 緑点滅:")
    detector.reset(2)
    for i in range(20):
        color = "green" if i % 2 == 0 else "black"
        detector.add_sample(2, color, i * 300)  # 300ms間隔で点滅
    color, blink = detector.get_state(2)
    print(f"   色: {color}, 点滅: {blink}")

    # 稼働状況判定
    print("\n=== 稼働状況判定テスト ===\n")

    config = EquipmentConfig(
        station=StationConfig(sta_no1="PLANT01", sta_no2="LINE01")
    )
    manager = EquipmentStatusManager(config)

    # 緑点灯
    for i in range(20):
        manager.update(1, "green", i * 100)
    print(f"緑点灯: {manager.get_status_name(1)} ({manager.get_status(1)})")

    # 緑点滅
    for i in range(20):
        color = "green" if i % 2 == 0 else "black"
        manager.update(2, color, i * 300)
    print(f"緑点滅: {manager.get_status_name(2)} ({manager.get_status(2)})")

    # 黄点灯
    manager.blink_detector.reset(3)
    for i in range(20):
        manager.update(3, "yellow", i * 100)
    print(f"黄点灯: {manager.get_status_name(3)} ({manager.get_status(3)})")

    # 黄点滅
    manager.blink_detector.reset(4)
    for i in range(20):
        color = "yellow" if i % 2 == 0 else "black"
        manager.update(4, color, i * 300)
    print(f"黄点滅: {manager.get_status_name(4)} ({manager.get_status(4)})")

    # 赤点灯
    manager.blink_detector.reset(5)
    for i in range(20):
        manager.update(5, "red", i * 100)
    print(f"赤点灯: {manager.get_status_name(5)} ({manager.get_status(5)})")

    print("\n✅ テスト完了")
