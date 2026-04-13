#!/bin/bash
# Circle Detector - 設定UI起動スクリプト
#
# 設定UI（Flask）コンテナを起動し、Chromiumをアプリモードで開く。
# 検出ランタイムはターミナルで 'circle-detector start' で起動する。

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

cd "$APP_DIR" || exit 1

# 検出ランタイムが稼働中なら設定UIは起動できない
if docker compose ps --services --status running 2>/dev/null | grep -q "^detector-runtime$"; then
    zenity --error --text="検出ランタイムが稼働中のため設定UIを起動できません。\nターミナルで 'circle-detector stop' を実行してください。" 2>/dev/null || \
        echo "検出ランタイム稼働中のため設定UIを起動できません" >&2
    exit 1
fi

# 設定UIが既に稼働中ならブラウザだけ開く
if docker compose ps --services --status running 2>/dev/null | grep -q "^config-ui$"; then
    open_browser &
    exit 0
fi

docker compose --profile ui up -d

# サーバー起動待ち（最大15秒）
for _ in $(seq 1 30); do
    if curl -s -o /dev/null "$URL" 2>/dev/null; then
        break
    fi
    sleep 0.5
done

# ブラウザ起動（アプリモード）
open_browser &
BROWSER_PID=$!

# ブラウザ終了を待つ → 設定UIコンテナ停止
wait "$BROWSER_PID" 2>/dev/null

docker compose --profile ui down
