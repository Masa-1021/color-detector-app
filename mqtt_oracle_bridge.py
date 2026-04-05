#!/usr/bin/env python3
"""
MQTT-Oracle ブリッジサービス

MQTTトピックを購読し、受信したメッセージをOracleに保存する常駐サービス。
設定は config/settings.json から読み込み。

使用方法:
    python3 mqtt_oracle_bridge.py

停止:
    Ctrl+C
"""

import json
import os
import sys
import signal
import time
import threading
from datetime import datetime

import paho.mqtt.client as mqtt

# 同じディレクトリのモジュールをインポート
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from equipment_status import load_equipment_config, EquipmentConfig
from message_queue import FileQueue

# グローバル変数
oracle_connection = None
equipment_config = None
running = True
oracle_queue = None  # Oracle送信用ファイルキュー
retry_thread = None  # バックグラウンド再送スレッド
stats = {
    "received": 0,
    "inserted": 0,
    "skipped": 0,  # 重複スキップ
    "queued": 0,   # キューに保存された数
    "queue_sent": 0,  # キューから再送された数
    "errors": 0,
    "last_message": None
}


def load_config():
    """設定ファイルを読み込み"""
    global equipment_config

    config_file = os.path.join(os.path.dirname(__file__), "config", "settings.json")

    if os.path.exists(config_file):
        try:
            equipment_config = load_equipment_config(config_file)
            print(f"設定ファイル読み込み: {config_file}")
            return True
        except Exception as e:
            print(f"設定ファイルエラー: {e}")
            return False
    else:
        print(f"設定ファイルが見つかりません: {config_file}")
        return False


def init_oracle():
    """Oracle接続を初期化（Thinモード）"""
    global oracle_connection

    if not equipment_config.oracle.enabled:
        print("Oracle: 無効（設定で有効化してください）")
        return False

    try:
        import oracledb
        conn_params = {
            'user': equipment_config.oracle.user,
            'password': equipment_config.oracle.password,
            'dsn': equipment_config.oracle.dsn,
        }
        use_wallet = getattr(equipment_config.oracle, 'use_wallet',
                             bool(getattr(equipment_config.oracle, 'wallet_dir', '').strip()))
        if use_wallet:
            wallet_dir = getattr(equipment_config.oracle, 'wallet_dir', '').strip()
            if wallet_dir:
                conn_params['config_dir'] = wallet_dir
                conn_params['wallet_location'] = wallet_dir
                wallet_pw = getattr(equipment_config.oracle, 'wallet_password', '')
                if wallet_pw:
                    conn_params['wallet_password'] = wallet_pw
        oracle_connection = oracledb.connect(**conn_params)
        print(f"Oracle: 接続成功 ({equipment_config.oracle.dsn})")
        return True
    except ImportError:
        print("Oracle: oracledbモジュールがインストールされていません")
        return False
    except Exception as e:
        print(f"Oracle: 接続エラー - {e}")
        return False


def init_queue():
    """ファイルキューを初期化"""
    global oracle_queue

    queue_dir = os.path.join(os.path.dirname(__file__), "queue")
    queue_file = os.path.join(queue_dir, "pending_oracle.jsonl")

    oracle_queue = FileQueue(queue_file, max_retries=10000)

    pending = oracle_queue.get_count()
    if pending > 0:
        print(f"Queue: {pending} messages pending from previous session")

    return True


def add_to_queue(data: dict):
    """キューにデータを追加"""
    global stats
    if oracle_queue:
        oracle_queue.add(data)
        stats["queued"] += 1


def process_queue_one() -> bool:
    """キューから1件処理。成功時True、失敗/空ならFalse"""
    global stats

    if not oracle_queue or not oracle_connection:
        return False

    pending = oracle_queue.get_pending(limit=1)
    if not pending:
        return False

    msg = pending[0]
    data = msg.data

    success, skipped = insert_to_oracle(data)

    if success or skipped:
        oracle_queue.remove(msg.id)
        if success:
            stats["queue_sent"] += 1
        return True
    else:
        oracle_queue.increment_retry(msg.id)
        return False


def retry_loop():
    """バックグラウンドでキューを定期的に処理（Oracle再接続対応）"""
    global running

    retry_interval = 5.0  # 秒
    reconnect_interval = 30.0  # Oracle再接続の試行間隔（秒）
    last_reconnect_attempt = 0.0

    while running:
        try:
            # Oracle未接続なら定期的に再接続を試みる
            if oracle_queue and not oracle_connection:
                now = time.time()
                if now - last_reconnect_attempt >= reconnect_interval:
                    last_reconnect_attempt = now
                    print("[Retry] Oracle未接続 → 再接続を試みます...")
                    if init_oracle():
                        print("[Retry] Oracle再接続成功")
                    else:
                        print("[Retry] Oracle再接続失敗（次回再試行まで30秒）")

            # Oracle接続中ならキューを処理
            if oracle_queue and oracle_connection:
                pending_count = oracle_queue.get_count()
                if pending_count > 0:
                    success = process_queue_one()
                    if success:
                        remaining = oracle_queue.get_count()
                        print(f"[Queue] Retry sent to Oracle (remaining: {remaining})")
        except Exception as e:
            pass

        time.sleep(retry_interval)


def start_retry_thread():
    """再送スレッドを開始"""
    global retry_thread

    retry_thread = threading.Thread(target=retry_loop, daemon=True)
    retry_thread.start()
    print("Queue: Background retry thread started")


def insert_to_oracle(data: dict) -> tuple:
    """Oracleにデータを挿入

    Returns:
        (success: bool, skipped: bool) - 成功/失敗, 重複スキップかどうか
    """
    global oracle_connection

    if not oracle_connection:
        return False, False

    try:
        cursor = oracle_connection.cursor()
        sql = f"""
            INSERT INTO {equipment_config.oracle.table_name}
            (MK_DATE, STA_NO1, STA_NO2, STA_NO3, T1_STATUS)
            VALUES (:1, :2, :3, :4, :5)
        """
        cursor.execute(sql, [
            data.get("mk_date", datetime.now().strftime("%Y%m%d%H%M%S")),
            data.get("sta_no1", ""),
            data.get("sta_no2", ""),
            data.get("sta_no3", ""),
            data.get("t1_status", 0)
        ])
        oracle_connection.commit()
        cursor.close()
        return True, False
    except Exception as e:
        error_str = str(e)
        # ORA-00001: 一意制約違反（重複キー）
        if "ORA-00001" in error_str:
            return False, True  # 重複スキップ

        print(f"Oracle INSERT エラー: {e}")
        # 接続が切れた場合は再接続を試みる
        try:
            oracle_connection.ping()
        except:
            print("Oracle: 再接続を試みます...")
            init_oracle()
        return False, False


def on_connect(client, userdata, flags, reason_code, properties=None):
    """MQTT接続時のコールバック"""
    if reason_code == 0 or (hasattr(reason_code, 'is_failure') and not reason_code.is_failure):
        topic = f"{equipment_config.mqtt.topic}/#"
        client.subscribe(topic, qos=2)
        print(f"MQTT: 接続成功、トピック購読: {topic}")
    else:
        print(f"MQTT: 接続失敗 (rc={reason_code})")


def on_disconnect(client, userdata, flags, rc, properties=None):
    """MQTT切断時のコールバック"""
    print(f"MQTT: 切断されました (rc={rc})")
    if running:
        print("MQTT: 再接続を試みます...")


def on_message(client, userdata, msg):
    """MQTTメッセージ受信時のコールバック"""
    global stats

    stats["received"] += 1

    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)

        sta_no3 = data.get("sta_no3", "?")
        status = data.get("t1_status", "?")
        stats["last_message"] = datetime.now().strftime("%H:%M:%S")

        # Oracle に挿入を試みる（リアルタイム）
        if oracle_connection:
            success, skipped = insert_to_oracle(data)

            if success:
                stats["inserted"] += 1
                print(f"[{stats['last_message']}] {sta_no3}: status={status} → Oracle保存完了")
            elif skipped:
                stats["skipped"] += 1
                print(f"[{stats['last_message']}] {sta_no3}: status={status} → スキップ(同一秒内の重複)")
            else:
                # 挿入失敗 → キューに保存
                add_to_queue(data)
                print(f"[{stats['last_message']}] {sta_no3}: status={status} → キューに保存(Oracle接続エラー)")
        else:
            # Oracle未接続 → キューに保存
            add_to_queue(data)
            print(f"[{stats['last_message']}] {sta_no3}: status={status} → キューに保存(Oracle未接続)")

    except json.JSONDecodeError as e:
        print(f"JSONパースエラー: {e}")
        stats["errors"] += 1
    except Exception as e:
        print(f"メッセージ処理エラー: {e}")
        stats["errors"] += 1


def signal_handler(signum, frame):
    """シグナルハンドラ（Ctrl+C対応）"""
    global running
    print("\n終了シグナルを受信しました...")
    running = False


def write_status_file():
    """ステータスをJSONファイルに書き出す（UIからの参照用）"""
    status_file = os.path.join(os.path.dirname(__file__), "logs", "bridge_status.json")
    pending = oracle_queue.get_count() if oracle_queue else 0
    oracle_ok = False
    if oracle_connection:
        try:
            oracle_connection.ping()
            oracle_ok = True
        except Exception:
            oracle_ok = False

    status_data = {
        "running": running,
        "oracle_connected": oracle_ok,
        "mqtt_connected": True,  # ブリッジ起動中なら接続済み
        "received": stats["received"],
        "inserted": stats["inserted"],
        "skipped": stats["skipped"],
        "errors": stats["errors"],
        "queued": stats["queued"],
        "queue_sent": stats["queue_sent"],
        "pending": pending,
        "last_message": stats["last_message"],
        "updated_at": datetime.now().isoformat()
    }
    try:
        with open(status_file, 'w') as f:
            json.dump(status_data, f)
    except Exception:
        pass


def print_status():
    """現在のステータスを表示"""
    pending = oracle_queue.get_count() if oracle_queue else 0

    print(f"\n--- ブリッジ統計 ---")
    print(f"受信: {stats['received']} | 保存: {stats['inserted']} | スキップ: {stats['skipped']} | エラー: {stats['errors']}")
    print(f"キュー保存: {stats['queued']} | キュー再送: {stats['queue_sent']} | キュー残: {pending}")
    print(f"最終メッセージ: {stats['last_message'] or 'なし'}")
    print(f"-------------------\n")


def main():
    global running

    print("=" * 50)
    print("MQTT-Oracle ブリッジサービス")
    print("=" * 50)

    # シグナルハンドラ設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 設定読み込み
    if not load_config():
        sys.exit(1)

    # ファイルキュー初期化
    init_queue()

    # Oracle接続
    if not init_oracle():
        print("警告: Oracle接続なしで起動します（メッセージはキューに保存されます）")

    # バックグラウンド再送スレッド開始
    start_retry_thread()

    # MQTTクライアント設定
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    # MQTT認証（設定されている場合）
    if equipment_config.mqtt.username:
        client.username_pw_set(
            equipment_config.mqtt.username,
            equipment_config.mqtt.password
        )

    # MQTT接続
    try:
        print(f"MQTT: {equipment_config.mqtt.broker}:{equipment_config.mqtt.port} に接続中...")
        client.connect(
            equipment_config.mqtt.broker,
            equipment_config.mqtt.port,
            keepalive=60
        )
    except Exception as e:
        print(f"MQTT接続エラー: {e}")
        sys.exit(1)

    print("=" * 50)
    print("ブリッジ稼働中... (Ctrl+C で停止)")
    print("=" * 50)

    # メインループ
    client.loop_start()

    last_status_time = time.time()
    last_file_time = time.time()
    status_interval = 60  # 60秒ごとにステータス表示
    file_interval = 5     # 5秒ごとにステータスファイル更新

    try:
        while running:
            time.sleep(1)

            # ステータスファイル更新
            if time.time() - last_file_time >= file_interval:
                write_status_file()
                last_file_time = time.time()

            # 定期的にステータス表示
            if time.time() - last_status_time >= status_interval:
                print_status()
                last_status_time = time.time()

    except KeyboardInterrupt:
        pass

    # 終了処理
    print("終了処理中...")
    running = False  # 再送スレッド停止
    write_status_file()

    client.loop_stop()
    client.disconnect()

    if oracle_connection:
        try:
            oracle_connection.close()
            print("Oracle: 切断しました")
        except:
            pass

    print_status()

    pending = oracle_queue.get_count() if oracle_queue else 0
    if pending > 0:
        print(f"Note: {pending} messages saved in queue (will be sent on next startup)")

    print("ブリッジサービスを終了しました")


if __name__ == "__main__":
    main()
