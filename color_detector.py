#!/usr/bin/env python3
"""
色検知・設備稼働状況監視アプリ（独立版）

信号灯の色と点滅状態を検出し、設備の稼働状況を判定
MQTTで送信、ローカルファイルにログ保存

使用方法:
    python3 color_detector.py -i usb                    # USBカメラ
    python3 color_detector.py -i usb --mqtt             # MQTT送信有効
    python3 color_detector.py -i usb -c config.json     # 設定ファイル使用
"""

import cv2
import numpy as np
import json
import os
import sys
import math
import time
import argparse
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple
from collections import deque
from PIL import Image, ImageDraw, ImageFont

# 設備稼働状況モジュール
from equipment_status import (
    EquipmentStatusManager, EquipmentConfig, StationConfig,
    MQTTConfig, BlinkConfig, RegionConfig as EqRegionConfig,
    MQTTPublisher, LocalStatusLogger, EquipmentStatusCode,
    STATUS_NAMES_JP, STATUS_COLORS_BGR,
    load_equipment_config
)


# =============================================================================
# 定数定義
# =============================================================================

APP_NAME = "色検知・設備監視"
APP_VERSION = "1.0.0"

# アプリケーション設定
DEFAULT_THRESHOLD = 30
DEFAULT_DEBOUNCE_MS = 500
MAX_REGIONS = 10
MIN_REGION_SIZE = 10
MAX_REGION_RATIO = 0.5
LOG_DISPLAY_COUNT = 5

# 表示設定
PANEL_HEIGHT = 180
FONT_SCALE = 0.5
BORDER_THICKNESS = 2
SELECTED_BORDER_THICKNESS = 3
BUTTON_HEIGHT = 30
BUTTON_MARGIN = 5

# キーバインド
KEY_BINDINGS = {
    ord('m'): 'toggle_monitoring',
    ord('M'): 'toggle_monitoring',
    ord('n'): 'add_region',
    ord('N'): 'add_region',
    ord('d'): 'delete_region',
    ord('D'): 'delete_region',
    ord('s'): 'save_config',
    ord('S'): 'save_config',
    ord('l'): 'load_config',
    ord('L'): 'load_config',
    ord('h'): 'show_help',
    ord('H'): 'show_help',
    ord('q'): 'quit',
    ord('Q'): 'quit',
    27: 'cancel',
    9: 'next_region',
    ord('+'): 'increase_threshold',
    ord('='): 'increase_threshold',
    ord('-'): 'decrease_threshold',
}


# =============================================================================
# データクラス
# =============================================================================

@dataclass
class Region:
    """監視領域"""
    id: int
    name: str
    x: int
    y: int
    width: int
    height: int
    threshold: int = 30
    sta_no3: str = ""
    enabled: bool = True


@dataclass
class ColorInfo:
    """色情報"""
    r: int
    g: int
    b: int
    h: int
    s: int
    v: int
    name: str


@dataclass
class ColorChangeEvent:
    """色変化イベント"""
    timestamp: str
    region_id: int
    region_name: str
    previous_color: ColorInfo
    current_color: ColorInfo
    frame_number: int


@dataclass
class AppState:
    """アプリケーション状態"""
    mode: str = "normal"
    is_running: bool = True
    is_monitoring: bool = False  # 監視中フラグ（False=準備中、True=送信中）
    frame_count: int = 0
    drawing_start: Optional[Tuple[int, int]] = None
    drawing_end: Optional[Tuple[int, int]] = None
    error_message: str = ""
    error_until: float = 0


@dataclass
class Button:
    """GUIボタン"""
    id: str
    label: str
    x: int
    y: int
    width: int
    height: int
    color: Tuple[int, int, int] = (80, 80, 80)
    hover_color: Tuple[int, int, int] = (100, 100, 100)
    text_color: Tuple[int, int, int] = (255, 255, 255)
    enabled: bool = True


# =============================================================================
# CameraInput クラス
# =============================================================================

class CameraInput:
    """カメラ入力管理"""

    def __init__(self, source: str):
        self.source = source
        self.cap = None
        self.frame_width = 0
        self.frame_height = 0

    def open(self) -> bool:
        if self.source == "usb":
            self.cap = cv2.VideoCapture(0)
        elif self.source == "rpi":
            self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        elif self.source.startswith("/dev/"):
            device_num = int(self.source.replace("/dev/video", ""))
            self.cap = cv2.VideoCapture(device_num)
        else:
            self.cap = cv2.VideoCapture(self.source)

        if self.cap and self.cap.isOpened():
            self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            return True
        return False

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.cap:
            return self.cap.read()
        return False, None

    def release(self):
        if self.cap:
            self.cap.release()


# =============================================================================
# ROIManager クラス
# =============================================================================

class ROIManager:
    """領域管理"""

    def __init__(self, frame_width: int, frame_height: int):
        self.regions: List[Region] = []
        self.selected_id: int = -1
        self.next_id: int = 1
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.max_size = int(frame_width * frame_height * MAX_REGION_RATIO)

    def add(self, x: int, y: int, w: int, h: int, name: str = None) -> Tuple[Optional[Region], str]:
        if w < 0:
            x, w = x + w, -w
        if h < 0:
            y, h = y + h, -h

        if w < MIN_REGION_SIZE or h < MIN_REGION_SIZE:
            return None, f"サイズが小さすぎます（最小: {MIN_REGION_SIZE}px）"
        if w * h > self.max_size:
            return None, "サイズが大きすぎます（最大: 画面の50%）"
        if len(self.regions) >= MAX_REGIONS:
            return None, f"領域数が上限（{MAX_REGIONS}個）に達しています"

        new_region = Region(
            id=self.next_id,
            name=name or f"領域{self.next_id}",
            x=x, y=y, width=w, height=h,
            sta_no3=f"EQ{self.next_id:03d}"
        )

        self.regions.append(new_region)
        self.selected_id = new_region.id
        self.next_id += 1
        return new_region, ""

    def remove(self, region_id: int = None):
        if region_id is None:
            region_id = self.selected_id
        if region_id < 0:
            return
        self.regions = [r for r in self.regions if r.id != region_id]
        if self.selected_id == region_id:
            self.selected_id = self.regions[0].id if self.regions else -1

    def select_next(self):
        if not self.regions:
            return
        ids = [r.id for r in self.regions]
        if self.selected_id not in ids:
            self.selected_id = ids[0]
        else:
            idx = ids.index(self.selected_id)
            self.selected_id = ids[(idx + 1) % len(ids)]

    def get_selected(self) -> Optional[Region]:
        for r in self.regions:
            if r.id == self.selected_id:
                return r
        return None

    def save(self, filepath: str) -> str:
        try:
            config = {
                "version": "2.0",
                "created": datetime.now().isoformat(),
                "regions": [asdict(r) for r in self.regions]
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            return ""
        except Exception as e:
            return f"保存エラー: {e}"

    def load(self, filepath: str) -> str:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.regions = [Region(**r) for r in config.get("regions", [])]
            if self.regions:
                self.next_id = max(r.id for r in self.regions) + 1
                self.selected_id = self.regions[0].id
            return ""
        except Exception as e:
            return f"読込エラー: {e}"


# =============================================================================
# ColorDetector クラス
# =============================================================================

class ColorDetector:
    """色検出"""

    COLOR_RANGES = {
        "red":    [((0, 100, 50), (10, 255, 255)),
                   ((160, 100, 50), (180, 255, 255))],
        "orange": [((10, 100, 50), (25, 255, 255))],
        "yellow": [((25, 100, 50), (40, 255, 255))],
        "green":  [((40, 100, 50), (80, 255, 255))],
        "blue":   [((100, 100, 50), (130, 255, 255))],
        "purple": [((130, 100, 50), (160, 255, 255))],
        "white":  [((0, 0, 200), (180, 30, 255))],
        "black":  [((0, 0, 0), (180, 255, 50))],
        "gray":   [((0, 0, 50), (180, 30, 200))],
    }

    COLOR_NAMES_JP = {
        "red": "赤", "orange": "オレンジ", "yellow": "黄",
        "green": "緑", "blue": "青", "purple": "紫",
        "white": "白", "black": "黒", "gray": "灰",
        "unknown": "不明"
    }

    COLOR_BGR = {
        "red": (0, 0, 255), "orange": (0, 165, 255),
        "yellow": (0, 255, 255), "green": (0, 255, 0),
        "blue": (255, 0, 0), "purple": (255, 0, 255),
        "white": (255, 255, 255), "black": (0, 0, 0),
        "gray": (128, 128, 128), "unknown": (128, 128, 128),
    }

    def detect(self, frame: np.ndarray, region: Region) -> Optional[ColorInfo]:
        if (region.x < 0 or region.y < 0 or
            region.x + region.width > frame.shape[1] or
            region.y + region.height > frame.shape[0]):
            return None

        roi = frame[region.y:region.y+region.height,
                    region.x:region.x+region.width]

        if roi.size == 0:
            return None

        mean_bgr = cv2.mean(roi)[:3]
        b, g, r = int(mean_bgr[0]), int(mean_bgr[1]), int(mean_bgr[2])

        hsv_pixel = cv2.cvtColor(
            np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV
        )[0][0]
        h, s, v = int(hsv_pixel[0]), int(hsv_pixel[1]), int(hsv_pixel[2])

        color_name = self._get_color_name(h, s, v)

        return ColorInfo(r=r, g=g, b=b, h=h, s=s, v=v, name=color_name)

    def _get_color_name(self, h: int, s: int, v: int) -> str:
        for name, ranges in self.COLOR_RANGES.items():
            for (h_min, s_min, v_min), (h_max, s_max, v_max) in ranges:
                if (h_min <= h <= h_max and
                    s_min <= s <= s_max and
                    v_min <= v <= v_max):
                    return name
        return "unknown"

    def get_color_name_jp(self, color_name: str) -> str:
        return self.COLOR_NAMES_JP.get(color_name, "不明")

    def get_color_bgr(self, color_name: str) -> Tuple[int, int, int]:
        return self.COLOR_BGR.get(color_name, (128, 128, 128))


# =============================================================================
# ChangeDetector クラス
# =============================================================================

class ChangeDetector:
    """変化検出"""

    def __init__(self, default_threshold: int = 30, debounce_ms: int = 500):
        self.default_threshold = default_threshold
        self.debounce_ms = debounce_ms
        self.prev_colors: Dict[int, ColorInfo] = {}
        self.last_change_time: Dict[int, float] = {}

    def check(self, region: Region, current_color: ColorInfo) -> Tuple[bool, Optional[ColorInfo]]:
        region_id = region.id
        threshold = region.threshold or self.default_threshold

        if region_id not in self.prev_colors:
            self.prev_colors[region_id] = current_color
            return False, None

        prev = self.prev_colors[region_id]

        diff = math.sqrt(
            (current_color.r - prev.r) ** 2 +
            (current_color.g - prev.g) ** 2 +
            (current_color.b - prev.b) ** 2
        )

        if diff > threshold:
            now = time.time() * 1000
            last_time = self.last_change_time.get(region_id, 0)

            if now - last_time >= self.debounce_ms:
                self.last_change_time[region_id] = now
                old_color = self.prev_colors[region_id]
                self.prev_colors[region_id] = current_color
                return True, old_color

        return False, None

    def reset(self, region_id: int = None):
        if region_id is None:
            self.prev_colors.clear()
            self.last_change_time.clear()
        else:
            self.prev_colors.pop(region_id, None)
            self.last_change_time.pop(region_id, None)


# =============================================================================
# ColorLogger クラス
# =============================================================================

class ColorLogger:
    """ログ記録"""

    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self.recent_entries: deque = deque(maxlen=LOG_DISPLAY_COUNT)

        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"color_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")

        self._write_entry({
            "timestamp": datetime.now().isoformat(),
            "event": "session_start"
        })

    def log_change(self, event: ColorChangeEvent):
        self.recent_entries.append(event)
        entry = {
            "timestamp": event.timestamp,
            "frame_number": event.frame_number,
            "event_type": "color_change",
            "region_id": event.region_id,
            "region_name": event.region_name,
            "prev_color": {
                "r": event.previous_color.r,
                "g": event.previous_color.g,
                "b": event.previous_color.b,
                "name": event.previous_color.name
            },
            "current_color": {
                "r": event.current_color.r,
                "g": event.current_color.g,
                "b": event.current_color.b,
                "name": event.current_color.name
            }
        }
        self._write_entry(entry)

    def _write_entry(self, entry: dict):
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def get_recent_entries(self) -> List[ColorChangeEvent]:
        return list(self.recent_entries)

    def close(self):
        self._write_entry({
            "timestamp": datetime.now().isoformat(),
            "event_type": "session_end"
        })


# =============================================================================
# UIRenderer クラス
# =============================================================================

class UIRenderer:
    """画面描画"""

    FONT_PATHS = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/takao-gothic/TakaoGothic.ttf",
        "/usr/share/fonts/truetype/vlgothic/VL-Gothic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    def __init__(self, color_detector: ColorDetector, frame_width: int, frame_height: int,
                 equipment_manager: EquipmentStatusManager = None):
        self.font = cv2.FONT_HERSHEY_SIMPLEX
        self.color_detector = color_detector
        self.equipment_manager = equipment_manager
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.buttons: List[Button] = []
        self.hovered_button: Optional[str] = None

        self.pil_font = None
        self.pil_font_small = None
        self._load_japanese_font()
        self._create_buttons()

    def _load_japanese_font(self):
        for font_path in self.FONT_PATHS:
            if os.path.exists(font_path):
                try:
                    self.pil_font = ImageFont.truetype(font_path, 16)
                    self.pil_font_small = ImageFont.truetype(font_path, 12)
                    return
                except Exception:
                    continue
        self.pil_font = ImageFont.load_default()
        self.pil_font_small = ImageFont.load_default()

    def _create_buttons(self):
        button_width = 70
        y = self.frame_height + PANEL_HEIGHT - BUTTON_HEIGHT - 10
        x = 10

        button_defs = [
            ("monitor", "監視開始", (50, 150, 50)),  # 監視開始/停止ボタン
            ("add", "追加", (80, 80, 80)),
            ("delete", "削除", (50, 50, 150)),
            ("save", "保存", (150, 100, 50)),
            ("load", "読込", (100, 100, 50)),
            ("next", "次へ", (80, 80, 80)),
            ("help", "ヘルプ", (80, 80, 80)),
            ("quit", "終了", (100, 50, 50)),
        ]

        for btn_id, label, color in button_defs:
            self.buttons.append(Button(
                id=btn_id, label=label, x=x, y=y,
                width=button_width, height=BUTTON_HEIGHT,
                color=color,
                hover_color=tuple(min(255, c + 30) for c in color)
            ))
            x += button_width + BUTTON_MARGIN

    def get_button_at(self, x: int, y: int) -> Optional[Button]:
        for btn in self.buttons:
            if (btn.x <= x <= btn.x + btn.width and
                btn.y <= y <= btn.y + btn.height and
                btn.enabled):
                return btn
        return None

    def update_hover(self, x: int, y: int):
        btn = self.get_button_at(x, y)
        self.hovered_button = btn.id if btn else None

    def render(self, frame: np.ndarray, regions: List[Region],
               current_colors: Dict[int, ColorInfo],
               recent_logs: List[ColorChangeEvent],
               selected_id: int, state: AppState) -> np.ndarray:

        h, w = frame.shape[:2]
        output = np.zeros((h + PANEL_HEIGHT, w, 3), dtype=np.uint8)
        output[:h, :] = frame

        # 領域の枠を描画
        for region in regions:
            self._draw_region_shapes(output, region,
                                     current_colors.get(region.id),
                                     region.id == selected_id)

        # 描画中の矩形
        if state.mode == "drawing" and state.drawing_start and state.drawing_end:
            x1, y1 = state.drawing_start
            x2, y2 = state.drawing_end
            cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 255), 2)

        # ボタンの背景を描画
        self._draw_button_backgrounds(output, state)

        # エラー背景を描画
        if state.error_message and time.time() < state.error_until:
            cv2.rectangle(output, (10, h - 30), (w - 10, h - 5), (0, 0, 150), -1)

        # ヘルプオーバーレイ背景
        if state.mode == "help":
            overlay = output.copy()
            cv2.rectangle(overlay, (50, 50), (w - 50, h + PANEL_HEIGHT - 50), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.8, output, 0.2, 0, output)

        # テキストを描画
        output = self._draw_all_texts(output, h, w, regions, current_colors,
                                      recent_logs, selected_id, state)

        return output

    def _draw_region_shapes(self, frame: np.ndarray, region: Region,
                            color_info: Optional[ColorInfo], is_selected: bool):
        x, y, w, h = region.x, region.y, region.width, region.height
        border_color = (0, 255, 255) if is_selected else (255, 255, 255)
        thickness = SELECTED_BORDER_THICKNESS if is_selected else BORDER_THICKNESS

        cv2.rectangle(frame, (x, y), (x+w, y+h), border_color, thickness)

        if color_info:
            color_bgr = self.color_detector.get_color_bgr(color_info.name)
            cv2.rectangle(frame, (x+w-25, y+5), (x+w-5, y+25), color_bgr, -1)
            cv2.rectangle(frame, (x+w-25, y+5), (x+w-5, y+25), (255, 255, 255), 1)

    def _draw_button_backgrounds(self, frame: np.ndarray, state: AppState):
        for btn in self.buttons:
            if state.mode == "drawing":
                btn.enabled = btn.id in ["quit"]
            else:
                btn.enabled = True

            # 監視ボタンの色を状態に応じて変更
            if btn.id == "monitor":
                if state.is_monitoring:
                    color = (50, 50, 200)  # 赤系（監視中→停止ボタン）
                else:
                    color = (50, 200, 50)  # 緑系（停止中→開始ボタン）
                if self.hovered_button == btn.id:
                    color = tuple(min(255, c + 30) for c in color)
            elif not btn.enabled:
                color = (50, 50, 50)
            elif self.hovered_button == btn.id:
                color = btn.hover_color
            else:
                color = btn.color

            cv2.rectangle(frame, (btn.x, btn.y),
                         (btn.x + btn.width, btn.y + btn.height), color, -1)
            border_color = (180, 180, 180) if btn.enabled else (80, 80, 80)
            cv2.rectangle(frame, (btn.x, btn.y),
                         (btn.x + btn.width, btn.y + btn.height), border_color, 1)

    def _draw_all_texts(self, frame: np.ndarray, video_h: int, w: int,
                        regions: List[Region], current_colors: Dict[int, ColorInfo],
                        recent_logs: List[ColorChangeEvent], selected_id: int,
                        state: AppState) -> np.ndarray:

        pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_image)

        # 領域ラベル
        for region in regions:
            border_color = (255, 255, 0) if region.id == selected_id else (255, 255, 255)
            label = f"R{region.id}: {region.name}"
            draw.text((region.x, region.y - 18), label, font=self.pil_font_small, fill=border_color)

        # 稼働状況パネル
        y_start = video_h + 5
        draw.text((10, y_start), "=== 稼働状況 ===", font=self.pil_font_small, fill=(200, 200, 200))

        for i, region in enumerate(regions[:4]):
            if self.equipment_manager:
                status = self.equipment_manager.get_status(region.id)
                status_name = STATUS_NAMES_JP.get(status, "不明")
                color_bgr = STATUS_COLORS_BGR.get(status, (128, 128, 128))
                color_rgb = (color_bgr[2], color_bgr[1], color_bgr[0])
                text = f"R{region.id}:{region.name} [{status_name}({int(status)})]"
            else:
                color_info = current_colors.get(region.id)
                if color_info:
                    color_name_jp = self.color_detector.get_color_name_jp(color_info.name)
                    text = f"R{region.id}:{region.name} [{color_name_jp}]"
                    color_rgb = (255, 255, 255)
                else:
                    text = f"R{region.id}:{region.name} [---]"
                    color_rgb = (128, 128, 128)

            x_pos = 10 + (i % 2) * 300
            y_pos = y_start + 18 + (i // 2) * 18
            draw.text((x_pos, y_pos), text, font=self.pil_font_small, fill=color_rgb)

        # ログパネル
        y_log = video_h + 70
        draw.text((10, y_log - 5), "=== Log ===", font=self.pil_font_small, fill=(200, 200, 200))

        for i, event in enumerate(reversed(recent_logs)):
            if i >= 3:
                break
            time_str = event.timestamp.split('T')[1][:8]
            prev_name = self.color_detector.get_color_name_jp(event.previous_color.name)
            curr_name = self.color_detector.get_color_name_jp(event.current_color.name)
            text = f"[{time_str}] {event.region_name}: {prev_name} -> {curr_name}"
            draw.text((10, y_log + 10 + i * 15), text, font=self.pil_font_small, fill=(180, 180, 180))

        # ボタンテキスト
        for btn in self.buttons:
            text_color = (255, 255, 255) if btn.enabled else (100, 100, 100)
            # 監視ボタンのラベルを状態に応じて変更
            if btn.id == "monitor":
                label = "監視停止" if state.is_monitoring else "監視開始"
            else:
                label = btn.label
            bbox = draw.textbbox((0, 0), label, font=self.pil_font_small)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = btn.x + (btn.width - text_width) // 2
            text_y = btn.y + (btn.height - text_height) // 2 - 2
            draw.text((text_x, text_y), label, font=self.pil_font_small, fill=text_color)

        # モード表示
        if state.mode == "drawing":
            status_text = "領域をドラッグで選択してください [ESC]キャンセル"
            draw.text((10, video_h + 2), status_text, font=self.pil_font_small, fill=(0, 255, 255))
        else:
            # 監視状態の表示
            if state.is_monitoring:
                status_text = "● 監視中 - データ送信ON [M]で停止"
                status_color = (100, 255, 100)  # 緑
            else:
                status_text = "○ 準備中 - データ送信OFF [M]で開始"
                status_color = (255, 200, 100)  # オレンジ
            draw.text((w - 280, video_h + 2), status_text, font=self.pil_font_small, fill=status_color)

        # エラーメッセージ
        if state.error_message and time.time() < state.error_until:
            draw.text((20, video_h - 25), state.error_message, font=self.pil_font, fill=(255, 255, 255))

        # ヘルプ画面
        if state.mode == "help":
            help_text = [
                "=== キーボードショートカット ===",
                "",
                "[M] 監視開始/停止（データ送信ON/OFF）",
                "[N] 新しい領域を追加",
                "[D] 選択中の領域を削除",
                "[S] 領域設定を保存",
                "[L] 領域設定を読込",
                "[Tab] 次の領域を選択",
                "[+/-] 閾値を調整",
                "[H] ヘルプを表示/非表示",
                "[Q/ESC] 終了",
                "",
                "何かキーを押すと閉じます"
            ]
            y = 70
            for line in help_text:
                draw.text((70, y), line, font=self.pil_font, fill=(255, 255, 255))
                y += 22

        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


# =============================================================================
# メインアプリケーション
# =============================================================================

class ColorDetectorApp:
    """色検知アプリケーション"""

    def __init__(self, args):
        self.args = args
        self.camera = CameraInput(args.input)
        self.roi_manager = None
        self.color_detector = ColorDetector()
        self.change_detector = ChangeDetector(args.threshold, args.debounce)
        self.logger = None
        self.ui = None
        self.state = AppState()
        self.current_colors: Dict[int, ColorInfo] = {}
        self.window_name = APP_NAME

        # 設備稼働状況機能
        self.equipment_manager = None
        self.mqtt_publisher = None
        self.status_logger = None
        self.equipment_config = None

        self._init_equipment_status()

    def _init_equipment_status(self):
        """設備稼働状況機能を初期化"""
        # 設定ファイルから読み込み（存在すれば）
        config_file = os.path.join(os.path.dirname(__file__), "config", "settings.json")
        if os.path.exists(config_file):
            try:
                self.equipment_config = load_equipment_config(config_file)
                print(f"設定ファイルを読み込みました: {config_file}")
            except Exception as e:
                print(f"設定ファイル読み込みエラー: {e}")
                self.equipment_config = None

        # 設定ファイルがない場合はコマンドライン引数から
        if self.equipment_config is None:
            mqtt_config = MQTTConfig(
                broker=self.args.mqtt_broker,
                port=self.args.mqtt_port,
                topic=self.args.mqtt_topic,
                enabled=self.args.mqtt
            )
            station_config = StationConfig(
                sta_no1=self.args.sta_no1,
                sta_no2=self.args.sta_no2
            )
            self.equipment_config = EquipmentConfig(
                station=station_config,
                mqtt=mqtt_config
            )
        else:
            # コマンドライン引数で上書き
            if self.args.mqtt:
                self.equipment_config.mqtt.enabled = True
            if self.args.mqtt_broker != "localhost":
                self.equipment_config.mqtt.broker = self.args.mqtt_broker
            if self.args.mqtt_port != 1883:
                self.equipment_config.mqtt.port = self.args.mqtt_port
            if self.args.mqtt_topic != "equipment/status":
                self.equipment_config.mqtt.topic = self.args.mqtt_topic
            if self.args.sta_no1:
                self.equipment_config.station.sta_no1 = self.args.sta_no1
            if self.args.sta_no2:
                self.equipment_config.station.sta_no2 = self.args.sta_no2

        self.equipment_manager = EquipmentStatusManager(self.equipment_config)
        self.equipment_manager.on_status_change = self._on_equipment_status_change

        # ローカルログ
        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        self.status_logger = LocalStatusLogger(log_dir)

        # MQTT接続（ブリッジ経由でOracleにも保存される）
        if self.equipment_config.mqtt.enabled:
            mqtt_config = self.equipment_config.mqtt
            self.mqtt_publisher = MQTTPublisher(mqtt_config)
            if self.mqtt_publisher.connect():
                print(f"MQTT connected to {mqtt_config.broker}:{mqtt_config.port}")
                if self.equipment_config.oracle.enabled:
                    print("Oracle: ブリッジ経由で保存（mqtt_oracle_bridge.py を起動してください）")
            else:
                print("Warning: MQTT connection failed")

    def _on_equipment_status_change(self, region_id: int, old_status, new_status):
        """設備稼働状況が変化したときのコールバック"""
        # 監視停止中はデータ送信しない
        if not self.state.is_monitoring:
            return

        region = None
        for r in self.roi_manager.regions:
            if r.id == region_id:
                region = r
                break

        if region is None:
            return

        eq_region = EqRegionConfig(
            id=region.id,
            name=region.name,
            x=region.x,
            y=region.y,
            width=region.width,
            height=region.height,
            sta_no3=getattr(region, 'sta_no3', '') or f"EQ{region.id:03d}"
        )
        message = self.equipment_manager.create_message(region_id, eq_region)

        # ローカルログ
        if self.status_logger:
            self.status_logger.log(message)

        # MQTT送信（ブリッジ経由でOracleにも保存される）
        mqtt_sent = False
        if self.mqtt_publisher:
            subtopic = eq_region.sta_no3
            mqtt_sent = self.mqtt_publisher.publish(message, subtopic)

        old_name = STATUS_NAMES_JP.get(old_status, "不明")
        new_name = STATUS_NAMES_JP.get(new_status, "不明")
        print(f"[{region.name}] {old_name}({int(old_status)}) → {new_name}({int(new_status)}) [MQTT:{'○' if mqtt_sent else '×'}]")

    def run(self):
        """メインループを実行"""
        if not self.camera.open():
            print(f"Error: Cannot open camera: {self.args.input}")
            return

        self.roi_manager = ROIManager(self.camera.frame_width, self.camera.frame_height)
        self.ui = UIRenderer(self.color_detector, self.camera.frame_width,
                             self.camera.frame_height, self.equipment_manager)

        log_dir = os.path.join(os.path.dirname(__file__), "logs")
        self.logger = ColorLogger(log_dir)

        if self.args.config:
            error = self.roi_manager.load(self.args.config)
            if error:
                print(f"Warning: {error}")

        cv2.namedWindow(self.window_name)
        cv2.setMouseCallback(self.window_name, self._mouse_callback)

        print(f"{APP_NAME} v{APP_VERSION} started")
        print(f"Log directory: {log_dir}")
        print("Press 'H' for help, 'Q' to quit")

        while self.state.is_running:
            ret, frame = self.camera.read()
            if not ret:
                print("Error: Cannot read frame")
                break

            self.state.frame_count += 1

            for region in self.roi_manager.regions:
                if hasattr(region, 'enabled') and not region.enabled:
                    continue

                color_info = self.color_detector.detect(frame, region)
                if color_info:
                    self.current_colors[region.id] = color_info

                    if self.equipment_manager:
                        self.equipment_manager.update(region.id, color_info.name)

                    changed, prev_color = self.change_detector.check(region, color_info)
                    if changed and prev_color:
                        event = ColorChangeEvent(
                            timestamp=datetime.now().isoformat(),
                            region_id=region.id,
                            region_name=region.name,
                            previous_color=prev_color,
                            current_color=color_info,
                            frame_number=self.state.frame_count
                        )
                        self.logger.log_change(event)

            output = self.ui.render(
                frame,
                self.roi_manager.regions,
                self.current_colors,
                self.logger.get_recent_entries(),
                self.roi_manager.selected_id,
                self.state
            )

            cv2.imshow(self.window_name, output)

            key = cv2.waitKey(1) & 0xFF
            self._handle_keyboard(key)

        # 終了処理
        self.logger.close()
        if self.mqtt_publisher:
            self.mqtt_publisher.disconnect()
        if self.status_logger:
            self.status_logger.close()
        self.camera.release()
        cv2.destroyAllWindows()
        print(f"{APP_NAME} stopped")

    def _mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            self.ui.update_hover(x, y)

        if self.state.mode == "drawing":
            if event == cv2.EVENT_LBUTTONDOWN:
                if y < self.camera.frame_height:
                    self.state.drawing_start = (x, y)
                    self.state.drawing_end = (x, y)
            elif event == cv2.EVENT_MOUSEMOVE and self.state.drawing_start:
                self.state.drawing_end = (x, y)
            elif event == cv2.EVENT_LBUTTONUP and self.state.drawing_start:
                x1, y1 = self.state.drawing_start
                x2, y2 = x, y
                w, h = x2 - x1, y2 - y1

                region, error = self.roi_manager.add(x1, y1, w, h)
                if error:
                    self._show_error(error)
                else:
                    self.change_detector.reset(region.id)

                self.state.mode = "normal"
                self.state.drawing_start = None
                self.state.drawing_end = None
        else:
            if event == cv2.EVENT_LBUTTONDOWN:
                btn = self.ui.get_button_at(x, y)
                if btn:
                    self._handle_button_click(btn.id)

    def _handle_button_click(self, button_id: str):
        if button_id == "monitor":
            self._toggle_monitoring()
        elif button_id == "add":
            self.state.mode = "drawing"
        elif button_id == "delete":
            if self.roi_manager.selected_id >= 0:
                self.change_detector.reset(self.roi_manager.selected_id)
                self.roi_manager.remove()
        elif button_id == "save":
            config_dir = os.path.join(os.path.dirname(__file__), "config")
            os.makedirs(config_dir, exist_ok=True)
            filepath = os.path.join(config_dir, "regions_config.json")
            error = self.roi_manager.save(filepath)
            if error:
                self._show_error(error)
            else:
                self._show_error(f"保存しました: {filepath}")
        elif button_id == "load":
            config_dir = os.path.join(os.path.dirname(__file__), "config")
            filepath = os.path.join(config_dir, "regions_config.json")
            error = self.roi_manager.load(filepath)
            if error:
                self._show_error(error)
            else:
                self._show_error(f"読み込みました: {filepath}")
        elif button_id == "next":
            self.roi_manager.select_next()
        elif button_id == "help":
            self.state.mode = "help"
        elif button_id == "quit":
            self.state.is_running = False

    def _toggle_monitoring(self):
        """監視状態を切り替え"""
        self.state.is_monitoring = not self.state.is_monitoring
        if self.state.is_monitoring:
            self._show_error("監視開始: データ送信ON")
            print("=== 監視開始 ===")
        else:
            self._show_error("監視停止: データ送信OFF")
            print("=== 監視停止 ===")

    def _handle_keyboard(self, key: int):
        if key == 255:
            return

        if self.state.mode == "help":
            self.state.mode = "normal"
            return

        action = KEY_BINDINGS.get(key)

        if action == "quit":
            self.state.is_running = False
        elif action == "toggle_monitoring":
            self._toggle_monitoring()
        elif action == "cancel":
            if self.state.mode == "drawing":
                self.state.mode = "normal"
                self.state.drawing_start = None
                self.state.drawing_end = None
        elif action == "add_region":
            if self.state.mode == "normal":
                self.state.mode = "drawing"
        elif action == "delete_region":
            if self.roi_manager.selected_id >= 0:
                self.change_detector.reset(self.roi_manager.selected_id)
                self.roi_manager.remove()
        elif action == "save_config":
            self._handle_button_click("save")
        elif action == "load_config":
            self._handle_button_click("load")
        elif action == "next_region":
            self.roi_manager.select_next()
        elif action == "show_help":
            self.state.mode = "help"
        elif action == "increase_threshold":
            region = self.roi_manager.get_selected()
            if region:
                region.threshold = min(255, region.threshold + 5)
                self._show_error(f"Threshold: {region.threshold}")
        elif action == "decrease_threshold":
            region = self.roi_manager.get_selected()
            if region:
                region.threshold = max(5, region.threshold - 5)
                self._show_error(f"Threshold: {region.threshold}")

    def _show_error(self, message: str, duration: float = 2.0):
        self.state.error_message = message
        self.state.error_until = time.time() + duration


# =============================================================================
# エントリーポイント
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - 信号灯の色・点滅を検出し設備稼働状況を監視"
    )
    parser.add_argument("-i", "--input", default="usb",
                       help="入力ソース: usb, rpi, /dev/videoX, ファイルパス")
    parser.add_argument("-c", "--config", default=None,
                       help="領域設定ファイル")
    parser.add_argument("-t", "--threshold", type=int, default=DEFAULT_THRESHOLD,
                       help=f"色変化検出閾値 (default: {DEFAULT_THRESHOLD})")
    parser.add_argument("-d", "--debounce", type=int, default=DEFAULT_DEBOUNCE_MS,
                       help=f"デバウンス時間ms (default: {DEFAULT_DEBOUNCE_MS})")

    # MQTT設定
    parser.add_argument("--mqtt", action="store_true",
                       help="MQTT送信を有効化")
    parser.add_argument("--mqtt-broker", default="localhost",
                       help="MQTTブローカー (default: localhost)")
    parser.add_argument("--mqtt-port", type=int, default=1883,
                       help="MQTTポート (default: 1883)")
    parser.add_argument("--mqtt-topic", default="equipment/status",
                       help="MQTTトピック (default: equipment/status)")
    parser.add_argument("--sta-no1", default="",
                       help="ステーション番号1（工場コード）")
    parser.add_argument("--sta-no2", default="",
                       help="ステーション番号2（ラインコード）")

    return parser.parse_args()


def main():
    args = parse_args()
    app = ColorDetectorApp(args)
    app.run()


if __name__ == "__main__":
    main()
