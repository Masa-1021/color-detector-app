# Systemd サービス設定

Raspberry Pi起動時に自動でサービスを開始する設定です。

## 子機（カメラ側）のセットアップ

```bash
# サービスファイルをコピー
sudo cp color-detector.service /etc/systemd/system/

# ブローカーIPを編集（必要に応じて）
sudo nano /etc/systemd/system/color-detector.service
# → --mqtt-broker の値を変更

# サービスを有効化
sudo systemctl daemon-reload
sudo systemctl enable color-detector
sudo systemctl start color-detector

# 状態確認
sudo systemctl status color-detector
```

## 親機（中継機）のセットアップ

```bash
# サービスファイルをコピー
sudo cp mqtt-oracle-bridge.service /etc/systemd/system/

# Mosquittoを自動起動に設定
sudo systemctl enable mosquitto

# ブリッジサービスを有効化
sudo systemctl daemon-reload
sudo systemctl enable mqtt-oracle-bridge
sudo systemctl start mqtt-oracle-bridge

# 状態確認
sudo systemctl status mosquitto
sudo systemctl status mqtt-oracle-bridge
```

## よく使うコマンド

```bash
# サービス開始
sudo systemctl start [サービス名]

# サービス停止
sudo systemctl stop [サービス名]

# 再起動
sudo systemctl restart [サービス名]

# ログ確認
sudo journalctl -u [サービス名] -f
```
