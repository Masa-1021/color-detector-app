#!/bin/bash
# Circle Detector - デスクトップアプリ起動スクリプト
#
# Flaskバックエンドを起動し、Chromiumをアプリモードで開く。
# 終了時にバックエンドも自動停止する。

APP_DIR="/home/pi/Apps/color-detector-app"
LOG_DIR="$APP_DIR/logs"
LOG_FILE="$LOG_DIR/app.log"
URL="http://localhost:5000"
PID_FILE="$LOG_DIR/app.pid"

mkdir -p "$LOG_DIR"

# ---------- ブラウザ検出 ----------
BROWSER=""
for cmd in chromium chromium-browser firefox; do
    if command -v "$cmd" &>/dev/null; then
        BROWSER="$cmd"
        break
    fi
done

if [ -z "$BROWSER" ]; then
    echo "ブラウザが見つかりません" >&2
    exit 1
fi

open_browser() {
    if [[ "$BROWSER" == chromium* ]]; then
        "$BROWSER" --app="$URL" --window-size=1280,800 2>/dev/null
    else
        "$BROWSER" "$URL" 2>/dev/null
    fi
}

# ---------- 既に起動中か確認 ----------
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    # バックエンド起動済み → ブラウザだけ開く
    open_browser &
    exit 0
fi

# ---------- バックエンド起動（再起動ループ）----------
cd "$APP_DIR" || exit 1
(while true; do
    # ポート5000が既に使用中なら既存プロセスを停止
    EXISTING_PID=$(lsof -ti :5000 2>/dev/null)
    if [ -n "$EXISTING_PID" ]; then
        echo "[$(date)] ポート5000使用中 (PID: $EXISTING_PID) → 停止" >> "$LOG_FILE"
        kill "$EXISTING_PID" 2>/dev/null
        sleep 2
    fi
    python3 -m circle_detector.app >> "$LOG_FILE" 2>&1
    EXIT_CODE=$?
    echo "[$(date)] アプリ終了 (code=$EXIT_CODE)、再起動..." >> "$LOG_FILE"
    sleep 1
done) &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PID_FILE"

# ---------- デバイスモード判定 ----------
DEVICE_MODE=$(python3 -c "import json; print(json.load(open('config/settings.json')).get('device_mode','parent'))" 2>/dev/null || echo "parent")

# ---------- MQTT-Oracle ブリッジ起動（親機のみ）----------
BRIDGE_PID=""
if [ "$DEVICE_MODE" = "child" ]; then
    echo "子機モード: ブリッジスキップ"
elif ! pgrep -f "mqtt_oracle_bridge.py" > /dev/null; then
    python3 -u mqtt_oracle_bridge.py >> "$LOG_DIR/bridge.log" 2>&1 &
    BRIDGE_PID=$!
fi

# サーバー起動待ち（最大10秒）
for _ in $(seq 1 20); do
    if curl -s -o /dev/null "$URL" 2>/dev/null; then
        break
    fi
    sleep 0.5
done

# ---------- ブラウザ起動（アプリモード）----------
open_browser &
BROWSER_PID=$!

# ---------- ブラウザ終了を待つ → バックエンド停止 ----------
wait "$BROWSER_PID" 2>/dev/null

kill -- -$BACKEND_PID 2>/dev/null || kill $BACKEND_PID 2>/dev/null
pkill -P $BACKEND_PID 2>/dev/null
[ -n "$BRIDGE_PID" ] && kill "$BRIDGE_PID" 2>/dev/null
rm -f "$PID_FILE"
