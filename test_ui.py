#!/usr/bin/env python3
"""
設備状態テストUI
カメラなしで状態を選択してMQTT送信をテストするWebアプリ
設定ファイル: config/settings.json

注意: Oracle保存はMQTT-Oracleブリッジサービス経由で行います
      ブリッジ起動: python3 mqtt_oracle_bridge.py
"""

from flask import Flask, render_template, jsonify, request
from datetime import datetime
import json
import os
import sys
import subprocess

# 同じディレクトリのモジュールをインポート
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from equipment_status import (
    EquipmentStatusCode, STATUS_NAMES_JP,
    MQTTConfig, MQTTPublisher, StatusMessage,
    LocalStatusLogger,
    load_equipment_config, save_equipment_config, EquipmentConfig,
    StationConfig, BlinkConfig
)

app = Flask(__name__)

# アプリケーションディレクトリ
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, "config", "settings.json")

# グローバル変数
mqtt_publisher = None
local_logger = None
equipment_config = None

current_status = {
    "code": 0,
    "name": "不明",
    "color": "unknown",
    "is_blinking": False
}
history = []  # 送信履歴

# 状態定義
STATUS_OPTIONS = [
    {"code": 1, "name": "運転準備", "color": "green", "blinking": True, "display_color": "#00ff00", "icon": "🟢"},
    {"code": 2, "name": "自動運転", "color": "green", "blinking": False, "display_color": "#00cc00", "icon": "🟢"},
    {"code": 3, "name": "通過運転", "color": "yellow", "blinking": False, "display_color": "#ffff00", "icon": "🟡"},
    {"code": 16, "name": "段換中", "color": "yellow", "blinking": True, "display_color": "#ffcc00", "icon": "🟡"},
    {"code": 14, "name": "異常中", "color": "red", "blinking": False, "display_color": "#ff0000", "icon": "🔴"},
]


def load_config():
    """設定ファイルを読み込み"""
    global equipment_config

    if os.path.exists(CONFIG_FILE):
        try:
            equipment_config = load_equipment_config(CONFIG_FILE)
            print(f"設定ファイルを読み込みました: {CONFIG_FILE}")
        except Exception as e:
            print(f"設定ファイル読み込みエラー: {e}")
            equipment_config = EquipmentConfig()
    else:
        # デフォルト設定で作成
        equipment_config = EquipmentConfig(
            station=StationConfig(sta_no1="PLANT01", sta_no2="LINE01"),
            mqtt=MQTTConfig(enabled=True, broker="localhost", port=1883, topic="equipment/status"),
            oracle=OracleConfig(enabled=False)
        )
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        save_equipment_config(equipment_config, CONFIG_FILE)
        print(f"デフォルト設定ファイルを作成しました: {CONFIG_FILE}")

    return equipment_config


def get_config_dict():
    """設定を辞書形式で取得"""
    return {
        "sta_no1": equipment_config.station.sta_no1,
        "sta_no2": equipment_config.station.sta_no2,
        "sta_no3": equipment_config.regions[0].sta_no3 if equipment_config.regions else "EQUIP01",
        "mqtt_enabled": equipment_config.mqtt.enabled,
        "mqtt_broker": equipment_config.mqtt.broker,
        "mqtt_port": equipment_config.mqtt.port,
        "mqtt_topic": equipment_config.mqtt.topic,
        "oracle_enabled": equipment_config.oracle.enabled,
        "oracle_dsn": equipment_config.oracle.dsn,
        "oracle_user": equipment_config.oracle.user,
        "oracle_wallet_dir": equipment_config.oracle.wallet_dir,
        "oracle_table": equipment_config.oracle.table_name
    }


def init_mqtt():
    """MQTT初期化"""
    global mqtt_publisher

    if not equipment_config.mqtt.enabled:
        print("MQTT: 無効")
        return

    mqtt_config = MQTTConfig(
        broker=equipment_config.mqtt.broker,
        port=equipment_config.mqtt.port,
        topic=equipment_config.mqtt.topic,
        client_id="test_ui",
        enabled=True
    )
    mqtt_publisher = MQTTPublisher(mqtt_config)
    mqtt_publisher.connect()


def is_bridge_running():
    """MQTT-Oracleブリッジが起動しているか確認"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "mqtt_oracle_bridge.py"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except:
        return False


def init_logger():
    """ローカルロガー初期化"""
    global local_logger
    log_dir = os.path.join(APP_DIR, "logs")
    local_logger = LocalStatusLogger(log_dir)


@app.route('/')
def index():
    """メインページ"""
    return render_template('test_ui.html',
                          status_options=STATUS_OPTIONS,
                          config=get_config_dict())


@app.route('/api/status', methods=['GET'])
def get_status():
    """現在の状態を取得"""
    mqtt_stats = mqtt_publisher.get_stats() if mqtt_publisher else {"connected": False}
    bridge_running = is_bridge_running()

    return jsonify({
        "current": current_status,
        "mqtt": mqtt_stats,
        "bridge_running": bridge_running,
        "oracle_enabled": equipment_config.oracle.enabled if equipment_config else False,
        "history": history[-20:]  # 直近20件
    })


@app.route('/api/status', methods=['POST'])
def set_status():
    """状態を設定してMQTT/Oracle送信"""
    global current_status

    data = request.json
    code = data.get('code', 0)

    # 対応する状態を検索
    status_info = next((s for s in STATUS_OPTIONS if s['code'] == code), None)
    if not status_info:
        return jsonify({"error": "Invalid status code"}), 400

    # 現在の状態を更新
    current_status = {
        "code": code,
        "name": status_info['name'],
        "color": status_info['color'],
        "is_blinking": status_info['blinking']
    }

    # メッセージ作成
    sta_no3 = equipment_config.regions[0].sta_no3 if equipment_config.regions else "EQUIP01"
    message = StatusMessage(
        mk_date=datetime.now().strftime("%Y%m%d%H%M%S"),
        sta_no1=equipment_config.station.sta_no1,
        sta_no2=equipment_config.station.sta_no2,
        sta_no3=sta_no3,
        t1_status=code,
        color_name=status_info['color'],
        is_blinking=status_info['blinking']
    )

    # MQTT送信（ブリッジ経由でOracleにも保存される）
    mqtt_result = False
    if mqtt_publisher and equipment_config.mqtt.enabled:
        mqtt_result = mqtt_publisher.publish(message)

    # ローカルログ
    if local_logger:
        local_logger.log(message)

    # ブリッジ稼働状況を確認
    bridge_running = is_bridge_running()

    # 履歴に追加
    history_entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "code": code,
        "name": status_info['name'],
        "mqtt_sent": mqtt_result,
        "bridge_running": bridge_running
    }
    history.append(history_entry)

    # 最大100件に制限
    if len(history) > 100:
        history.pop(0)

    return jsonify({
        "success": True,
        "message": message.to_dict(),
        "mqtt_sent": mqtt_result,
        "bridge_running": bridge_running
    })


@app.route('/api/config', methods=['GET'])
def get_config():
    """設定を取得"""
    return jsonify(get_config_dict())


@app.route('/api/config', methods=['POST'])
def update_config():
    """設定を更新して保存"""
    global mqtt_publisher, oracle_connection

    data = request.json

    # 設定を更新
    if 'sta_no1' in data:
        equipment_config.station.sta_no1 = data['sta_no1']
    if 'sta_no2' in data:
        equipment_config.station.sta_no2 = data['sta_no2']
    if 'sta_no3' in data and equipment_config.regions:
        equipment_config.regions[0].sta_no3 = data['sta_no3']

    # MQTT設定
    if 'mqtt_enabled' in data:
        equipment_config.mqtt.enabled = data['mqtt_enabled']
    if 'mqtt_broker' in data:
        equipment_config.mqtt.broker = data['mqtt_broker']
    if 'mqtt_port' in data:
        equipment_config.mqtt.port = int(data['mqtt_port'])
    if 'mqtt_topic' in data:
        equipment_config.mqtt.topic = data['mqtt_topic']

    # Oracle設定
    if 'oracle_enabled' in data:
        equipment_config.oracle.enabled = data['oracle_enabled']
    if 'oracle_dsn' in data:
        equipment_config.oracle.dsn = data['oracle_dsn']
    if 'oracle_user' in data:
        equipment_config.oracle.user = data['oracle_user']
    if 'oracle_password' in data and data['oracle_password']:
        equipment_config.oracle.password = data['oracle_password']
    if 'oracle_wallet_dir' in data:
        equipment_config.oracle.wallet_dir = data['oracle_wallet_dir']
    if 'oracle_wallet_password' in data and data['oracle_wallet_password']:
        equipment_config.oracle.wallet_password = data['oracle_wallet_password']
    if 'oracle_table' in data:
        equipment_config.oracle.table_name = data['oracle_table']

    # 設定ファイルに保存
    try:
        save_equipment_config(equipment_config, CONFIG_FILE)
        print(f"設定を保存しました: {CONFIG_FILE}")
    except Exception as e:
        print(f"設定保存エラー: {e}")

    # MQTT接続を再初期化
    if mqtt_publisher:
        mqtt_publisher.disconnect()
    init_mqtt()

    return jsonify({"success": True, "config": get_config_dict()})


@app.route('/api/mqtt/reconnect', methods=['POST'])
def reconnect_mqtt():
    """MQTT再接続"""
    global mqtt_publisher

    if mqtt_publisher:
        mqtt_publisher.disconnect()
    init_mqtt()

    return jsonify({
        "success": True,
        "connected": mqtt_publisher.connected if mqtt_publisher else False
    })


@app.route('/api/bridge/status', methods=['GET'])
def get_bridge_status():
    """ブリッジサービスの状態を取得"""
    return jsonify({
        "running": is_bridge_running(),
        "oracle_enabled": equipment_config.oracle.enabled if equipment_config else False
    })


@app.route('/api/bridge/start', methods=['POST'])
def start_bridge():
    """ブリッジサービスを起動"""
    if is_bridge_running():
        return jsonify({"success": True, "message": "既に起動しています"})

    try:
        bridge_script = os.path.join(os.path.dirname(__file__), "mqtt_oracle_bridge.py")
        oracle_env_python = "/home/sano/pose_detection/oracle_env/bin/python"

        # バックグラウンドで起動
        subprocess.Popen(
            [oracle_env_python, bridge_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

        # 起動を少し待つ
        import time
        time.sleep(1)

        return jsonify({
            "success": True,
            "running": is_bridge_running()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })


@app.route('/api/bridge/stop', methods=['POST'])
def stop_bridge():
    """ブリッジサービスを停止"""
    try:
        subprocess.run(["pkill", "-f", "mqtt_oracle_bridge.py"], capture_output=True)
        return jsonify({"success": True, "running": False})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == '__main__':
    # テンプレートディレクトリ作成
    template_dir = os.path.join(APP_DIR, 'templates')
    os.makedirs(template_dir, exist_ok=True)

    # 設定読み込み
    load_config()

    # 初期化
    init_mqtt()
    init_logger()

    # ブリッジ状態確認
    bridge_running = is_bridge_running()

    print("=" * 50)
    print("設備状態テストUI")
    print("=" * 50)
    print(f"設定ファイル: {CONFIG_FILE}")
    print(f"MQTT: {'有効' if equipment_config.mqtt.enabled else '無効'}")
    if equipment_config.mqtt.enabled:
        print(f"  Broker: {equipment_config.mqtt.broker}:{equipment_config.mqtt.port}")
        print(f"  Topic: {equipment_config.mqtt.topic}")
        print(f"  接続: {'成功' if (mqtt_publisher and mqtt_publisher.connected) else '失敗'}")
    print(f"Oracle: {'有効' if equipment_config.oracle.enabled else '無効'} (ブリッジ経由)")
    print(f"  ブリッジ: {'起動中' if bridge_running else '停止中'}")
    if not bridge_running and equipment_config.oracle.enabled:
        print("  ※ Oracleに保存するにはブリッジを起動してください")
        print("    python3 mqtt_oracle_bridge.py")
    print("=" * 50)
    print("ブラウザで http://localhost:5001 を開いてください")
    print("=" * 50)

    app.run(host='0.0.0.0', port=5001, debug=False)
