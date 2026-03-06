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
from .ntp_sync import NTPSync


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

    # settings.json からデバイスモード設定を同期
    try:
        import json as _json_init
        _settings_init_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "settings.json"
        )
        with open(_settings_init_path, 'r') as f:
            _init_settings = _json_init.load(f)
        if 'device_mode' in _init_settings:
            config_mgr.set_device_mode(_init_settings['device_mode'])
        if 'device_mode_confirmed' in _init_settings:
            config_mgr.set_device_mode_confirmed(_init_settings['device_mode_confirmed'])
    except Exception:
        pass

    cam_conf = config_mgr.get_camera_config()
    camera = CameraManager(
        device=cam_conf.get('device', 'usb'),
        width=cam_conf.get('width', 640),
        height=cam_conf.get('height', 480)
    )

    detector = DetectionEngine(config_mgr, config_mgr.get_blink_config())
    rule_engine = RuleEngine(config_mgr)
    mqtt_sender = MQTTSender(config_mgr)

    # NTP 同期
    ntp_conf = config_mgr.get_ntp_config()
    ntp_sync = NTPSync(
        server=ntp_conf.get('server', 'ntp.nict.jp'),
        interval_sec=ntp_conf.get('interval_sec', 3600)
    )

    # ------------------------------------------------------------------
    # 起動時の自動初期化（MQTT, ブリッジ, DB接続テスト, NTP同期）
    # ------------------------------------------------------------------
    def _startup_init():
        """バックグラウンドで起動時の接続を初期化"""
        import subprocess, time as _time

        is_child = config_mgr.get_device_mode() == 'child'
        print(f"[起動] デバイスモード: {'子機' if is_child else '親機'}")

        # 1. MQTT 接続（両モードで実行、ただし子機はMosquitto起動をスキップ）
        try:
            conf = config_mgr.get_mqtt_config()
            broker = conf.get('broker', 'localhost')
            if not is_child and broker in ('localhost', '127.0.0.1', ''):
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
                except Exception:
                    pass
            mqtt_sender.start()
            for _ in range(15):
                _time.sleep(0.2)
                if mqtt_sender.connected:
                    break
            print(f"[起動] MQTT: {'接続成功' if mqtt_sender.connected else '接続失敗'}")
        except Exception as e:
            print(f"[起動] MQTT: エラー - {e}")

        # 2. MQTT-Oracle ブリッジ起動（親機のみ）
        if not is_child:
            try:
                if not _is_bridge_running():
                    bridge_py = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "mqtt_oracle_bridge.py"
                    )
                    log_dir = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "logs"
                    )
                    os.makedirs(log_dir, exist_ok=True)
                    bridge_log = os.path.join(log_dir, "bridge.log")
                    with open(bridge_log, 'a') as log_f:
                        subprocess.Popen(
                            [sys.executable, '-u', bridge_py],
                            stdout=log_f, stderr=log_f,
                            cwd=os.path.dirname(bridge_py)
                        )
                    _time.sleep(3)
                    print(f"[起動] ブリッジ: {'稼働中' if _is_bridge_running() else '起動失敗'}")
                else:
                    print("[起動] ブリッジ: 既に稼働中")
            except Exception as e:
                print(f"[起動] ブリッジ: エラー - {e}")
        else:
            print("[起動] ブリッジ: 子機のためスキップ")

        # 3. Oracle DB 接続テスト（親機のみ）
        if not is_child:
            try:
                settings = _load_settings()
                oracle = settings.get('oracle', {})
                if oracle.get('dsn') and oracle.get('user'):
                    import oracledb
                    conn_params = {
                        'user': oracle.get('user', ''),
                        'password': oracle.get('password', ''),
                        'dsn': oracle.get('dsn', ''),
                    }
                    use_wallet = oracle.get('use_wallet', bool(oracle.get('wallet_dir', '').strip()))
                    if use_wallet:
                        wallet_dir = oracle.get('wallet_dir', '').strip()
                        if wallet_dir:
                            conn_params['config_dir'] = wallet_dir
                            conn_params['wallet_location'] = wallet_dir
                            wallet_pw = oracle.get('wallet_password', '')
                            if wallet_pw:
                                conn_params['wallet_password'] = wallet_pw
                    conn = oracledb.connect(**conn_params)
                    conn.close()
                    _oracle_test_result["success"] = True
                    _oracle_test_result["tested_at"] = datetime.now()
                    print("[起動] Oracle DB: 接続成功")
                else:
                    print("[起動] Oracle DB: 設定なし（スキップ）")
            except Exception as e:
                _oracle_test_result["success"] = False
                _oracle_test_result["tested_at"] = datetime.now()
                print(f"[起動] Oracle DB: 接続失敗 - {e}")
        else:
            print("[起動] Oracle DB: 子機のためスキップ")

        # 4. NTP 時刻同期（両モードで実行）
        try:
            if not ntp_sync.running:
                ntp_sync.start()
                config_mgr.set_ntp_config(enabled=True)
            result = ntp_sync.sync_once()
            print(f"[起動] NTP同期: オフセット {result.get('offset', 'N/A')}s")
        except Exception as e:
            print(f"[起動] NTP同期: エラー - {e}")

    def _is_bridge_running():
        """ブリッジプロセスが動作中か確認"""
        import subprocess
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'mqtt_oracle_bridge.py'],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    # バックグラウンドスレッドで起動初期化を実行
    threading.Thread(target=_startup_init, daemon=True, name="startup-init").start()

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

    # 接続テスト結果を保持
    _oracle_test_result = {"success": False, "tested_at": None}

    @app.route('/api/bridge/status', methods=['GET'])
    def get_bridge_status():
        """MQTT-Oracle ブリッジのステータスを返す"""
        import json as _json
        status_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "logs", "bridge_status.json"
        )
        bridge_data = None
        try:
            with open(status_file, 'r') as f:
                bridge_data = _json.load(f)
            # ファイルが古すぎる場合（30秒以上）はブリッジ停止とみなす
            from datetime import datetime as _dt
            updated = _dt.fromisoformat(bridge_data.get('updated_at', ''))
            age = (_dt.now() - updated).total_seconds()
            if age > 30:
                bridge_data['running'] = False
                bridge_data['oracle_connected'] = False
        except (FileNotFoundError, ValueError, KeyError):
            bridge_data = {
                "running": False,
                "oracle_connected": False,
                "received": 0,
                "inserted": 0,
                "errors": 0,
                "pending": 0
            }

        # 接続テスト結果を反映: ブリッジ未稼働でもDB接続テスト成功なら反映
        if _oracle_test_result.get("success") and _oracle_test_result.get("tested_at"):
            from datetime import datetime as _dt
            age = (_dt.now() - _oracle_test_result["tested_at"]).total_seconds()
            # テスト結果は5分間有効
            if age < 300:
                bridge_data["oracle_connected"] = True
                bridge_data["oracle_test_success"] = True

        bridge_data['child_mode'] = config_mgr.get_device_mode() == 'child'
        return jsonify(bridge_data)

    # -----------------------------------------------------------------------
    # デバイスモード API
    # -----------------------------------------------------------------------
    @app.route('/api/device_mode', methods=['GET'])
    def get_device_mode():
        return jsonify({
            "device_mode": config_mgr.get_device_mode(),
            "confirmed": config_mgr.get_device_mode_confirmed()
        })

    @app.route('/api/device_mode', methods=['PUT'])
    def set_device_mode():
        data = request.get_json()
        mode = data.get('device_mode', 'parent')
        if mode not in ('parent', 'child'):
            return jsonify({"success": False, "error": "Invalid mode"}), 400
        config_mgr.set_device_mode(mode)
        # settings.json にも保存
        settings = _load_settings()
        settings['device_mode'] = mode
        # confirmed フラグの処理
        if 'confirmed' in data:
            confirmed = bool(data['confirmed'])
            config_mgr.set_device_mode_confirmed(confirmed)
            settings['device_mode_confirmed'] = confirmed
        _save_settings(settings)
        # 再起動要求の処理
        if data.get('restart'):
            threading.Timer(0.5, lambda: os._exit(0)).start()
        return jsonify({"success": True, "device_mode": mode})

    # -----------------------------------------------------------------------
    # Oracle DB 設定 API
    # -----------------------------------------------------------------------
    def _get_settings_path():
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "settings.json"
        )

    import threading as _threading
    _settings_lock = _threading.Lock()

    def _load_settings():
        import json as _json
        try:
            with open(_get_settings_path(), 'r') as f:
                return _json.load(f)
        except (FileNotFoundError, _json.JSONDecodeError):
            return {}

    def _save_settings(settings):
        import json as _json
        import tempfile as _tempfile
        path = _get_settings_path()
        dir_path = os.path.dirname(path)
        os.makedirs(dir_path, exist_ok=True)
        with _settings_lock:
            fd, tmp = _tempfile.mkstemp(dir=dir_path, suffix='.tmp')
            try:
                with os.fdopen(fd, 'w') as f:
                    _json.dump(settings, f, indent=2, ensure_ascii=False)
                os.replace(tmp, path)
            except Exception:
                os.unlink(tmp)
                raise

    @app.route('/api/oracle', methods=['GET'])
    def get_oracle_config():
        settings = _load_settings()
        oracle = settings.get('oracle', {})
        return jsonify(oracle)

    @app.route('/api/oracle', methods=['PUT'])
    def update_oracle_config():
        data = request.get_json()
        settings = _load_settings()
        if 'oracle' not in settings:
            settings['oracle'] = {}
        for key, val in data.items():
            settings['oracle'][key] = val
        _save_settings(settings)
        return jsonify({"success": True})

    @app.route('/api/oracle/test', methods=['POST'])
    def test_oracle_connection():
        settings = _load_settings()
        oracle = settings.get('oracle', {})

        # リクエストに含まれる値で上書き（テスト用）
        data = request.get_json(silent=True) or {}
        for key, val in data.items():
            oracle[key] = val

        try:
            import oracledb
            conn_params = {
                'user': oracle.get('user', ''),
                'password': oracle.get('password', ''),
                'dsn': oracle.get('dsn', ''),
            }
            use_wallet = oracle.get('use_wallet', bool(oracle.get('wallet_dir', '').strip()))
            if use_wallet:
                wallet_dir = oracle.get('wallet_dir', '').strip()
                if wallet_dir:
                    conn_params['config_dir'] = wallet_dir
                    conn_params['wallet_location'] = wallet_dir
                    wallet_pw = oracle.get('wallet_password', '')
                    if wallet_pw:
                        conn_params['wallet_password'] = wallet_pw
            conn = oracledb.connect(**conn_params)
            cursor = conn.cursor()
            table = oracle.get('table_name', 'HF1RCM01')
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            _oracle_test_result["success"] = True
            _oracle_test_result["tested_at"] = datetime.now()
            return jsonify({
                "success": True,
                "message": f"接続成功 (テーブル {table}: {count}件)"
            })
        except ImportError:
            _oracle_test_result["success"] = False
            _oracle_test_result["tested_at"] = datetime.now()
            return jsonify({"success": False, "message": "oracledb モジュール未インストール"})
        except Exception as e:
            _oracle_test_result["success"] = False
            _oracle_test_result["tested_at"] = datetime.now()
            return jsonify({"success": False, "message": str(e)})

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
        new_port = conf.get('port', 1883)
        new_topic = conf.get('topic', 'equipment/status')
        broker_changed = (broker != mqtt_sender.broker or new_port != mqtt_sender.port)
        mqtt_sender.base_topic = new_topic
        mqtt_sender.enabled = conf.get('enabled', True)
        if broker_changed:
            # ブローカー設定が変わった場合のみ再接続
            mqtt_sender.stop()
            mqtt_sender.broker = broker
            mqtt_sender.port = new_port
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

    # -----------------------------------------------------------------------
    # NTP API
    # -----------------------------------------------------------------------
    @app.route('/api/ntp', methods=['GET'])
    def get_ntp():
        return jsonify(ntp_sync.get_status())

    @app.route('/api/ntp', methods=['PUT'])
    def update_ntp():
        data = request.get_json()
        if 'server' in data:
            ntp_sync.update_config(server=data['server'])
        if 'interval_sec' in data:
            ntp_sync.update_config(interval_sec=int(data['interval_sec']))
        # 設定を保存
        config_mgr.set_ntp_config(
            server=ntp_sync.server,
            interval_sec=ntp_sync.interval_sec,
            enabled=ntp_sync.running
        )
        return jsonify({"success": True})

    @app.route('/api/ntp/start', methods=['POST'])
    def ntp_start():
        ntp_sync.start()
        config_mgr.set_ntp_config(enabled=True)
        return jsonify({"success": True})

    @app.route('/api/ntp/stop', methods=['POST'])
    def ntp_stop():
        ntp_sync.stop()
        config_mgr.set_ntp_config(enabled=False)
        return jsonify({"success": True})

    @app.route('/api/ntp/sync', methods=['POST'])
    def ntp_sync_now():
        result = ntp_sync.sync_once()
        return jsonify(result)

    @app.route('/api/detection', methods=['PUT'])
    def update_detection():
        data = request.get_json()
        config_mgr.set_detection_config(**data)
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
                blinking=c.get('blinking', False),
                blink_interval_sec=float(c.get('blink_interval_sec', 0)),
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
                    blinking=c.get('blinking', False),
                    blink_interval_sec=float(c.get('blink_interval_sec', 0)),
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

        # MQTT開始（接続完了を待つ）
        mqtt_sender.start()
        for _ in range(15):
            time.sleep(0.2)
            if mqtt_sender.connected:
                break
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

            # 送信（設定を毎回読み取り、実行中の切り替えに対応）
            detection_conf = config_mgr.get_detection_config()
            send_mode = detection_conf.get('send_mode', 'on_change')
            send_interval = detection_conf.get('send_interval_sec', 1)

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
                    result = mqtt_sender.send(group, value, force=force)

                    # skipped = 変化なし → ログに記録しない
                    if result != 'skipped':
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        log_entry = {
                            "time": timestamp,
                            "group": group.name,
                            "sta_no3": group.sta_no3,
                            "value": value,
                            "sent": result == 'sent',
                            "status": result  # 'sent', 'failed', 'queued'
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
        ntp_sync.stop()
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
