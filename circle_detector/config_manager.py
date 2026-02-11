#!/usr/bin/env python3
"""
設定管理モジュール

円、グループ、ルールの設定を管理し、JSONファイルに永続化する。
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any


# =============================================================================
# データクラス
# =============================================================================

@dataclass
class ColorRange:
    """色の範囲定義"""
    name: str
    h_center: int      # 0-179
    h_range: int       # 許容範囲
    s_min: int         # 0-255
    s_max: int
    v_min: int         # 0-255
    v_max: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'ColorRange':
        return cls(**d)


@dataclass
class Circle:
    """円領域"""
    id: int
    name: str
    center_x: int
    center_y: int
    radius: int
    group_id: Optional[int] = None
    colors: List[ColorRange] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['colors'] = [c.to_dict() if isinstance(c, ColorRange) else c for c in self.colors]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Circle':
        colors = [ColorRange.from_dict(c) if isinstance(c, dict) else c for c in d.get('colors', [])]
        return cls(
            id=d['id'],
            name=d['name'],
            center_x=d['center_x'],
            center_y=d['center_y'],
            radius=d['radius'],
            group_id=d.get('group_id'),
            colors=colors
        )


@dataclass
class RuleCondition:
    """ルール条件"""
    circle_id: int
    color: str
    blinking: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'RuleCondition':
        return cls(**d)


@dataclass
class Rule:
    """マッピングルール"""
    id: int
    group_id: int
    priority: int
    type: str          # "single" or "composite"
    conditions: List[RuleCondition] = field(default_factory=list)
    value: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d['conditions'] = [c.to_dict() if isinstance(c, RuleCondition) else c for c in self.conditions]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> 'Rule':
        conditions = [RuleCondition.from_dict(c) if isinstance(c, dict) else c
                      for c in d.get('conditions', [])]
        return cls(
            id=d['id'],
            group_id=d['group_id'],
            priority=d['priority'],
            type=d['type'],
            conditions=conditions,
            value=d.get('value', 0)
        )


@dataclass
class Group:
    """グループ（パトライト）"""
    id: int
    name: str
    sta_no2: str
    sta_no3: str
    default_value: int = 0
    circle_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'Group':
        return cls(**d)


@dataclass
class DetectionResult:
    """検出結果"""
    circle_id: int
    detected_color: Optional[str]
    is_blinking: bool
    raw_hsv: tuple  # (H, S, V)

    def to_dict(self) -> dict:
        return {
            'circle_id': self.circle_id,
            'detected_color': self.detected_color,
            'is_blinking': self.is_blinking,
            'raw_hsv': list(self.raw_hsv)
        }


@dataclass
class SendData:
    """送信データ"""
    mk_date: str
    sta_no1: str
    sta_no2: str
    sta_no3: str
    t1_status: int

    def to_dict(self) -> dict:
        return asdict(self)


# =============================================================================
# ConfigManager クラス
# =============================================================================

class ConfigManager:
    """設定管理クラス"""

    DEFAULT_CONFIG_PATH = "config/circle_detector.json"

    def __init__(self, config_path: str = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self.config: dict = {}
        self.circles: List[Circle] = []
        self.groups: List[Group] = []
        self.rules: List[Rule] = []
        self._next_circle_id = 1
        self._next_group_id = 1
        self._next_rule_id = 1

    def load(self) -> bool:
        """設定ファイルを読み込み"""
        if not os.path.exists(self.config_path):
            self._init_default()
            return False

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self._parse_config()
            return True
        except Exception as e:
            print(f"Config load error: {e}")
            self._init_default()
            return False

    def save(self) -> bool:
        """設定ファイルに保存"""
        try:
            self.config['circles'] = [c.to_dict() for c in self.circles]
            self.config['groups'] = [g.to_dict() for g in self.groups]
            self.config['rules'] = [r.to_dict() for r in self.rules]
            self.config['updated'] = datetime.now().isoformat()

            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Config save error: {e}")
            return False

    # -------------------------------------------------------------------------
    # Circle 操作
    # -------------------------------------------------------------------------

    def add_circle(self, name: str, center_x: int, center_y: int, radius: int,
                   group_id: int = None) -> Circle:
        """円を追加"""
        circle = Circle(
            id=self._next_circle_id,
            name=name,
            center_x=center_x,
            center_y=center_y,
            radius=radius,
            group_id=group_id,
            colors=[]
        )
        self._next_circle_id += 1
        self.circles.append(circle)
        return circle

    def get_circle(self, circle_id: int) -> Optional[Circle]:
        """円を取得"""
        return next((c for c in self.circles if c.id == circle_id), None)

    def update_circle(self, circle_id: int, **kwargs) -> Optional[Circle]:
        """円を更新"""
        circle = self.get_circle(circle_id)
        if not circle:
            return None

        for key, value in kwargs.items():
            if hasattr(circle, key):
                setattr(circle, key, value)
        return circle

    def delete_circle(self, circle_id: int) -> bool:
        """円を削除"""
        original_len = len(self.circles)
        self.circles = [c for c in self.circles if c.id != circle_id]

        # グループからも削除
        for group in self.groups:
            if circle_id in group.circle_ids:
                group.circle_ids.remove(circle_id)

        # ルールの条件からも削除
        rules_to_remove = []
        for rule in self.rules:
            rule.conditions = [c for c in rule.conditions if c.circle_id != circle_id]
            if not rule.conditions:
                rules_to_remove.append(rule.id)

        for rule_id in rules_to_remove:
            self.delete_rule(rule_id)

        return len(self.circles) < original_len

    def add_color_to_circle(self, circle_id: int, color: ColorRange) -> bool:
        """円に色を追加"""
        circle = self.get_circle(circle_id)
        if not circle:
            return False
        circle.colors.append(color)
        return True

    def update_color_in_circle(self, circle_id: int, color_name: str, color: ColorRange) -> bool:
        """円の既存色を更新"""
        circle = self.get_circle(circle_id)
        if not circle:
            return False
        for i, c in enumerate(circle.colors):
            if c.name == color_name:
                circle.colors[i] = color
                return True
        return False

    def remove_color_from_circle(self, circle_id: int, color_name: str) -> bool:
        """円から色を削除"""
        circle = self.get_circle(circle_id)
        if not circle:
            return False
        original_len = len(circle.colors)
        circle.colors = [c for c in circle.colors if c.name != color_name]
        return len(circle.colors) < original_len

    # -------------------------------------------------------------------------
    # Group 操作
    # -------------------------------------------------------------------------

    def add_group(self, name: str, sta_no2: str, sta_no3: str,
                  default_value: int = 0) -> Group:
        """グループを追加"""
        group = Group(
            id=self._next_group_id,
            name=name,
            sta_no2=sta_no2,
            sta_no3=sta_no3,
            default_value=default_value,
            circle_ids=[]
        )
        self._next_group_id += 1
        self.groups.append(group)
        return group

    def get_group(self, group_id: int) -> Optional[Group]:
        """グループを取得"""
        return next((g for g in self.groups if g.id == group_id), None)

    def update_group(self, group_id: int, **kwargs) -> Optional[Group]:
        """グループを更新"""
        group = self.get_group(group_id)
        if not group:
            return None

        for key, value in kwargs.items():
            if hasattr(group, key):
                setattr(group, key, value)
        return group

    def delete_group(self, group_id: int) -> bool:
        """グループを削除"""
        original_len = len(self.groups)
        self.groups = [g for g in self.groups if g.id != group_id]

        # 円のgroup_idをクリア
        for circle in self.circles:
            if circle.group_id == group_id:
                circle.group_id = None

        # ルールも削除
        self.rules = [r for r in self.rules if r.group_id != group_id]

        return len(self.groups) < original_len

    def add_circle_to_group(self, group_id: int, circle_id: int) -> bool:
        """グループに円を追加"""
        group = self.get_group(group_id)
        circle = self.get_circle(circle_id)
        if not group or not circle:
            return False

        if circle_id not in group.circle_ids:
            group.circle_ids.append(circle_id)
        circle.group_id = group_id
        return True

    def remove_circle_from_group(self, group_id: int, circle_id: int) -> bool:
        """グループから円を削除"""
        group = self.get_group(group_id)
        circle = self.get_circle(circle_id)
        if not group:
            return False

        if circle_id in group.circle_ids:
            group.circle_ids.remove(circle_id)
        if circle and circle.group_id == group_id:
            circle.group_id = None
        return True

    # -------------------------------------------------------------------------
    # Rule 操作
    # -------------------------------------------------------------------------

    def add_rule(self, group_id: int, priority: int, rule_type: str,
                 conditions: List[RuleCondition], value: int) -> Rule:
        """ルールを追加"""
        rule = Rule(
            id=self._next_rule_id,
            group_id=group_id,
            priority=priority,
            type=rule_type,
            conditions=conditions,
            value=value
        )
        self._next_rule_id += 1
        self.rules.append(rule)
        return rule

    def get_rule(self, rule_id: int) -> Optional[Rule]:
        """ルールを取得"""
        return next((r for r in self.rules if r.id == rule_id), None)

    def get_rules_for_group(self, group_id: int) -> List[Rule]:
        """グループのルールを取得（優先度降順）"""
        group_rules = [r for r in self.rules if r.group_id == group_id]
        return sorted(group_rules, key=lambda r: r.priority, reverse=True)

    def update_rule(self, rule_id: int, **kwargs) -> Optional[Rule]:
        """ルールを更新"""
        rule = self.get_rule(rule_id)
        if not rule:
            return None

        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        return rule

    def delete_rule(self, rule_id: int) -> bool:
        """ルールを削除"""
        original_len = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        return len(self.rules) < original_len

    # -------------------------------------------------------------------------
    # 設定取得
    # -------------------------------------------------------------------------

    def get_sta_no1(self) -> str:
        """STA_NO1を取得"""
        return self.config.get('station', {}).get('sta_no1', 'PLANT01')

    def set_sta_no1(self, value: str):
        """STA_NO1を設定"""
        if 'station' not in self.config:
            self.config['station'] = {}
        self.config['station']['sta_no1'] = value

    def get_sta_no1_options(self) -> List[str]:
        """STA_NO1の選択肢を取得"""
        return self.config.get('station', {}).get('sta_no1_options', ['PLANT01'])

    def get_mqtt_config(self) -> dict:
        """MQTT設定を取得"""
        return self.config.get('mqtt', {
            'broker': 'localhost',
            'port': 1883,
            'topic': 'equipment/status',
            'enabled': True
        })

    def set_mqtt_config(self, **kwargs):
        """MQTT設定を更新"""
        if 'mqtt' not in self.config:
            self.config['mqtt'] = {}
        self.config['mqtt'].update(kwargs)

    def get_camera_config(self) -> dict:
        """カメラ設定を取得"""
        return self.config.get('camera', {
            'device': 'usb',
            'width': 640,
            'height': 480
        })

    def set_camera_config(self, **kwargs):
        """カメラ設定を更新"""
        if 'camera' not in self.config:
            self.config['camera'] = {}
        self.config['camera'].update(kwargs)

    def get_detection_config(self) -> dict:
        """検出設定を取得"""
        return self.config.get('detection', {
            'send_mode': 'on_change',
            'send_interval_sec': 1,
            'show_video_in_run_mode': True
        })

    def set_detection_config(self, **kwargs):
        """検出設定を更新"""
        if 'detection' not in self.config:
            self.config['detection'] = {}
        self.config['detection'].update(kwargs)

    def get_blink_config(self) -> dict:
        """点滅検出設定を取得"""
        return self.config.get('blink_detection', {
            'window_ms': 2000,
            'min_changes': 3,
            'min_interval_ms': 100,
            'max_interval_ms': 1500
        })

    def set_blink_config(self, **kwargs):
        """点滅検出設定を更新"""
        if 'blink_detection' not in self.config:
            self.config['blink_detection'] = {}
        self.config['blink_detection'].update(kwargs)

    def get_ntp_config(self) -> dict:
        """NTP同期設定を取得"""
        return self.config.get('ntp', {
            'enabled': False,
            'server': 'ntp.nict.jp',
            'interval_sec': 3600
        })

    def set_ntp_config(self, **kwargs):
        """NTP同期設定を更新"""
        if 'ntp' not in self.config:
            self.config['ntp'] = {}
        self.config['ntp'].update(kwargs)

    # -------------------------------------------------------------------------
    # API用変換
    # -------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """設定を辞書形式で取得（API用）"""
        return {
            'station': self.config.get('station', {}),
            'mqtt': self.get_mqtt_config(),
            'camera': self.get_camera_config(),
            'detection': self.get_detection_config(),
            'blink_detection': self.get_blink_config(),
            'circles': [c.to_dict() for c in self.circles],
            'groups': [g.to_dict() for g in self.groups],
            'rules': [r.to_dict() for r in self.rules]
        }

    # -------------------------------------------------------------------------
    # 内部メソッド
    # -------------------------------------------------------------------------

    def _init_default(self):
        """デフォルト設定を初期化"""
        self.config = {
            'version': '1.0',
            'created': datetime.now().isoformat(),
            'station': {
                'sta_no1': 'PLANT01',
                'sta_no1_options': ['PLANT01', 'PLANT02', 'PLANT03']
            },
            'mqtt': {
                'broker': 'localhost',
                'port': 1883,
                'topic': 'equipment/status',
                'enabled': True
            },
            'camera': {
                'device': 'usb',
                'width': 640,
                'height': 480
            },
            'detection': {
                'send_mode': 'on_change',
                'send_interval_sec': 1,
                'show_video_in_run_mode': True
            },
            'blink_detection': {
                'window_ms': 2000,
                'min_changes': 3,
                'min_interval_ms': 100,
                'max_interval_ms': 1500
            },
            'circles': [],
            'groups': [],
            'rules': []
        }
        self.circles = []
        self.groups = []
        self.rules = []

    def _parse_config(self):
        """設定をパース"""
        # circles
        self.circles = []
        for c in self.config.get('circles', []):
            circle = Circle.from_dict(c)
            self.circles.append(circle)
            self._next_circle_id = max(self._next_circle_id, circle.id + 1)

        # groups
        self.groups = []
        for g in self.config.get('groups', []):
            group = Group.from_dict(g)
            self.groups.append(group)
            self._next_group_id = max(self._next_group_id, group.id + 1)

        # rules
        self.rules = []
        for r in self.config.get('rules', []):
            rule = Rule.from_dict(r)
            self.rules.append(rule)
            self._next_rule_id = max(self._next_rule_id, rule.id + 1)


# =============================================================================
# テスト
# =============================================================================

if __name__ == "__main__":
    import tempfile

    # テスト用の一時ファイル
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        test_file = f.name

    print(f"テストファイル: {test_file}")

    # 設定マネージャー作成
    config = ConfigManager(test_file)
    config.load()

    # 円を追加
    circle1 = config.add_circle("ランプ1", 100, 100, 25)
    circle2 = config.add_circle("ランプ2", 200, 100, 25)
    print(f"円追加: {circle1.name}, {circle2.name}")

    # 色を追加
    config.add_color_to_circle(circle1.id, ColorRange(
        name="赤", h_center=0, h_range=10,
        s_min=100, s_max=255, v_min=100, v_max=255
    ))
    config.add_color_to_circle(circle1.id, ColorRange(
        name="緑", h_center=60, h_range=10,
        s_min=100, s_max=255, v_min=100, v_max=255
    ))
    print(f"円1の色: {[c.name for c in config.get_circle(circle1.id).colors]}")

    # グループを追加
    group1 = config.add_group("パトライト1", "LINE01", "EQUIP01")
    config.add_circle_to_group(group1.id, circle1.id)
    config.add_circle_to_group(group1.id, circle2.id)
    print(f"グループ: {group1.name}, 円: {group1.circle_ids}")

    # ルールを追加
    rule1 = config.add_rule(
        group_id=group1.id,
        priority=100,
        rule_type="single",
        conditions=[RuleCondition(circle_id=circle1.id, color="赤", blinking=False)],
        value=10
    )
    print(f"ルール追加: priority={rule1.priority}, value={rule1.value}")

    # 保存
    config.save()
    print("設定保存完了")

    # 再読み込み
    config2 = ConfigManager(test_file)
    config2.load()
    print(f"再読み込み: 円={len(config2.circles)}, グループ={len(config2.groups)}, ルール={len(config2.rules)}")

    # クリーンアップ
    os.remove(test_file)
    print("テスト完了")
