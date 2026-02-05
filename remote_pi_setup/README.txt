=====================================
他のRaspberry Pi セットアップ手順
=====================================

中継機（ハブ）: 192.168.32.213

■ 必要なもの
- Raspberry Pi (カメラ付き)
- Python 3
- paho-mqtt, opencv-python

■ セットアップ手順

1. 必要なパッケージをインストール:
   sudo apt update
   sudo apt install python3-pip python3-opencv
   pip3 install paho-mqtt

2. このフォルダをコピー:
   scp -r sano@192.168.32.213:/home/sano/color_detector_app ~/

3. 設定ファイルを編集:
   nano ~/color_detector_app/config/settings.json

   - broker を "192.168.32.213" に設定（済み）
   - oracle.enabled を false に設定（済み）
   - sta_no3 を このPi固有のID に変更 (例: "REMOTE_EQ001")

4. 実行:
   cd ~/color_detector_app
   python3 color_detector.py -i usb

■ 接続テスト

中継機に届いているか確認:
   mosquitto_sub -h 192.168.32.213 -t "equipment/status/#" -v

■ 注意事項

- Oracle接続は中継機のみで行う（他のPiではoracle.enabled: false）
- 各Piで異なる sta_no3 を設定すること
- ファイアウォールでポート1883が開いていること
