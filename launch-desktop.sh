#!/bin/bash
# Circle Detector - デスクトップアプリ起動スクリプト
#
# docker compose でバックエンドを起動し、Chromiumをアプリモードで開く。
# ブラウザ終了時にコンテナも自動停止する。

APP_DIR="/home/pi/Apps/color-detector-app"
URL="http://localhost:5000"

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

# ---------- コンテナ起動 ----------
cd "$APP_DIR" || exit 1

# 既にコンテナが起動中ならブラウザだけ開く
if docker compose ps --status running 2>/dev/null | grep -q detector; then
    open_browser &
    exit 0
fi

docker compose up -d

# サーバー起動待ち（最大15秒）
for _ in $(seq 1 30); do
    if curl -s -o /dev/null "$URL" 2>/dev/null; then
        break
    fi
    sleep 0.5
done

# ---------- ブラウザ起動（アプリモード）----------
open_browser &
BROWSER_PID=$!

# ---------- ブラウザ終了を待つ → コンテナ停止 ----------
wait "$BROWSER_PID" 2>/dev/null

docker compose down
