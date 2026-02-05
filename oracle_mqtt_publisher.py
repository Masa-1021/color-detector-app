#!/usr/bin/env python3
"""
Oracle-MQTT パブリッシャーサービス

Oracleからデータを定期的に取得し、MQTTトピックに配信する常駐サービス。
設定は config/settings.json から読み込み。

使用方法:
    python3 oracle_mqtt_publisher.py

停止:
    Ctrl+C
"""

import json
import os
import sys
import signal
import time
from datetime import datetime
from typing import Dict, List, Optional

import paho.mqtt.client as mqtt

# 同じディレクトリのモジュールをインポート
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from equipment_status import load_equipment_config, EquipmentConfig

# グローバル変数
oracle_connection = None
mqtt_client = None
equipment_config = None
running = True

stats = {
    "queries": 0,
    "published": 0,
    "errors": 0,
    "last_publish": None
}


def load_config() -> bool:
    """設定ファイルを読み込み"""
    global equipment_config

    config_file = os.path.join(os.path.dirname(__file__), "config", "settings.json")

    if os.path.exists(config_file):
        try:
            equipment_config = load_equipment_config(config_file)

            # oracle_publisher設定を読み込み
            with open(config_file, 'r', encoding='utf-8') as f:
                raw_config = json.load(f)

            equipment_config.publisher = raw_config.get("oracle_publisher", {
                "enabled": False,
                "poll_interval_sec": 10,
                "topic": "oracle/equipment",
                "query_mode": "latest",
                "sta_no3_filter": []
            })

            print(f"設定ファイル読み込み: {config_file}")
            return True
        except Exception as e:
            print(f"設定ファイルエラー: {e}")
            return False
    else:
        print(f"設定ファイルが見つかりません: {config_file}")
        return False


def init_oracle() -> bool:
    """Oracle接続を初期化"""
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


def init_mqtt() -> bool:
    """MQTTクライアントを初期化"""
    global mqtt_client

    mqtt_client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="oracle_publisher"
    )

    if equipment_config.mqtt.username:
        mqtt_client.username_pw_set(
            equipment_config.mqtt.username,
            equipment_config.mqtt.password
        )

    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_disconnect = on_mqtt_disconnect

    try:
        print(f"MQTT: {equipment_config.mqtt.broker}:{equipment_config.mqtt.port} に接続中...")
        mqtt_client.connect(
            equipment_config.mqtt.broker,
            equipment_config.mqtt.port,
            keepalive=60
        )
        mqtt_client.loop_start()
        return True
    except Exception as e:
        print(f"MQTT接続エラー: {e}")
        return False


def on_mqtt_connect(client, userdata, flags, reason_code, properties=None):
    """MQTT接続時のコールバック"""
    if reason_code == 0 or (hasattr(reason_code, 'is_failure') and not reason_code.is_failure):
        print(f"MQTT: 接続成功")
    else:
        print(f"MQTT: 接続失敗 (rc={reason_code})")


def on_mqtt_disconnect(client, userdata, flags, rc, properties=None):
    """MQTT切断時のコールバック"""
    print(f"MQTT: 切断されました (rc={rc})")


def query_latest_status() -> List[Dict]:
    """最新の設備ステータスを取得"""
    global oracle_connection

    if not oracle_connection:
        return []

    try:
        cursor = oracle_connection.cursor()

        # 各設備の最新レコードを取得
        sql = f"""
            SELECT MK_DATE, STA_NO1, STA_NO2, STA_NO3, T1_STATUS
            FROM (
                SELECT MK_DATE, STA_NO1, STA_NO2, STA_NO3, T1_STATUS,
                       ROW_NUMBER() OVER (PARTITION BY STA_NO3 ORDER BY MK_DATE DESC) as rn
                FROM {equipment_config.oracle.table_name}
            )
            WHERE rn = 1
        """

        # フィルタがある場合
        sta_no3_filter = equipment_config.publisher.get("sta_no3_filter", [])
        if sta_no3_filter:
            placeholders = ", ".join([f":f{i}" for i in range(len(sta_no3_filter))])
            sql = f"""
                SELECT MK_DATE, STA_NO1, STA_NO2, STA_NO3, T1_STATUS
                FROM (
                    SELECT MK_DATE, STA_NO1, STA_NO2, STA_NO3, T1_STATUS,
                           ROW_NUMBER() OVER (PARTITION BY STA_NO3 ORDER BY MK_DATE DESC) as rn
                    FROM {equipment_config.oracle.table_name}
                    WHERE STA_NO3 IN ({placeholders})
                )
                WHERE rn = 1
            """
            bind_vars = {f"f{i}": v for i, v in enumerate(sta_no3_filter)}
            cursor.execute(sql, bind_vars)
        else:
            cursor.execute(sql)

        results = []
        for row in cursor.fetchall():
            results.append({
                "mk_date": row[0],
                "sta_no1": row[1],
                "sta_no2": row[2],
                "sta_no3": row[3],
                "t1_status": row[4]
            })

        cursor.close()
        stats["queries"] += 1
        return results

    except Exception as e:
        print(f"Oracle クエリエラー: {e}")
        stats["errors"] += 1

        # 接続切れの場合は再接続
        try:
            oracle_connection.ping()
        except:
            print("Oracle: 再接続を試みます...")
            init_oracle()

        return []


def query_recent_changes(since_minutes: int = 5) -> List[Dict]:
    """指定時間以内の変更を取得"""
    global oracle_connection

    if not oracle_connection:
        return []

    try:
        cursor = oracle_connection.cursor()

        # N分以内のレコードを取得
        sql = f"""
            SELECT MK_DATE, STA_NO1, STA_NO2, STA_NO3, T1_STATUS
            FROM {equipment_config.oracle.table_name}
            WHERE TO_DATE(MK_DATE, 'YYYYMMDDHH24MISS') > SYSDATE - INTERVAL '{since_minutes}' MINUTE
            ORDER BY MK_DATE DESC
        """

        cursor.execute(sql)

        results = []
        for row in cursor.fetchall():
            results.append({
                "mk_date": row[0],
                "sta_no1": row[1],
                "sta_no2": row[2],
                "sta_no3": row[3],
                "t1_status": row[4]
            })

        cursor.close()
        stats["queries"] += 1
        return results

    except Exception as e:
        print(f"Oracle クエリエラー: {e}")
        stats["errors"] += 1
        return []


def publish_to_mqtt(data: List[Dict]):
    """データをMQTTに配信"""
    global mqtt_client

    if not mqtt_client or not data:
        return

    topic_base = equipment_config.publisher.get("topic", "oracle/equipment")

    for record in data:
        try:
            # 設備ごとのトピックに配信
            sta_no3 = record.get("sta_no3", "unknown")
            topic = f"{topic_base}/{sta_no3}"

            payload = json.dumps(record, ensure_ascii=False)
            result = mqtt_client.publish(topic, payload, qos=1)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                stats["published"] += 1
                stats["last_publish"] = datetime.now().strftime("%H:%M:%S")
            else:
                stats["errors"] += 1
                print(f"MQTT配信失敗: {sta_no3} (rc={result.rc})")

        except Exception as e:
            print(f"MQTT配信エラー: {e}")
            stats["errors"] += 1


def signal_handler(signum, frame):
    """シグナルハンドラ"""
    global running
    print("\n終了シグナルを受信しました...")
    running = False


def print_status():
    """ステータス表示"""
    print(f"\n--- パブリッシャー統計 ---")
    print(f"クエリ: {stats['queries']} | 配信: {stats['published']} | エラー: {stats['errors']}")
    print(f"最終配信: {stats['last_publish'] or 'なし'}")
    print(f"-------------------------\n")


def main():
    global running

    print("=" * 50)
    print("Oracle-MQTT パブリッシャーサービス")
    print("=" * 50)

    # シグナルハンドラ設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 設定読み込み
    if not load_config():
        sys.exit(1)

    # パブリッシャー有効確認
    if not equipment_config.publisher.get("enabled", False):
        print("エラー: oracle_publisher.enabled が false です")
        print("config/settings.json で有効化してください")
        sys.exit(1)

    # Oracle接続
    if not init_oracle():
        print("エラー: Oracle接続に失敗しました")
        sys.exit(1)

    # MQTT接続
    if not init_mqtt():
        print("エラー: MQTT接続に失敗しました")
        sys.exit(1)

    poll_interval = equipment_config.publisher.get("poll_interval_sec", 10)
    query_mode = equipment_config.publisher.get("query_mode", "latest")
    topic = equipment_config.publisher.get("topic", "oracle/equipment")

    print("=" * 50)
    print(f"配信トピック: {topic}/<STA_NO3>")
    print(f"ポーリング間隔: {poll_interval}秒")
    print(f"クエリモード: {query_mode}")
    print("パブリッシャー稼働中... (Ctrl+C で停止)")
    print("=" * 50)

    last_poll = 0
    last_status_time = time.time()
    status_interval = 60

    try:
        while running:
            now = time.time()

            # ポーリング実行
            if now - last_poll >= poll_interval:
                if query_mode == "latest":
                    data = query_latest_status()
                elif query_mode == "recent":
                    data = query_recent_changes(since_minutes=5)
                else:
                    data = query_latest_status()

                if data:
                    publish_to_mqtt(data)
                    for record in data:
                        print(f"[{stats['last_publish']}] {record['sta_no3']}: status={record['t1_status']}")

                last_poll = now

            # 定期ステータス表示
            if now - last_status_time >= status_interval:
                print_status()
                last_status_time = now

            time.sleep(1)

    except KeyboardInterrupt:
        pass

    # 終了処理
    print("終了処理中...")

    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("MQTT: 切断しました")

    if oracle_connection:
        try:
            oracle_connection.close()
            print("Oracle: 切断しました")
        except:
            pass

    print_status()
    print("パブリッシャーサービスを終了しました")


if __name__ == "__main__":
    main()
