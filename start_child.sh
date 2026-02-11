#!/bin/bash
#
# 子機（カメラ側）起動スクリプト
#
# 使用方法:
#   ./start_child.sh [BROKER_IP] [--headless]
#
# 例:
#   ./start_child.sh 192.168.32.213              # GUI付き
#   ./start_child.sh 192.168.32.213 --headless   # ヘッドレス（GUI無し）
#   ./start_child.sh --headless                  # デフォルトIP + ヘッドレス
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 引数解析
BROKER_IP="192.168.32.213"
HEADLESS=""

for arg in "$@"; do
    if [ "$arg" = "--headless" ]; then
        HEADLESS="--headless"
    elif [[ "$arg" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        BROKER_IP="$arg"
    fi
done

echo "========================================"
echo "子機（カメラ）起動"
echo "========================================"
echo "ブローカー: $BROKER_IP"
if [ -n "$HEADLESS" ]; then
    echo "モード: ヘッドレス（GUI無し）"
fi
echo "----------------------------------------"

# color_detector.py を起動
python3 color_detector.py -i usb --mqtt --mqtt-broker "$BROKER_IP" $HEADLESS
