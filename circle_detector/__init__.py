"""
Circle Detector - 円形領域色検知アプリケーション

カメラ映像内の指定した円形領域の色を検知し、
パトライトの状態を判定してMQTT経由でOracle DBにデータを送信する。
"""

__version__ = "1.0.0"

from .config_manager import (
    ConfigManager, Circle, ColorRange, Group, Rule, RuleCondition,
    DetectionResult, SendData
)
from .camera import CameraManager
from .detector import DetectionEngine, BlinkDetector
from .rule_engine import RuleEngine
from .mqtt_sender import MQTTSender

# Flaskは設定UI側でのみ必要。検出ランタイム側では読み込まない。
try:
    from .app import create_app  # noqa: F401
except ImportError:
    pass
