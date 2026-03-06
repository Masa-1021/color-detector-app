#!/bin/bash
# Circle Detector - インストールスクリプト
#
# タスクバー、自動起動、systemdサービスをセットアップする。
# 使い方: ./install.sh

set -e

APP_DIR="/home/pi/Apps/color-detector-app"
DESKTOP_FILE="$APP_DIR/circle-detector.desktop"
PANEL_CONF="$HOME/.config/lxpanel-pi/panels/panel"

echo "=== Circle Detector インストール ==="

# ---------- アプリケーション登録 ----------
echo "[1/4] アプリケーション登録..."
mkdir -p "$HOME/.local/share/applications"
cp "$DESKTOP_FILE" "$HOME/.local/share/applications/"
echo "  -> アプリケーションメニューに追加"

# ---------- タスクバーにランチャー追加 ----------
echo "[2/4] タスクバー..."
if [ -f "$PANEL_CONF" ]; then
    if ! grep -q "circle-detector.desktop" "$PANEL_CONF" 2>/dev/null; then
        # launchbarセクションの最後のButton閉じタグの後に追加
        sed -i '/id=x-terminal-emulator.desktop/a\    }\n    Button {\n      id=circle-detector.desktop' "$PANEL_CONF"
        echo "  -> タスクバーにアイコン追加（再起動後に反映）"
    else
        echo "  -> タスクバーに登録済み"
    fi
else
    echo "  -> lxpanel-pi設定が見つかりません（スキップ）"
fi

# ---------- 自動起動 ----------
echo "[3/4] 自動起動..."
mkdir -p "$HOME/.config/autostart"
cp "$DESKTOP_FILE" "$HOME/.config/autostart/"
echo "  -> ログイン時に自動起動を設定"

# ---------- systemdサービス ----------
echo "[4/4] systemdサービス..."
if [ "$(id -u)" -eq 0 ] || command -v sudo &>/dev/null; then
    sudo cp "$APP_DIR/systemd/color-detector.service" /etc/systemd/system/
    sudo cp "$APP_DIR/systemd/mqtt-oracle-bridge.service" /etc/systemd/system/
    sudo systemctl daemon-reload
    echo "  -> サービスファイルをインストール"
    echo "  -> 有効化: sudo systemctl enable circle-detector"
    echo "  -> 起動:   sudo systemctl start circle-detector"
else
    echo "  -> sudo が必要です。手動でインストールしてください:"
    echo "     sudo cp $APP_DIR/systemd/*.service /etc/systemd/system/"
    echo "     sudo systemctl daemon-reload"
fi

# ---------- 依存パッケージ確認 ----------
echo ""
echo "依存パッケージ確認..."
MISSING=""
python3 -c "import flask" 2>/dev/null || MISSING="$MISSING flask"
python3 -c "import cv2" 2>/dev/null || MISSING="$MISSING opencv-python"
python3 -c "import paho.mqtt.client" 2>/dev/null || MISSING="$MISSING paho-mqtt"
python3 -c "import numpy" 2>/dev/null || MISSING="$MISSING numpy"

if [ -n "$MISSING" ]; then
    echo "  不足:$MISSING"
    echo "  pip3 install --break-system-packages$MISSING"
else
    echo "  全て OK"
fi

echo ""
echo "=== インストール完了 ==="
echo "起動方法:"
echo "  タスクバー:   左上のCircle Detectorアイコンをクリック"
echo "  自動起動:     ログイン時に自動で起動"
echo "  コマンド:     $APP_DIR/launch-desktop.sh"
echo "  サービス:     sudo systemctl start circle-detector"
