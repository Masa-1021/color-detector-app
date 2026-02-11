#!/bin/bash
# Circle Detector 起動スクリプト
#
# Oracle保存を有効にするには、別ターミナルでブリッジを起動:
#   ./run_bridge.sh

APP_DIR="/home/sano/color_detector_app"
LOG_DIR="$APP_DIR/logs"
STARTUP_LOG="$LOG_DIR/startup.log"

# ログディレクトリ作成
mkdir -p "$LOG_DIR"

# 起動ログ
echo "=== $(date) ===" >> "$STARTUP_LOG"

# 作業ディレクトリに移動
cd "$APP_DIR"

# ブリッジ状態確認
if pgrep -f "mqtt_oracle_bridge.py" > /dev/null; then
    echo "MQTT-Oracleブリッジ: 起動中 (DB保存有効)" | tee -a "$STARTUP_LOG"
else
    echo "MQTT-Oracleブリッジ: 停止中 (DB保存無効)" | tee -a "$STARTUP_LOG"
fi

# Circle Detector起動
echo "Starting Circle Detector..." | tee -a "$STARTUP_LOG"
python3 -m circle_detector.app "$@" 2>&1 | tee -a "$STARTUP_LOG"
