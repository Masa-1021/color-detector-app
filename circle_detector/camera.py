#!/usr/bin/env python3
"""
カメラ管理モジュール

カメラの制御、フレーム取得、MJPEGストリーミングを提供する。
"""

import cv2
import numpy as np
import threading
import time
from typing import Optional, Generator, Tuple


class CameraManager:
    """カメラ管理クラス"""

    def __init__(self, device: str = "usb", width: int = 640, height: int = 480):
        """
        初期化

        Args:
            device: カメラデバイス ("usb", "rpi", または数値/パス)
            width: 画像幅
            height: 画像高さ
        """
        self.device = device
        self.width = width
        self.height = height
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame: Optional[np.ndarray] = None
        self.lock = threading.Lock()
        self.running = False
        self._capture_thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """
        カメラを開始

        Returns:
            成功したかどうか
        """
        if self.running:
            return True

        # デバイスを開く
        if self.device == "usb":
            self.cap = cv2.VideoCapture(0)
        elif self.device == "rpi":
            self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        elif self.device.isdigit():
            self.cap = cv2.VideoCapture(int(self.device))
        else:
            self.cap = cv2.VideoCapture(self.device)

        if not self.cap.isOpened():
            print(f"Failed to open camera: {self.device}")
            return False

        # 解像度を設定
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        # バッファサイズを小さく設定（遅延対策）
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.running = True

        # バックグラウンドでフレームを取得
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        print(f"Camera started: {self.device} ({self.width}x{self.height})")
        return True

    def stop(self):
        """カメラを停止"""
        self.running = False

        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)
            self._capture_thread = None

        if self.cap:
            self.cap.release()
            self.cap = None

        print("Camera stopped")

    def _capture_loop(self):
        """バックグラウンドでフレームを取得するループ"""
        while self.running and self.cap:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.frame = frame
            else:
                time.sleep(0.01)

    def get_frame(self) -> Optional[np.ndarray]:
        """
        現在のフレームを取得

        Returns:
            BGRフレーム（コピー）、取得できない場合はNone
        """
        with self.lock:
            if self.frame is not None:
                return self.frame.copy()
        return None

    def generate_mjpeg(self, quality: int = 80) -> Generator[bytes, None, None]:
        """
        MJPEGストリームを生成

        Args:
            quality: JPEG品質 (1-100)

        Yields:
            MJPEGフレームデータ
        """
        while self.running:
            frame = self.get_frame()
            if frame is not None:
                # JPEGにエンコード
                encode_param = [cv2.IMWRITE_JPEG_QUALITY, quality]
                _, buffer = cv2.imencode('.jpg', frame, encode_param)
                frame_data = buffer.tobytes()

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            else:
                time.sleep(0.033)  # 約30fps

    def get_color_at(self, x: int, y: int, radius: int = 5) -> Tuple[int, int, int]:
        """
        指定位置の平均色（HSV）を取得

        Args:
            x: X座標
            y: Y座標
            radius: 平均化する半径

        Returns:
            (H, S, V)の平均値
        """
        with self.lock:
            if self.frame is None:
                return (0, 0, 0)

            frame = self.frame.copy()

        # 範囲チェック
        h, w = frame.shape[:2]
        y1 = max(0, y - radius)
        y2 = min(h, y + radius)
        x1 = max(0, x - radius)
        x2 = min(w, x + radius)

        if y1 >= y2 or x1 >= x2:
            return (0, 0, 0)

        # 領域を切り出し
        roi = frame[y1:y2, x1:x2]

        # BGRからHSVに変換
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # 色相は循環するため、sin/cosで平均を取る
        h_values = hsv[:, :, 0].astype(float)
        h_rad = h_values * np.pi / 90  # 0-179 → 0-2π

        h_sin = np.mean(np.sin(h_rad))
        h_cos = np.mean(np.cos(h_rad))
        h_avg = np.arctan2(h_sin, h_cos) * 90 / np.pi
        if h_avg < 0:
            h_avg += 180

        # S, Vは単純平均
        s_avg = np.mean(hsv[:, :, 1])
        v_avg = np.mean(hsv[:, :, 2])

        return (int(h_avg), int(s_avg), int(v_avg))

    def get_rgb_at(self, x: int, y: int, radius: int = 5) -> Tuple[int, int, int]:
        """
        指定位置の平均色（RGB）を取得

        Args:
            x: X座標
            y: Y座標
            radius: 平均化する半径

        Returns:
            (R, G, B)の平均値
        """
        with self.lock:
            if self.frame is None:
                return (0, 0, 0)

            frame = self.frame.copy()

        # 範囲チェック
        h, w = frame.shape[:2]
        y1 = max(0, y - radius)
        y2 = min(h, y + radius)
        x1 = max(0, x - radius)
        x2 = min(w, x + radius)

        if y1 >= y2 or x1 >= x2:
            return (0, 0, 0)

        # 領域を切り出し
        roi = frame[y1:y2, x1:x2]

        # BGR平均を計算
        b_avg = np.mean(roi[:, :, 0])
        g_avg = np.mean(roi[:, :, 1])
        r_avg = np.mean(roi[:, :, 2])

        return (int(r_avg), int(g_avg), int(b_avg))

    def suggest_color_name(self, h: int, s: int, v: int) -> str:
        """
        HSV値から色名を推定

        Args:
            h: 色相 (0-179)
            s: 彩度 (0-255)
            v: 明度 (0-255)

        Returns:
            推定された色名
        """
        # 彩度・明度が低い場合
        if v < 50:
            return "黒"
        if s < 30:
            if v > 200:
                return "白"
            return "グレー"

        # 色相で判定
        if h < 10 or h >= 170:
            return "赤"
        elif h < 25:
            return "オレンジ"
        elif h < 35:
            return "黄"
        elif h < 85:
            return "緑"
        elif h < 130:
            return "青"
        elif h < 150:
            return "紫"
        elif h < 170:
            return "ピンク"
        else:
            return "不明"

    @property
    def is_running(self) -> bool:
        """カメラが動作中かどうか"""
        return self.running

    @property
    def frame_size(self) -> Tuple[int, int]:
        """フレームサイズ (width, height)"""
        return (self.width, self.height)


# =============================================================================
# テスト
# =============================================================================

if __name__ == "__main__":
    print("カメラテスト開始...")

    camera = CameraManager(device="usb", width=640, height=480)

    if not camera.start():
        print("カメラの起動に失敗しました")
        exit(1)

    print("カメラ起動成功")

    # 数フレーム取得してテスト
    time.sleep(1)

    for i in range(5):
        frame = camera.get_frame()
        if frame is not None:
            print(f"フレーム {i+1}: {frame.shape}")

            # 中央の色を取得
            h, w = frame.shape[:2]
            hsv = camera.get_color_at(w // 2, h // 2, radius=10)
            rgb = camera.get_rgb_at(w // 2, h // 2, radius=10)
            color_name = camera.suggest_color_name(*hsv)
            print(f"  中央の色: HSV={hsv}, RGB={rgb}, 推定={color_name}")
        else:
            print(f"フレーム {i+1}: 取得失敗")

        time.sleep(0.5)

    camera.stop()
    print("テスト完了")
