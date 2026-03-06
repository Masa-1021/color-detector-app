#!/bin/bash
# Circle Detector 起動スクリプト（ブリッジ自動起動付き）

APP_DIR="/home/pi/Apps/color-detector-app"
LOG_DIR="$APP_DIR/logs"
STARTUP_LOG="$LOG_DIR/startup.log"

# ログディレクトリ作成
mkdir -p "$LOG_DIR"

# 起動ログ
echo "=== $(date) ===" >> "$STARTUP_LOG"

# 作業ディレクトリに移動
cd "$APP_DIR" || exit 1

# デバイスモード判定
DEVICE_MODE=$(python3 -c "import json; print(json.load(open('config/settings.json')).get('device_mode','parent'))" 2>/dev/null || echo "parent")
echo "デバイスモード: $DEVICE_MODE" | tee -a "$STARTUP_LOG"

# MQTT-Oracle ブリッジ自動起動（親機のみ）
BRIDGE_PID=""
if [ "$DEVICE_MODE" = "child" ]; then
    echo "MQTT-Oracleブリッジ: 子機のためスキップ" | tee -a "$STARTUP_LOG"
elif pgrep -f "mqtt_oracle_bridge.py" > /dev/null; then
    echo "MQTT-Oracleブリッジ: 既に起動中" | tee -a "$STARTUP_LOG"
else
    echo "MQTT-Oracleブリッジを起動中..." | tee -a "$STARTUP_LOG"
    python3 -u mqtt_oracle_bridge.py >> "$LOG_DIR/bridge.log" 2>&1 &
    BRIDGE_PID=$!
    echo "MQTT-Oracleブリッジ: 起動 (PID: $BRIDGE_PID)" | tee -a "$STARTUP_LOG"
fi

# Circle Detector起動（再起動ループ）
echo "Starting Circle Detector..." | tee -a "$STARTUP_LOG"

cleanup() {
    [ -n "$LOOP_PID" ] && kill -- -$LOOP_PID 2>/dev/null
    [ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM

(while true; do
    # ポート5000が既に使用中なら既存プロセスを停止
    EXISTING_PID=$(lsof -ti :5000 2>/dev/null)
    if [ -n "$EXISTING_PID" ]; then
        echo "[$(date)] ポート5000使用中 (PID: $EXISTING_PID) → 停止" | tee -a "$STARTUP_LOG"
        kill "$EXISTING_PID" 2>/dev/null
        sleep 2
    fi
    python3 -m circle_detector.app "$@" 2>&1 | tee -a "$STARTUP_LOG"
    EXIT_CODE=$?
    echo "[$(date)] アプリ終了 (code=$EXIT_CODE)、再起動..." | tee -a "$STARTUP_LOG"
    sleep 1
done) &
LOOP_PID=$!

wait "$LOOP_PID"
