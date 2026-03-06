#!/bin/bash
# MQTT-Oracle ブリッジサービス 起動スクリプト

APP_DIR="/home/pi/Apps/color-detector-app"
ORACLE_ENV="/home/pi/Apps/color-detector-app/oracle_env"
LOG_FILE="$APP_DIR/logs/bridge.log"

cd "$APP_DIR"

# ログディレクトリ作成
mkdir -p "$APP_DIR/logs"

# 既存プロセスを確認
if pgrep -f "mqtt_oracle_bridge.py" > /dev/null; then
    echo "ブリッジは既に起動しています"
    echo "停止するには: pkill -f mqtt_oracle_bridge.py"
    exit 0
fi

# Oracle環境で起動
if [ -f "$ORACLE_ENV/bin/python" ]; then
    echo "MQTT-Oracle ブリッジを起動します..."
    echo "ログ: $LOG_FILE"
    "$ORACLE_ENV/bin/python" mqtt_oracle_bridge.py 2>&1 | tee -a "$LOG_FILE"
else
    echo "Error: Oracle環境が見つかりません: $ORACLE_ENV"
    exit 1
fi
