#!/bin/bash
# Circle Detector - デスクトップアプリ起動スクリプト
#
# Flaskバックエンドを起動し、Chromiumをアプリモードで開く。
# 終了時にバックエンドも自動停止する。

APP_DIR="/home/sano/color_detector_app"
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

# ---------- バックエンド起動 ----------
cd "$APP_DIR"
python3 -m circle_detector.app > "$LOG_FILE" 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > "$PID_FILE"

# サーバー起動待ち（最大10秒）
for i in $(seq 1 20); do
    if curl -s -o /dev/null "$URL" 2>/dev/null; then
        break
    fi
    sleep 0.5
done

# ---------- ブラウザ起動（アプリモード）----------
open_browser &
BROWSER_PID=$!

# ---------- ブラウザ終了を待つ → バックエンド停止 ----------
wait $BROWSER_PID 2>/dev/null

kill $BACKEND_PID 2>/dev/null
rm -f "$PID_FILE"
