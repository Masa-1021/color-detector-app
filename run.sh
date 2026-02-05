#!/bin/bash
# 色検知アプリ 起動スクリプト
# Color Detector Application Launcher
#
# Oracle保存を有効にするには、別ターミナルでブリッジを起動:
#   ./run_bridge.sh

APP_DIR="/home/sano/color_detector_app"
LOG_DIR="$APP_DIR/logs"

# ログディレクトリが存在しない場合は作成
mkdir -p "$LOG_DIR"

# 環境変数設定（ディスプレイ）
export DISPLAY=:0

# 作業ディレクトリに移動
cd "$APP_DIR"

# ブリッジ状態確認
if pgrep -f "mqtt_oracle_bridge.py" > /dev/null; then
    echo "MQTT-Oracleブリッジ: 起動中 (DB保存有効)"
else
    echo "MQTT-Oracleブリッジ: 停止中 (DB保存無効)"
    echo "  DB保存するには別ターミナルで: ./run_bridge.sh"
fi

# アプリケーション起動
# 設定は config/settings.json から読み込み
python3 color_detector.py -i usb "$@"

# オプション例:
# ./run.sh                            # USBカメラ（設定ファイルから自動読み込み）
# ./run.sh -i /dev/video0             # 特定のカメラデバイス
# ./run.sh --mqtt                     # MQTT強制有効化
