#!/usr/bin/env python3
"""
Circle Detector - Flask メインアプリケーション

カメラ映像の円形領域の色を検知し、マッピングルールで評価、
MQTT経由でOracle DBに送信するWebアプリケーション。
"""

import os
import sys
import time
import threading
from datetime import datetime
from flask import Flask, render_template, Response, jsonify, request

# 親ディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .config_manager import (
    ConfigManager, Circle, ColorRange, Group, Rule, RuleCondition,
    DetectionResult, SendData
)
from .camera import CameraManager
from .detector import DetectionEngine
from .rule_engine import RuleEngine
from .mqtt_sender import MQTTSender


def create_app(config_path: str = None) -> Flask:
    """Flaskアプリケーションを生成"""

    app = Flask(
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), 'static'),
        template_folder=os.path.join(os.path.dirname(__file__), 'templates')
    )

    # -----------------------------------------------------------------------
    # 初期化
    # -----------------------------------------------------------------------
    config_mgr = ConfigManager(config_path)
    config_mgr.load()

    cam_conf = config_mgr.get_camera_config()
    camera = CameraManager(
        device=cam_conf.get('device', 'usb'),
        width=cam_conf.get('width', 640),
        height=cam_conf.get('height', 480)
    )

    detector = DetectionEngine(config_mgr, config_mgr.get_blink_config())
    rule_engine = RuleEngine(config_mgr)
    mqtt_sender = MQTTSender(config_mgr)

    # 実行モード状態
    run_state = {
        "running": False,
        "thread": None,
        "results": [],
        "group_values": {},
        "last_send": None,
        "start_time": None,
        "send_log": []   # 直近の送信ログ (max 50)
    }

    # -----------------------------------------------------------------------
    # ページルーティング
    # -----------------------------------------------------------------------
    @app.route('/')
    def index():
        return render_template('index.html')

    # -----------------------------------------------------------------------
    # 映像ストリーム
    # -----------------------------------------------------------------------
    @app.route('/video_feed')
    def video_feed():
        if not camera.is_running:
            camera.start()
        return Response(
            camera.generate_mjpeg(quality=80),
            mimetype='multipart/x-mixed-replace; boundary=frame'
        )

    # -----------------------------------------------------------------------
    # 設定 API
    # -----------------------------------------------------------------------
    @app.route('/api/config', methods=['GET'])
    def get_config():
        return jsonify(config_mgr.to_dict())

    @app.route('/api/config', methods=['POST'])
    def save_config():
        config_mgr.save()
        return jsonify({"success": True})

    @app.route('/api/mqtt', methods=['GET'])
    def get_mqtt():
        stats = mqtt_sender.get_stats()
        conf = config_mgr.get_mqtt_config()
        return jsonify({**conf, **stats})

    @app.route('/api/bridge/status', methods=['GET'])
    def get_bridge_status():
        """MQTT-Oracle ブリッジのステータスを返す"""
        import json as _json
        status_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs", "bridge_status.json"
        )
        try:
            with open(status_file, 'r') as f:
                data = _json.load(f)
            # ファイルが古すぎる場合（30秒以上）はブリッジ停止とみなす
            from datetime import datetime as _dt
            updated = _dt.fromisoformat(data.get('updated_at', ''))
            age = (_dt.now() - updated).total_seconds()
            if age > 30:
                data['running'] = False
                data['oracle_connected'] = False
            return jsonify(data)
        except (FileNotFoundError, ValueError, KeyError):
            return jsonify({
                "running": False,
                "oracle_connected": False,
                "received": 0,
                "inserted": 0,
                "errors": 0,
                "pending": 0
            })

    @app.route('/api/mqtt', methods=['PUT'])
    def update_mqtt():
        data = request.get_json()
        config_mgr.set_mqtt_config(**data)
        # 実行時パラメータも更新
        if 'broker' in data:
            mqtt_sender.broker = data['broker']
        if 'port' in data:
            mqtt_sender.port = int(data['port'])
        if 'topic' in data:
            mqtt_sender.base_topic = data['topic']
        if 'enabled' in data:
            mqtt_sender.enabled = data['enabled']
        return jsonify({"success": True})

    @app.route('/api/mqtt/connect', methods=['POST'])
    def mqtt_connect():
        import subprocess, time as _time

        mqtt_sender.stop()

        # ローカルブローカーの場合、Mosquittoを起動
        conf = config_mgr.get_mqtt_config()
        broker = conf.get('broker', 'localhost')
        if broker in ('localhost', '127.0.0.1', ''):
            try:
                result = subprocess.run(
                    ['systemctl', 'is-active', 'mosquitto'],
                    capture_output=True, text=True, timeout=5
                )
                if result.stdout.strip() != 'active':
                    subprocess.run(
                        ['sudo', 'systemctl', 'start', 'mosquitto'],
                        capture_output=True, timeout=10
                    )
                    _time.sleep(1)
            except Exception as e:
                print(f"[MQTT] Mosquitto start attempt: {e}")

        # 最新の設定を再読み込み
        mqtt_sender.broker = broker
        mqtt_sender.port = conf.get('port', 1883)
        mqtt_sender.base_topic = conf.get('topic', 'equipment/status')
        mqtt_sender.enabled = conf.get('enabled', True)
        mqtt_sender.start()
        # 接続完了をリトライ付きで待つ（最大3秒）
        for _ in range(15):
            _time.sleep(0.2)
            if mqtt_sender.connected:
                break
        return jsonify({"success": True, "connected": mqtt_sender.is_effectively_connected})

    @app.route('/api/mqtt/disconnect', methods=['POST'])
    def mqtt_disconnect():
        mqtt_sender.stop()
        return jsonify({"success": True})

    @app.route('/api/sta_no1_options', methods=['GET'])
    def get_sta_no1_options():
        return jsonify({"options": config_mgr.get_sta_no1_options()})

    @app.route('/api/sta_no1', methods=['PUT'])
    def set_sta_no1():
        data = request.get_json()
        config_mgr.set_sta_no1(data.get('sta_no1', ''))
        return jsonify({"success": True})

    # -----------------------------------------------------------------------
    # 円 API
    # -----------------------------------------------------------------------
    @app.route('/api/circles', methods=['GET'])
    def get_circles():
        return jsonify([c.to_dict() for c in config_mgr.circles])

    @app.route('/api/circles', methods=['POST'])
    def add_circle():
        data = request.get_json()
        circle = config_mgr.add_circle(
            name=data.get('name', f'円{config_mgr._next_circle_id}'),
            center_x=data['center_x'],
            center_y=data['center_y'],
            radius=data['radius'],
            group_id=data.get('group_id')
        )
        return jsonify({"success": True, "id": circle.id, "circle": circle.to_dict()})

    @app.route('/api/circles/<int:circle_id>', methods=['GET'])
    def get_circle(circle_id):
        circle = config_mgr.get_circle(circle_id)
        if not circle:
            return jsonify({"error": "Circle not found"}), 404
        return jsonify(circle.to_dict())

    @app.route('/api/circles/<int:circle_id>', methods=['PUT'])
    def update_circle(circle_id):
        data = request.get_json()
        circle = config_mgr.update_circle(circle_id, **data)
        if not circle:
            return jsonify({"error": "Circle not found"}), 404
        return jsonify({"success": True, "circle": circle.to_dict()})

    @app.route('/api/circles/<int:circle_id>', methods=['DELETE'])
    def delete_circle(circle_id):
        result = config_mgr.delete_circle(circle_id)
        return jsonify({"success": result})

    # -----------------------------------------------------------------------
    # 円の色 API
    # -----------------------------------------------------------------------
    @app.route('/api/circles/<int:circle_id>/colors', methods=['POST'])
    def add_color(circle_id):
        data = request.get_json()
        color = ColorRange(
            name=data['name'],
            h_center=data['h_center'],
            h_range=data.get('h_range', 10),
            s_min=data.get('s_min', 50),
            s_max=data.get('s_max', 255),
            v_min=data.get('v_min', 50),
            v_max=data.get('v_max', 255)
        )
        result = config_mgr.add_color_to_circle(circle_id, color)
        if not result:
            return jsonify({"error": "Circle not found"}), 404
        return jsonify({"success": True})

    @app.route('/api/circles/<int:circle_id>/colors/<color_name>', methods=['PUT'])
    def update_color(circle_id, color_name):
        data = request.get_json()
        color = ColorRange(
            name=data.get('name', color_name),
            h_center=data['h_center'],
            h_range=data.get('h_range', 10),
            s_min=data.get('s_min', 50),
            s_max=data.get('s_max', 255),
            v_min=data.get('v_min', 50),
            v_max=data.get('v_max', 255)
        )
        result = config_mgr.update_color_in_circle(circle_id, color_name, color)
        if not result:
            return jsonify({"error": "Circle or color not found"}), 404
        return jsonify({"success": True})

    @app.route('/api/circles/<int:circle_id>/colors/<color_name>', methods=['DELETE'])
    def remove_color(circle_id, color_name):
        result = config_mgr.remove_color_from_circle(circle_id, color_name)
        return jsonify({"success": result})

    # -----------------------------------------------------------------------
    # グループ API
    # -----------------------------------------------------------------------
    @app.route('/api/groups', methods=['GET'])
    def get_groups():
        return jsonify([g.to_dict() for g in config_mgr.groups])

    @app.route('/api/groups', methods=['POST'])
    def add_group():
        data = request.get_json()
        group = config_mgr.add_group(
            name=data.get('name', f'パトライト{config_mgr._next_group_id}'),
            sta_no2=data.get('sta_no2', ''),
            sta_no3=data.get('sta_no3', ''),
            default_value=data.get('default_value', 0)
        )
        return jsonify({"success": True, "id": group.id, "group": group.to_dict()})

    @app.route('/api/groups/<int:group_id>', methods=['GET'])
    def get_group(group_id):
        group = config_mgr.get_group(group_id)
        if not group:
            return jsonify({"error": "Group not found"}), 404
        return jsonify(group.to_dict())

    @app.route('/api/groups/<int:group_id>', methods=['PUT'])
    def update_group(group_id):
        data = request.get_json()
        group = config_mgr.update_group(group_id, **data)
        if not group:
            return jsonify({"error": "Group not found"}), 404
        return jsonify({"success": True, "group": group.to_dict()})

    @app.route('/api/groups/<int:group_id>', methods=['DELETE'])
    def delete_group(group_id):
        result = config_mgr.delete_group(group_id)
        return jsonify({"success": result})

    @app.route('/api/groups/<int:group_id>/circles/<int:circle_id>', methods=['POST'])
    def add_circle_to_group(group_id, circle_id):
        result = config_mgr.add_circle_to_group(group_id, circle_id)
        return jsonify({"success": result})

    @app.route('/api/groups/<int:group_id>/circles/<int:circle_id>', methods=['DELETE'])
    def remove_circle_from_group(group_id, circle_id):
        result = config_mgr.remove_circle_from_group(group_id, circle_id)
        return jsonify({"success": result})

    # -----------------------------------------------------------------------
    # ルール API
    # -----------------------------------------------------------------------
    @app.route('/api/rules', methods=['GET'])
    def get_rules():
        return jsonify([r.to_dict() for r in config_mgr.rules])

    @app.route('/api/rules', methods=['POST'])
    def add_rule():
        data = request.get_json()
        conditions = [
            RuleCondition(
                circle_id=c['circle_id'],
                color=c['color'],
                blinking=c.get('blinking', False)
            )
            for c in data.get('conditions', [])
        ]
        rule = config_mgr.add_rule(
            group_id=data['group_id'],
            priority=data.get('priority', 100),
            rule_type=data.get('type', 'single'),
            conditions=conditions,
            value=data.get('value', 0)
        )
        return jsonify({"success": True, "id": rule.id, "rule": rule.to_dict()})

    @app.route('/api/rules/<int:rule_id>', methods=['GET'])
    def get_rule(rule_id):
        rule = config_mgr.get_rule(rule_id)
        if not rule:
            return jsonify({"error": "Rule not found"}), 404
        return jsonify(rule.to_dict())

    @app.route('/api/rules/<int:rule_id>', methods=['PUT'])
    def update_rule(rule_id):
        data = request.get_json()
        # conditionsが含まれている場合はRuleConditionに変換
        if 'conditions' in data:
            data['conditions'] = [
                RuleCondition(
                    circle_id=c['circle_id'],
                    color=c['color'],
                    blinking=c.get('blinking', False)
                )
                for c in data['conditions']
            ]
        rule = config_mgr.update_rule(rule_id, **data)
        if not rule:
            return jsonify({"error": "Rule not found"}), 404
        return jsonify({"success": True, "rule": rule.to_dict()})

    @app.route('/api/rules/<int:rule_id>', methods=['DELETE'])
    def delete_rule(rule_id):
        result = config_mgr.delete_rule(rule_id)
        return jsonify({"success": result})

    # -----------------------------------------------------------------------
    # 色取得 API
    # -----------------------------------------------------------------------
    @app.route('/api/color/<int:x>/<int:y>', methods=['GET'])
    def get_color_at(x, y):
        if not camera.is_running:
            return jsonify({"error": "Camera not running"}), 503

        hsv = camera.get_color_at(x, y, radius=5)
        rgb = camera.get_rgb_at(x, y, radius=5)
        suggested = camera.suggest_color_name(*hsv)

        return jsonify({
            "x": x,
            "y": y,
            "hsv": list(hsv),
            "rgb": list(rgb),
            "suggested_name": suggested
        })

    # -----------------------------------------------------------------------
    # 実行モード API
    # -----------------------------------------------------------------------
    @app.route('/api/status', methods=['GET'])
    def get_status():
        return jsonify({
            "running": run_state["running"],
            "results": [r.to_dict() for r in run_state["results"]],
            "group_values": run_state["group_values"],
            "last_send": run_state["last_send"],
            "start_time": run_state["start_time"],
            "send_log": run_state["send_log"][-20:],
            "mqtt": mqtt_sender.get_stats()
        })

    @app.route('/api/run/start', methods=['POST'])
    def start_run():
        if run_state["running"]:
            return jsonify({"success": False, "error": "Already running"})

        # カメラ開始
        if not camera.is_running:
            if not camera.start():
                return jsonify({"success": False, "error": "Camera start failed"})

        # MQTT開始
        mqtt_sender.start()
        mqtt_sender.reset_last_values()

        # 点滅検出リセット
        detector.reset()

        run_state["running"] = True
        run_state["start_time"] = datetime.now().isoformat()
        run_state["send_log"] = []

        # 検出ループスレッド開始
        run_state["thread"] = threading.Thread(target=_detection_loop, daemon=True)
        run_state["thread"].start()

        return jsonify({"success": True})

    @app.route('/api/run/stop', methods=['POST'])
    def stop_run():
        run_state["running"] = False

        if run_state["thread"]:
            run_state["thread"].join(timeout=3.0)
            run_state["thread"] = None

        mqtt_sender.stop()

        return jsonify({"success": True})

    # -----------------------------------------------------------------------
    # カメラ制御 API
    # -----------------------------------------------------------------------
    @app.route('/api/camera/start', methods=['POST'])
    def start_camera():
        if camera.is_running:
            return jsonify({"success": True, "message": "Already running"})
        result = camera.start()
        return jsonify({"success": result})

    @app.route('/api/camera/stop', methods=['POST'])
    def stop_camera():
        if not run_state["running"]:
            camera.stop()
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Cannot stop camera while running"})

    @app.route('/api/camera/status', methods=['GET'])
    def camera_status():
        return jsonify({
            "running": camera.is_running,
            "frame_size": list(camera.frame_size)
        })

    # -----------------------------------------------------------------------
    # 検出ループ（バックグラウンドスレッド）
    # -----------------------------------------------------------------------
    def _detection_loop():
        """実行モードの検出ループ"""
        detection_conf = config_mgr.get_detection_config()
        send_mode = detection_conf.get('send_mode', 'on_change')
        send_interval = detection_conf.get('send_interval_sec', 1)
        last_periodic_send = 0

        while run_state["running"]:
            frame = camera.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue

            # 全円の色を検出
            results = detector.detect_all(frame)
            run_state["results"] = results

            # ルール評価
            group_values = rule_engine.evaluate_all_groups(results)
            run_state["group_values"] = group_values

            # 送信
            now = time.time()
            should_send = False

            if send_mode == 'periodic':
                if now - last_periodic_send >= send_interval:
                    should_send = True
                    last_periodic_send = now
            else:
                # on_change: MQTTSender内部で変化チェック
                should_send = True

            if should_send:
                for group in config_mgr.groups:
                    value = group_values.get(group.id, group.default_value)
                    force = (send_mode == 'periodic')
                    sent = mqtt_sender.send(group, value, force=force)

                    if sent or force:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        log_entry = {
                            "time": timestamp,
                            "group": group.name,
                            "sta_no3": group.sta_no3,
                            "value": value,
                            "sent": sent
                        }
                        run_state["send_log"].append(log_entry)
                        # ログ上限
                        if len(run_state["send_log"]) > 50:
                            run_state["send_log"] = run_state["send_log"][-50:]

                run_state["last_send"] = datetime.now().isoformat()

            # フレームレート制御（約10fps）
            time.sleep(0.1)

    # -----------------------------------------------------------------------
    # シャットダウン
    # -----------------------------------------------------------------------
    @app.teardown_appcontext
    def cleanup(exception=None):
        pass

    def shutdown():
        """アプリ終了時のクリーンアップ"""
        run_state["running"] = False
        mqtt_sender.stop()
        camera.stop()

    app.shutdown = shutdown

    return app


# =============================================================================
# メイン
# =============================================================================

if __name__ == "__main__":
    app = create_app()

    # カメラを先に起動
    print("Starting camera...")

    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        app.shutdown()
