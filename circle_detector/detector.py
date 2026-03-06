#!/usr/bin/env python3
"""
色検出エンジン

円領域の色を検出し、点滅判定を行う。
"""

import time
import cv2
import numpy as np
from collections import deque
from typing import Dict, List, Optional, Tuple

from .config_manager import Circle, ColorRange, DetectionResult, ConfigManager


class BlinkDetector:
    """点滅検出クラス"""

    def __init__(self, config: dict):
        self.window_ms = config.get('window_ms', 2000)
        self.min_changes = config.get('min_changes', 3)
        self.min_interval_ms = config.get('min_interval_ms', 100)
        self.max_interval_ms = config.get('max_interval_ms', 1500)

        # 履歴: {circle_id: deque of (timestamp_ms, color)}
        self.history: Dict[int, deque] = {}

    def update(self, circle_id: int, color: Optional[str]) -> Tuple[bool, Optional[float]]:
        """
        色を記録し、点滅かどうかを判定

        Args:
            circle_id: 円ID
            color: 検出された色（Noneも可）

        Returns:
            (点滅中かどうか, 平均間隔ms or None)
        """
        now = time.time() * 1000  # ミリ秒

        if circle_id not in self.history:
            self.history[circle_id] = deque(maxlen=100)

        history = self.history[circle_id]

        # 前回と色が変わった場合のみ記録
        if not history or history[-1][1] != color:
            history.append((now, color))

        # 古い履歴を削除
        cutoff = now - self.window_ms
        while history and history[0][0] < cutoff:
            history.popleft()

        return self._is_blinking(history)

    def _is_blinking(self, history: deque) -> Tuple[bool, Optional[float]]:
        """
        履歴から点滅を判定

        条件:
        1. window_ms内にmin_changes回以上の色変化
        2. 各変化の間隔がmin_interval_ms～max_interval_msの範囲

        Returns:
            (点滅中かどうか, 有効間隔の平均ms or None)
        """
        if len(history) < self.min_changes + 1:
            return False, None

        # 変化間隔を計算
        intervals = []
        for i in range(1, len(history)):
            interval = history[i][0] - history[i - 1][0]
            intervals.append(interval)

        # 条件チェック
        valid_intervals = [
            i for i in intervals
            if self.min_interval_ms <= i <= self.max_interval_ms
        ]

        is_blinking = len(valid_intervals) >= self.min_changes
        avg_interval = sum(valid_intervals) / len(valid_intervals) if valid_intervals else None

        return is_blinking, avg_interval

    def reset(self, circle_id: int = None):
        """履歴をリセット"""
        if circle_id is not None:
            self.history.pop(circle_id, None)
        else:
            self.history.clear()


class DetectionEngine:
    """色検出エンジン"""

    def __init__(self, config_manager: ConfigManager, blink_config: dict = None):
        self.config = config_manager
        self.blink_detector = BlinkDetector(blink_config or {})

    def detect_all(self, frame: np.ndarray) -> List[DetectionResult]:
        """
        全円の色を検出

        Args:
            frame: 入力フレーム (BGR)

        Returns:
            全円の検出結果リスト
        """
        results = []
        for circle in self.config.circles:
            result = self.detect_circle(frame, circle)
            results.append(result)
        return results

    def detect_circle(self, frame: np.ndarray, circle: Circle) -> DetectionResult:
        """
        1つの円の色を検出

        Args:
            frame: 入力フレーム (BGR)
            circle: 円情報

        Returns:
            検出結果
        """
        # 円領域取得
        roi, mask = self._get_circle_region(frame, circle)

        if roi is None or mask is None:
            return DetectionResult(
                circle_id=circle.id,
                detected_color=None,
                is_blinking=False,
                raw_hsv=(0, 0, 0)
            )

        # 平均HSV計算
        hsv = self._calculate_average_hsv(roi, mask)

        # 色マッチング
        color_name = self._match_color(hsv, circle.colors)

        # 点滅判定
        is_blinking, blink_interval_ms = self.blink_detector.update(circle.id, color_name)

        return DetectionResult(
            circle_id=circle.id,
            detected_color=color_name,
            is_blinking=is_blinking,
            raw_hsv=hsv,
            blink_interval_ms=blink_interval_ms,
        )

    def _get_circle_region(self, frame: np.ndarray, circle: Circle) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        円領域を切り出し、マスクを生成

        Args:
            frame: 入力フレーム (BGR)
            circle: 円情報

        Returns:
            (切り出し領域, マスク) またはエラー時 (None, None)
        """
        h, w = frame.shape[:2]

        # バウンディングボックス計算
        x1 = max(0, circle.center_x - circle.radius)
        y1 = max(0, circle.center_y - circle.radius)
        x2 = min(w, circle.center_x + circle.radius)
        y2 = min(h, circle.center_y + circle.radius)

        if x1 >= x2 or y1 >= y2:
            return None, None

        # 領域切り出し
        roi = frame[y1:y2, x1:x2].copy()

        # 円形マスク作成
        mask = np.zeros(roi.shape[:2], dtype=np.uint8)
        center_in_roi = (circle.center_x - x1, circle.center_y - y1)
        cv2.circle(mask, center_in_roi, circle.radius, 255, -1)

        return roi, mask

    def _calculate_average_hsv(self, roi: np.ndarray, mask: np.ndarray) -> Tuple[int, int, int]:
        """
        マスク領域内の平均HSVを計算

        Args:
            roi: 切り出し領域 (BGR)
            mask: 円形マスク

        Returns:
            (H, S, V) の平均値
        """
        # BGR → HSV
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # マスク内のピクセルのみ抽出
        masked_pixels = hsv[mask > 0]

        if len(masked_pixels) == 0:
            return (0, 0, 0)

        # 色相（H）は循環するため特別な処理
        h_values = masked_pixels[:, 0].astype(float)
        h_rad = h_values * np.pi / 90  # 0-179 → 0-2π

        h_sin = np.mean(np.sin(h_rad))
        h_cos = np.mean(np.cos(h_rad))
        h_avg = np.arctan2(h_sin, h_cos) * 90 / np.pi
        if h_avg < 0:
            h_avg += 180

        # S, V は単純平均
        s_avg = np.mean(masked_pixels[:, 1])
        v_avg = np.mean(masked_pixels[:, 2])

        return (int(h_avg), int(s_avg), int(v_avg))

    def _match_color(self, hsv: Tuple[int, int, int], colors: List[ColorRange]) -> Optional[str]:
        """
        HSV値を登録色とマッチング

        Args:
            hsv: 検出したHSV値
            colors: 登録色リスト

        Returns:
            マッチした色名、なければNone
        """
        h, s, v = hsv

        for color in colors:
            # 色相（H）の判定 - 循環を考慮
            h_min = color.h_center - color.h_range
            h_max = color.h_center + color.h_range

            h_match = False
            if h_min < 0:
                h_match = (h >= h_min + 180) or (h <= h_max)
            elif h_max >= 180:
                h_match = (h >= h_min) or (h <= h_max - 180)
            else:
                h_match = h_min <= h <= h_max

            # 彩度（S）と明度（V）の判定
            s_match = color.s_min <= s <= color.s_max
            v_match = color.v_min <= v <= color.v_max

            if h_match and s_match and v_match:
                return color.name

        return None

    def reset(self):
        """点滅履歴をリセット"""
        self.blink_detector.reset()
