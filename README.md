# Circle Detector

カメラ映像内の円形領域の色を検知し、パトライト（信号灯）の状態を判定して MQTT 経由で Oracle DB に送信するデスクトップアプリケーション。

Raspberry Pi 上で動作し、Chromium アプリモードでネイティブアプリのように使用可能。

## システム構成

```
┌─────────────────────────────────────────────────────────────────┐
│                         親機 (Parent)                           │
│                                                                 │
│  カメラ → Circle Detector → MQTT Broker → Bridge → Oracle DB   │
│            (Flask :5000)    (Mosquitto)                          │
└─────────────────────────────────────────────────────────────────┘
         ▲
         │ MQTT
┌────────┴────────┐
│   子機 (Child)   │
│ カメラ → Circle  │
│   Detector       │
│   (Flask :5000)  │
└─────────────────┘
```

- **親機**: カメラ検出 + MQTTブローカー + Oracle DB ブリッジ（全機能）
- **子機**: カメラ検出のみ。MQTT で親機にデータを送信

## 機能

- **映像表示**: MJPEG ストリーミングでリアルタイムカメラ映像を表示
- **円領域管理**: ワンクリックで円を追加、ドラッグで移動・リサイズ
- **色検出**: HSV ベースの色判定 + 点滅検出
- **グループ管理**: 複数の円をグループ化し、マッピングルールで送信値を決定
- **MQTT 送信**: 検出結果を MQTT で送信（通信障害時はファイルキューに一時保管→自動再送）
- **Oracle DB 保存**: MQTT-Oracle ブリッジ経由でクラウド DB に INSERT（Wallet 認証対応）
- **デスクトップアプリ**: Chromium アプリモードでネイティブ風 UI、タスクバーランチャー対応
- **初回セットアップ**: 起動時にデバイスモード（親機/子機）を選択するウィザード
- **Web UI**: レスポンシブ対応、Serendie Design System 準拠

---

## 新しい Raspberry Pi への導入手順

### 前提条件

| 項目 | 要件 |
|------|------|
| ハードウェア | Raspberry Pi 4/5（aarch64） |
| OS | Raspberry Pi OS（Debian Bookworm/Trixie）|
| カメラ | USB カメラ または Raspberry Pi カメラモジュール |
| ネットワーク | 親機と同一 LAN に接続（子機の場合） |
| ブラウザ | Chromium（デスクトップアプリ用、通常プリインストール済み） |

### Step 1: OS の基本セットアップ

```bash
# システム更新
sudo apt update && sudo apt upgrade -y

# 必要なシステムパッケージ
sudo apt install -y git python3-pip python3-opencv mosquitto mosquitto-clients lsof
```

> **子機の場合**: `mosquitto` は不要（親機のブローカーを使用）。インストールしなくても動作します。

### Step 2: リポジトリのクローン

```bash
cd ~
git clone https://github.com/MasatoshiSano/color-detector-app.git color_detector_app
cd color_detector_app
```

> **既存の親機からコピーする場合**:
> ```bash
> scp -r sano@<親機IP>:/home/sano/color_detector_app ~/color_detector_app
> ```

### Step 3: Python パッケージのインストール

```bash
pip3 install --break-system-packages flask opencv-python-headless paho-mqtt numpy ntplib
```

**親機で Oracle DB を使う場合**は追加で:

```bash
pip3 install --break-system-packages oracledb
```

> `--break-system-packages` は Debian Bookworm 以降で venv 外にインストールする際に必要です。venv を使う場合は不要です。

### Step 4: カメラの確認

```bash
# カメラデバイスの存在確認
ls /dev/video*

# USBカメラのテスト（映像が映ればOK、q で終了）
python3 -c "import cv2; cap=cv2.VideoCapture(0); print('OK' if cap.isOpened() else 'NG'); cap.release()"
```

Raspberry Pi カメラモジュールの場合:
```bash
# legacy camera を有効化（必要に応じて）
sudo raspi-config  # → Interface Options → Camera → Enable
```

### Step 5: 初回起動と動作確認

```bash
cd ~/color_detector_app

# Web UI のみ起動
python3 -m circle_detector.app
```

ブラウザで `http://localhost:5000` を開く。

**初回起動時の画面**:
1. デバイスモード選択ダイアログが表示される
2. **親機**（ブローカー＋DB＋カメラ）または **子機**（カメラのみ）を選択
3. 「設定して開始」をクリック

> Ctrl+C で停止。

### Step 6: 設定の調整

初回起動後、ブラウザの UI から設定できます。

#### 親機の場合

1. ヘッダーの **歯車アイコン** → システム設定
2. MQTT: ブローカーは `localhost`（デフォルト）
3. Oracle DB: DSN, ユーザー, パスワードを入力 → 「接続テスト」で確認
4. NTP: 必要に応じて有効化

#### 子機の場合

1. ヘッダーの **歯車アイコン** → システム設定
2. MQTT ブローカーに **親機の IP アドレス** を入力（例: `192.168.1.100`）
3. 「接続」ボタンで接続確認

#### 設定ファイル（直接編集する場合）

`config/settings.json`:
```json
{
  "device_mode": "parent",
  "mqtt": {
    "broker": "localhost",
    "port": 1883,
    "topic": "equipment/status"
  },
  "oracle": {
    "dsn": "eqstatusdb_low",
    "user": "ADMIN",
    "password": "your_password",
    "wallet_dir": "/home/sano/oracle_wallet",
    "table_name": "HF1RCM01"
  }
}
```

---

## デスクトップアプリとして使う

Chromium をアプリモード（アドレスバーなし）で起動し、ネイティブアプリのように使えます。

### 手動で起動

```bash
cd ~/color_detector_app
./launch-desktop.sh
```

これにより:
1. Flask バックエンドが起動（自動再起動ループ付き）
2. MQTT-Oracle ブリッジが起動（親機のみ）
3. Chromium がアプリモードで開く
4. **ブラウザを閉じるとバックエンドも自動停止**

### 自動インストール（タスクバー・自動起動）

```bash
cd ~/color_detector_app
./install.sh
```

以下を自動設定します:

| 項目 | 内容 |
|------|------|
| アプリメニュー | Raspberry Pi のアプリケーションメニューに登録 |
| タスクバー | 左上のタスクバーにランチャーアイコン追加 |
| 自動起動 | ログイン時に自動で Circle Detector を起動 |
| systemd | サービスファイルをインストール（手動で有効化が必要） |

### install.sh がやること（詳細）

```
1. ~/.local/share/applications/ に circle-detector.desktop をコピー
   → アプリメニューの「ユーティリティ」に表示される

2. ~/.config/lxpanel-pi/panels/panel を編集
   → タスクバーのランチャーにアイコンを追加

3. ~/.config/autostart/ に circle-detector.desktop をコピー
   → ログイン時に launch-desktop.sh が自動実行される

4. systemd サービスファイルを /etc/systemd/system/ にコピー
   → sudo systemctl enable circle-detector で有効化可能
```

### デスクトップアプリの仕組み

```
launch-desktop.sh
├── ポート5000 の既存プロセスを確認
├── Flask バックエンドを起動（while true ループで自動再起動）
├── MQTT-Oracle ブリッジを起動（親機のみ）
├── localhost:5000 の応答を待つ（最大10秒）
├── Chromium --app=http://localhost:5000 で起動
└── ブラウザ終了時にバックエンドも停止
```

### ユーザー名が `sano` 以外の場合

`install.sh` と `launch-desktop.sh` 内のパスを変更:

```bash
# 例: ユーザー名が pi の場合
sed -i 's|/home/sano|/home/pi|g' launch-desktop.sh install.sh circle-detector.desktop
sed -i 's|/home/sano|/home/pi|g' systemd/color-detector.service systemd/mqtt-oracle-bridge.service
```

---

## systemd サービスとして起動（ヘッドレス運用）

ディスプレイなしで Raspberry Pi を運用する場合:

```bash
# サービス有効化
sudo systemctl enable circle-detector
sudo systemctl start circle-detector

# 親機の場合は Mosquitto とブリッジも
sudo systemctl enable mosquitto
sudo systemctl enable mqtt-oracle-bridge
sudo systemctl start mqtt-oracle-bridge

# 状態確認
sudo systemctl status circle-detector

# ログ確認
sudo journalctl -u circle-detector -f
```

---

## コマンドラインから起動

```bash
cd ~/color_detector_app

# Web UI のみ
python3 -m circle_detector.app
# → http://localhost:5000

# MQTT-Oracle ブリッジ（別ターミナル、親機のみ）
python3 -u mqtt_oracle_bridge.py

# 一括起動（バックエンド + ブリッジ + 自動再起動）
./run.sh
```

---

## 使い方

### 編集モード

1. **円を追加**: 「円設定」タブ →「新しい円を追加」ボタン（画面中央に自動配置）
2. **円を移動**: 映像上の円をドラッグ
3. **円をリサイズ**: 円の外周部分をドラッグ
4. **色を登録**: 円を選択 →「中心色を取得」または「パレット」で色を追加
5. **グループ設定**: 「グループ」タブで円をグループ化し、ルールを設定
6. **設定保存**: ヘッダーの「設定保存」ボタン

### 実行モード

1. 「実行開始」ボタン → カメラ映像の表示有無を選択
2. 検出状態とルール評価結果がリアルタイム表示
3. 送信ログで MQTT 送信状況を確認:
   - ✓ 送信成功
   - 🔂 キュー保存（MQTT 切断中→復帰後に自動再送）
   - ✗ 送信失敗

---

## ディレクトリ構成

```
color_detector_app/
├── circle_detector/          # メインアプリケーション
│   ├── app.py                #   Flask メインアプリ（API 含む）
│   ├── camera.py             #   カメラ管理 (MJPEG ストリーミング)
│   ├── config_manager.py     #   設定管理（JSON ベース）
│   ├── detector.py           #   HSV 色検出 + 点滅検出エンジン
│   ├── mqtt_sender.py        #   MQTT 送信クライアント（キュー対応）
│   ├── ntp_sync.py           #   NTP 時刻同期
│   ├── rule_engine.py        #   マッピングルール評価
│   ├── templates/index.html  #   Web UI テンプレート
│   ├── static/css/style.css  #   Serendie Design System CSS
│   └── static/js/main.js     #   フロントエンド JS
│
├── mqtt_oracle_bridge.py     # MQTT → Oracle DB ブリッジ
├── equipment_status.py       # 設備ステータス定義
├── message_queue.py          # ファイルベースメッセージキュー
│
├── config/
│   └── settings.json         # MQTT・Oracle・デバイスモード設定
│
├── launch-desktop.sh         # デスクトップアプリ起動スクリプト
├── run.sh                    # CLI 一括起動スクリプト
├── install.sh                # インストール（メニュー・タスクバー・自動起動）
├── circle-detector.desktop   # Linux デスクトップエントリ
│
├── icons/                    # アプリアイコン (SVG/PNG)
├── systemd/                  # systemd サービス定義
├── logs/                     # ログ出力先（自動作成）
└── queue/                    # 未送信メッセージキュー（自動作成）
```

## データフロー

1. **編集モード**: 円の追加・色登録・グループ設定・ルール設定
2. **実行モード**: カメラ映像から色検出 → ルール評価 → MQTT 送信
3. **ブリッジ**: MQTT メッセージを受信 → Oracle DB に INSERT
4. **耐障害性**: MQTT 切断時・Oracle 切断時はファイルキューに保管し、復帰後に自動再送

## トラブルシューティング

### カメラが映らない

```bash
# デバイス確認
ls /dev/video*

# 他のプロセスがカメラを使用していないか
fuser /dev/video0
```

### MQTT に接続できない（子機）

```bash
# 親機の Mosquitto が動いているか
ssh sano@<親機IP> "systemctl status mosquitto"

# ポート 1883 が開いているか
nc -zv <親機IP> 1883
```

### ポート 5000 が使用中

```bash
# 使用中のプロセスを確認
lsof -i :5000

# 既存プロセスを停止
pkill -f "circle_detector.app"
```

### ログの確認

```bash
# アプリログ
tail -f ~/color_detector_app/logs/app.log

# ブリッジログ
tail -f ~/color_detector_app/logs/bridge.log
```

## ライセンス

Private
