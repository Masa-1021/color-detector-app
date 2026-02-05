#!/bin/bash
# Oracle-MQTT パブリッシャー起動スクリプト
#
# Oracleからデータを取得してMQTTに配信するサービスを起動します。
# 使用前に config/settings.json で oracle_publisher.enabled を true に設定してください。

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 仮想環境があれば有効化
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "Oracle-MQTT パブリッシャーを起動します..."
python3 oracle_mqtt_publisher.py
