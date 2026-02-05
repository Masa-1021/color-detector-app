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
from datetime import datetime

import paho.mqtt.client as mqtt

# 同じディレクトリのモジュールをインポート
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from equipment_status import load_equipment_config, EquipmentConfig

# グローバル変数
oracle_connection = None
equipment_config = None
running = True
stats = {
    "received": 0,
    "inserted": 0,
    "skipped": 0,  # 重複スキップ
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
        oracle_connection = oracledb.connect(
            user=equipment_config.oracle.user,
            password=equipment_config.oracle.password,
            dsn=equipment_config.oracle.dsn,
            config_dir=equipment_config.oracle.wallet_dir,
            wallet_location=equipment_config.oracle.wallet_dir,
            wallet_password=equipment_config.oracle.wallet_password
        )
        print(f"Oracle: 接続成功 ({equipment_config.oracle.dsn})")
        return True
    except ImportError:
        print("Oracle: oracledbモジュールがインストールされていません")
        return False
    except Exception as e:
        print(f"Oracle: 接続エラー - {e}")
        return False


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
        client.subscribe(topic)
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

        # Oracle に挿入
        success, skipped = insert_to_oracle(data)
        stats["last_message"] = datetime.now().strftime("%H:%M:%S")
        sta_no3 = data.get("sta_no3", "?")
        status = data.get("t1_status", "?")

        if success:
            stats["inserted"] += 1
            print(f"[{stats['last_message']}] {sta_no3}: status={status} → Oracle保存完了")
        elif skipped:
            stats["skipped"] += 1
            print(f"[{stats['last_message']}] {sta_no3}: status={status} → スキップ(同一秒内の重複)")
        else:
            stats["errors"] += 1

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


def print_status():
    """現在のステータスを表示"""
    print(f"\n--- ブリッジ統計 ---")
    print(f"受信: {stats['received']} | 保存: {stats['inserted']} | スキップ: {stats['skipped']} | エラー: {stats['errors']}")
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

    # Oracle接続
    if not init_oracle():
        print("警告: Oracle接続なしで起動します（メッセージは破棄されます）")

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
    status_interval = 60  # 60秒ごとにステータス表示

    try:
        while running:
            time.sleep(1)

            # 定期的にステータス表示
            if time.time() - last_status_time >= status_interval:
                print_status()
                last_status_time = time.time()

    except KeyboardInterrupt:
        pass

    # 終了処理
    print("終了処理中...")
    client.loop_stop()
    client.disconnect()

    if oracle_connection:
        try:
            oracle_connection.close()
            print("Oracle: 切断しました")
        except:
            pass

    print_status()
    print("ブリッジサービスを終了しました")


if __name__ == "__main__":
    main()
