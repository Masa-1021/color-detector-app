#!/usr/bin/env python3
"""
MQTT送信モジュール

既存のMQTTPublisherとFileQueueを流用し、
Circle Detector用の送信インターフェースを提供する。
"""

import os
import sys
import json
import time
import threading
from datetime import datetime
from typing import Dict, Optional

# 親ディレクトリのモジュールをインポート
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from message_queue import FileQueue
    HAS_FILE_QUEUE = True
except ImportError:
    HAS_FILE_QUEUE = False

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False

from .config_manager import ConfigManager, Group, SendData


class MQTTSender:
    """MQTT送信クラス（ファイルキュー永続化対応）"""

    RETRY_INTERVAL = 5.0  # 5秒ごとにリトライ

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        mqtt_conf = config_manager.get_mqtt_config()

        self.broker = mqtt_conf.get('broker', 'localhost')
        self.port = mqtt_conf.get('port', 1883)
        self.base_topic = mqtt_conf.get('topic', 'equipment/status')
        self.enabled = mqtt_conf.get('enabled', True)

        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self._disconnect_time: Optional[float] = None  # 切断時刻（グレースピリオド用）
        self._reconnect_grace_sec = 10.0  # 自動再接続の猶予期間（秒）

        # ファイルキュー
        queue_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "queue")
        queue_file = os.path.join(queue_dir, "pending_circle.jsonl")
        if HAS_FILE_QUEUE:
            self.queue = FileQueue(queue_file, max_retries=10000)
        else:
            self.queue = None

        self.running = False
        self._retry_thread: Optional[threading.Thread] = None

        # 統計
        self.stats = {
            "sent": 0,
            "queued": 0,
            "retried": 0,
            "errors": 0
        }

        # 前回の送信値（変化時のみ送信に使用）
        self._last_values: Dict[int, int] = {}

    def start(self):
        """MQTT接続とバックグラウンドリトライを開始

        既に接続済みの場合は何もしない（接続を壊さない）。
        ブローカー/ポート変更時は先に stop() を呼ぶこと。
        """
        if not HAS_MQTT or not self.enabled:
            print("[MQTT] Disabled or paho-mqtt not installed")
            return

        # 既に接続済みならスキップ（不要な再接続を防止）
        if self.connected and self.client is not None:
            return

        # 古いクライアントがあれば確実に停止
        if self.client is not None:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
            self.client = None

        try:
            self.client = mqtt.Client(
                client_id=f"circle_detector_{os.getpid()}",
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2
            )
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.reconnect_delay_set(min_delay=1, max_delay=60)
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            print(f"[MQTT] Connection error: {e}")

        if not self.running:
            self.running = True
            self._retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
            self._retry_thread.start()

        # 起動時に未送信キューを確認
        if self.queue:
            pending = self.queue.get_count()
            if pending > 0:
                print(f"[MQTT] {pending} messages pending from previous session")

    def stop(self):
        """停止"""
        self.running = False

        if self._retry_thread:
            self._retry_thread.join(timeout=2.0)
            self._retry_thread = None

        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None
            self.connected = False
            self._disconnect_time = None

        print("[MQTT] Stopped")

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """接続時のコールバック"""
        if reason_code == 0:
            self.connected = True
            self._disconnect_time = None
            print(f"[MQTT] Connected to {self.broker}:{self.port}")
        else:
            print(f"[MQTT] Connection failed: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """切断時のコールバック"""
        self.connected = False
        self._disconnect_time = time.time()
        if reason_code != 0:
            print(f"[MQTT] Unexpected disconnect: {reason_code}, will auto-reconnect")

    @property
    def is_effectively_connected(self) -> bool:
        """
        実質的な接続状態を返す。
        自動再接続中のグレースピリオド内であれば True を返し、
        UIの断続的な「未接続」表示を防ぐ。
        """
        if self.connected:
            return True
        # 切断直後で、クライアントが存在し、runningなら猶予期間内は接続中扱い
        if (self._disconnect_time is not None
                and self.running
                and self.client is not None):
            elapsed = time.time() - self._disconnect_time
            if elapsed < self._reconnect_grace_sec:
                return True
        return False

    def send(self, group: Group, value: int, force: bool = False):
        """
        グループの値を送信

        Args:
            group: グループ情報
            value: 送信値
            force: 変化がなくても強制送信するか

        Returns:
            'sent' = 送信成功, 'skipped' = 変化なしスキップ,
            'queued' = 送信失敗→キュー保存, 'failed' = 送信失敗（キューなし）
        """
        # 変化チェック（on_changeモード）
        if not force:
            send_mode = self.config.get_detection_config().get('send_mode', 'on_change')
            if send_mode == 'on_change':
                if self._last_values.get(group.id) == value:
                    return 'skipped'  # 変化なし、送信不要

        self._last_values[group.id] = value

        data = SendData(
            mk_date=datetime.now().strftime("%Y%m%d%H%M%S"),
            sta_no1=self.config.get_sta_no1(),
            sta_no2=group.sta_no2,
            sta_no3=group.sta_no3,
            t1_status=value
        )

        return self._send_data(data)

    def _send_data(self, data: SendData) -> str:
        """データを送信（失敗時はキュー保存）

        Returns:
            'sent', 'queued', or 'failed'
        """
        payload = data.to_dict()
        topic = f"{self.base_topic}/{data.sta_no3}"

        success = self._publish(topic, payload)

        if success:
            self.stats["sent"] += 1
            return 'sent'
        else:
            # 失敗時はキューに保存
            if self.queue:
                self.queue.add({"topic": topic, **payload})
                self.stats["queued"] += 1
                return 'queued'
            else:
                self.stats["errors"] += 1
                return 'failed'

    def _publish(self, topic: str, payload: dict) -> bool:
        """MQTTブローカーに直接送信"""
        if not self.client or not self.connected:
            return False

        try:
            result = self.client.publish(topic, json.dumps(payload), qos=1)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception:
            return False

    def _retry_loop(self):
        """バックグラウンドで5秒ごとにキューを確認して再送"""
        while self.running:
            try:
                if self.queue and self.connected:
                    pending = self.queue.get_pending(limit=1)
                    if pending:
                        msg = pending[0]
                        topic = msg.data.pop('topic', self.base_topic)
                        success = self._publish(topic, msg.data)

                        if success:
                            self.queue.remove(msg.id)
                            self.stats["retried"] += 1
                        else:
                            msg.data['topic'] = topic  # topicを戻す
                            self.queue.increment_retry(msg.id)
            except Exception:
                pass

            time.sleep(self.RETRY_INTERVAL)

    def reset_last_values(self):
        """前回送信値をリセット（全グループ再送信される）"""
        self._last_values.clear()

    def get_stats(self) -> dict:
        """統計情報を取得"""
        return {
            **self.stats,
            "pending": self.queue.get_count() if self.queue else 0,
            "connected": self.is_effectively_connected,
            "enabled": self.enabled
        }
