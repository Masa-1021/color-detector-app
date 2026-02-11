# Circle Detector

カメラ映像内の円形領域の色を検知し、パトライト（信号灯）の状態を判定して MQTT 経由で Oracle DB に送信する Web アプリケーション。

## システム構成

```
カメラ映像 → Circle Detector (Flask) → MQTT Broker → mqtt_oracle_bridge → Oracle Cloud DB
                  :5000                  (Mosquitto)
```

## 機能

- **映像表示**: MJPEG ストリーミングでリアルタイムカメラ映像を表示
- **円領域管理**: ドラッグで円を追加、移動・リサイズ対応
- **色検出**: HSV ベースの色判定 + 点滅検出
- **グループ管理**: 複数の円をグループ化し、マッピングルールで送信値を決定
- **MQTT 送信**: 検出結果を MQTT で送信（通信障害時はファイルキューに一時保管）
- **Oracle DB 保存**: MQTT-Oracle ブリッジ経由でクラウド DB に INSERT
- **Web UI**: レスポンシブ対応、Serendie Design System 準拠

## 必要環境

- Raspberry Pi (aarch64) / Linux
- Python 3.11+
- USB カメラ または Raspberry Pi カメラモジュール
- Mosquitto (MQTT ブローカー)

## セットアップ

### 依存パッケージ

```bash
pip3 install flask opencv-python-headless paho-mqtt oracledb
```

### Oracle Wallet

Oracle Cloud DB を使用する場合は Wallet を配置:

```
~/oracle_wallet/
  cwallet.sso, ewallet.p12, tnsnames.ora, sqlnet.ora ...
```

### 設定ファイル

`config/settings.json` に MQTT・Oracle 接続情報を記載。

## 起動

### Circle Detector (Web UI)

```bash
python3 -m circle_detector.app
# → http://localhost:5000
```

### MQTT-Oracle ブリッジ

```bash
python3 -u mqtt_oracle_bridge.py
```

### 一括起動

```bash
./run.sh
```

## ディレクトリ構成

```
circle_detector/
  app.py              # Flask メインアプリ
  camera.py           # カメラ管理 (MJPEG)
  config_manager.py   # 設定管理
  detector.py         # 色検出エンジン
  mqtt_sender.py      # MQTT 送信クライアント
  rule_engine.py      # マッピングルール評価
  templates/           # HTML テンプレート
  static/css/          # Serendie Design System CSS
  static/js/           # フロントエンド JS

mqtt_oracle_bridge.py  # MQTT → Oracle ブリッジ
equipment_status.py    # 設備ステータス定義
message_queue.py       # ファイルベースメッセージキュー
config/settings.json   # MQTT・Oracle 設定
test_playwright.py     # E2E テスト (Playwright)
```

## データフロー

1. **編集モード**: 円の追加・色登録・グループ設定・ルール設定
2. **実行モード**: カメラ映像から色検出 → ルール評価 → MQTT 送信
3. **ブリッジ**: MQTT メッセージを受信 → Oracle DB に INSERT
4. **耐障害性**: MQTT 切断時・Oracle 切断時はファイルキューに保管し、復旧後に再送
