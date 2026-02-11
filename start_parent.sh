#!/bin/bash
#
# 親機（中継機）起動スクリプト
#
# Mosquittoブローカーとmqtt_oracle_bridgeを同時に起動
#
# 使用方法:
#   ./start_parent.sh
#
# 停止:
#   Ctrl+C
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "親機（中継機）起動"
echo "========================================"

# Mosquittoが起動しているか確認
if ! systemctl is-active --quiet mosquitto; then
    echo "Mosquitto: 起動中..."
    sudo systemctl start mosquitto
    sleep 1
fi

if systemctl is-active --quiet mosquitto; then
    echo "Mosquitto: 稼働中 ✓"
else
    echo "Mosquitto: 起動失敗"
    echo "  sudo apt install mosquitto で インストールしてください"
    exit 1
fi

echo "----------------------------------------"
echo "MQTT-Oracle ブリッジを起動します..."
echo "(Ctrl+C で停止)"
echo "----------------------------------------"

# ブリッジを起動（フォアグラウンド）
python3 mqtt_oracle_bridge.py

# 終了時にMosquittoも停止するか確認
echo ""
read -p "Mosquittoも停止しますか？ [y/N]: " answer
if [[ "$answer" =~ ^[Yy]$ ]]; then
    sudo systemctl stop mosquitto
    echo "Mosquitto: 停止しました"
fi
