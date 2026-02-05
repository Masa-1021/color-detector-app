#!/bin/bash
# 設備状態テストUI 起動スクリプト
# Equipment Status Test UI Launcher
#
# Oracle保存を有効にするには、UIからブリッジを起動するか、
# 別ターミナルで: ./run_bridge.sh

APP_DIR="/home/sano/color_detector_app"

# 環境変数設定
export DISPLAY=:0

# 作業ディレクトリに移動
cd "$APP_DIR"

echo "=================================="
echo "設備状態テストUI を起動中..."
echo "=================================="

# ブリッジ状態確認
if pgrep -f "mqtt_oracle_bridge.py" > /dev/null; then
    echo "MQTT-Oracleブリッジ: 起動中 (DB保存有効)"
else
    echo "MQTT-Oracleブリッジ: 停止中 (UIから起動可能)"
fi

python3 test_ui.py
