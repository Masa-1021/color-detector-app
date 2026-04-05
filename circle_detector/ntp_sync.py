#!/usr/bin/env python3
"""
NTP 時刻同期モジュール

指定した SNTP サーバーと定期的に時刻を同期する。
オフセットが閾値を超えた場合にシステム時刻を補正する。
"""

import subprocess
import threading
import time
from datetime import datetime
from typing import Optional

try:
    import ntplib
    HAS_NTPLIB = True
except ImportError:
    HAS_NTPLIB = False


class NTPSync:
    """NTP 時刻同期クラス"""

    # オフセットがこの値（秒）を超えたらシステム時刻を補正
    OFFSET_THRESHOLD = 0.5

    def __init__(self, server: str = "ntp.nict.jp", interval_sec: int = 3600):
        self.server = server
        self.interval_sec = interval_sec
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._client = ntplib.NTPClient() if HAS_NTPLIB else None

        # ステータス
        self.last_sync: Optional[str] = None
        self.last_offset: Optional[float] = None
        self.last_error: Optional[str] = None
        self.sync_count = 0

    # ホスト側の timesyncd-watcher サービスが監視するシグナルファイル
    _SIGNAL_DIR = "/run/circle-detector"
    _SIGNAL_FILE = "/run/circle-detector/ntp-active"

    @staticmethod
    def _stop_timesyncd():
        """シグナルファイルを作成して timesyncd 停止を要求"""
        try:
            import os
            os.makedirs(NTPSync._SIGNAL_DIR, exist_ok=True)
            with open(NTPSync._SIGNAL_FILE, 'w') as f:
                f.write("1")
            print("[NTP] Signal: request timesyncd stop")
        except Exception as e:
            print(f"[NTP] Failed to signal timesyncd stop: {e}")

    @staticmethod
    def _start_timesyncd():
        """シグナルファイルを削除して timesyncd 再開を要求"""
        try:
            import os
            if os.path.exists(NTPSync._SIGNAL_FILE):
                os.remove(NTPSync._SIGNAL_FILE)
            print("[NTP] Signal: request timesyncd start")
        except Exception as e:
            print(f"[NTP] Failed to signal timesyncd start: {e}")

    def start(self):
        """バックグラウンド同期を開始"""
        if not HAS_NTPLIB:
            print("[NTP] ntplib not installed, skipping")
            return
        if self.running:
            return

        self._stop_timesyncd()
        self.running = True
        self._thread = threading.Thread(target=self._sync_loop, daemon=True)
        self._thread.start()
        print(f"[NTP] Started: server={self.server}, interval={self.interval_sec}s")

    def stop(self):
        """同期を停止"""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._start_timesyncd()
        print("[NTP] Stopped")

    def update_config(self, server: str = None, interval_sec: int = None):
        """設定を更新"""
        if server is not None:
            self.server = server
        if interval_sec is not None:
            self.interval_sec = max(60, interval_sec)  # 最低60秒

    def sync_once(self) -> dict:
        """1回だけ同期を試みる"""
        if not HAS_NTPLIB:
            return {"success": False, "error": "ntplib not installed"}

        try:
            response = self._client.request(self.server, version=3, timeout=5)
            offset = response.offset

            self.last_offset = offset
            self.last_sync = datetime.now().isoformat()
            self.last_error = None
            self.sync_count += 1

            adjusted = False
            if abs(offset) > self.OFFSET_THRESHOLD:
                adjusted = self._adjust_time(offset)

            print(f"[NTP] Sync OK: offset={offset:+.3f}s, adjusted={adjusted}")
            return {
                "success": True,
                "offset": round(offset, 3),
                "adjusted": adjusted,
                "server": self.server
            }

        except Exception as e:
            self.last_error = str(e)
            print(f"[NTP] Sync failed: {e}")
            return {"success": False, "error": str(e)}

    def _adjust_time(self, offset: float) -> bool:
        """システム時刻を補正"""
        try:
            # 現在時刻 + オフセットで補正
            import time as _time
            new_time = _time.time() + offset
            dt = datetime.fromtimestamp(new_time)
            date_str = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            result = subprocess.run(
                ["sudo", "date", "-s", date_str],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            print(f"[NTP] Time adjust failed: {e}")
            return False

    def _sync_loop(self):
        """バックグラウンド定期同期"""
        # 起動直後に1回同期
        self.sync_once()

        while self.running:
            # interval_sec 待機（1秒刻みでrunningチェック）
            waited = 0
            while self.running and waited < self.interval_sec:
                time.sleep(1)
                waited += 1

            if self.running:
                self.sync_once()

    def get_status(self) -> dict:
        """現在のステータスを返す"""
        return {
            "server": self.server,
            "interval_sec": self.interval_sec,
            "running": self.running,
            "last_sync": self.last_sync,
            "last_offset": round(self.last_offset, 3) if self.last_offset is not None else None,
            "last_error": self.last_error,
            "sync_count": self.sync_count
        }
