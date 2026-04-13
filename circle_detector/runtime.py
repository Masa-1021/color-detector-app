#!/usr/bin/env python3
"""
Circle Detector - 検出ランタイム（CLI / ヘッドレス）

Flask・UIなしで検出ループのみを実行する常駐プロセス。
設定は config/*.json から読み込み、SIGHUP で再読み込みする。
停止は SIGTERM / SIGINT。
"""

import os
import signal
import sys
import time
import threading
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .config_manager import ConfigManager
from .camera import CameraManager
from .detector import DetectionEngine
from .rule_engine import RuleEngine
from .mqtt_sender import MQTTSender
from .ntp_sync import NTPSync


class Runtime:
    def __init__(self, config_path: str = None):
        self.config_mgr = ConfigManager(config_path)
        self.config_mgr.load()

        cam_conf = self.config_mgr.get_camera_config()
        self.camera = CameraManager(
            device=cam_conf.get('device', 'usb'),
            width=cam_conf.get('width', 640),
            height=cam_conf.get('height', 480)
        )
        self.detector = DetectionEngine(self.config_mgr, self.config_mgr.get_blink_config())
        self.rule_engine = RuleEngine(self.config_mgr)
        self.mqtt_sender = MQTTSender(self.config_mgr)

        ntp_conf = self.config_mgr.get_ntp_config()
        self.ntp_sync = NTPSync(
            server=ntp_conf.get('server', 'ntp.nict.jp'),
            interval_sec=ntp_conf.get('interval_sec', 3600)
        )

        self.running = False
        self._reload_requested = False

    def _reload_config(self):
        print("[Runtime] SIGHUP: 設定を再読み込みします")
        self.config_mgr.load()
        self.detector = DetectionEngine(self.config_mgr, self.config_mgr.get_blink_config())
        self.rule_engine = RuleEngine(self.config_mgr)

    def start(self):
        print("=" * 50)
        print("Circle Detector Runtime")
        print("=" * 50)

        if not self.camera.start():
            print("[Runtime] カメラ起動失敗")
            sys.exit(1)
        print(f"[Runtime] カメラ起動: {self.camera.frame_size}")

        self.mqtt_sender.start()
        for _ in range(15):
            time.sleep(0.2)
            if self.mqtt_sender.connected:
                break
        print(f"[Runtime] MQTT: {'接続' if self.mqtt_sender.connected else '未接続（キュー経由）'}")

        self.ntp_sync.start()
        print("[Runtime] NTP同期スレッド開始")

        self.detector.reset()
        self.mqtt_sender.reset_last_values()

        self.running = True
        self._loop()

    def _loop(self):
        last_periodic_send = 0.0

        while self.running:
            if self._reload_requested:
                self._reload_requested = False
                self._reload_config()

            frame = self.camera.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            results = self.detector.detect_all(frame)
            group_values = self.rule_engine.evaluate_all_groups(results)

            detection_conf = self.config_mgr.get_detection_config()
            send_mode = detection_conf.get('send_mode', 'on_change')
            send_interval = detection_conf.get('send_interval_sec', 1)

            now = time.time()
            should_send = False
            if send_mode == 'periodic':
                if now - last_periodic_send >= send_interval:
                    should_send = True
                    last_periodic_send = now
            else:
                should_send = True

            if should_send:
                for group in self.config_mgr.groups:
                    value = group_values.get(group.id, group.default_value)
                    force = (send_mode == 'periodic')
                    self.mqtt_sender.send(group, value, force=force)

            time.sleep(0.1)

    def stop(self):
        print("\n[Runtime] 停止中...")
        self.running = False
        self.ntp_sync.stop()
        self.mqtt_sender.stop()
        self.camera.stop()
        print("[Runtime] 停止完了")


def main():
    runtime = Runtime()

    def sig_term(signum, frame):
        runtime.running = False

    def sig_hup(signum, frame):
        runtime._reload_requested = True

    signal.signal(signal.SIGTERM, sig_term)
    signal.signal(signal.SIGINT, sig_term)
    signal.signal(signal.SIGHUP, sig_hup)

    try:
        runtime.start()
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
