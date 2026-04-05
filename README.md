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
- **MQTT 送信**: QoS 2 (Exactly once) で検出結果を送信（通信障害時はファイルキューに一時保管→自動再送）
- **Oracle DB 保存**: MQTT-Oracle ブリッジ経由でクラウド DB に INSERT（Wallet 認証対応）
- **NTP 時刻同期**: アプリ起動中は systemd-timesyncd を停止しアプリの NTP 設定を優先
- **デスクトップアプリ**: Chromium アプリモードでネイティブ風 UI、タスクバーランチャー対応
- **初回セットアップ**: 起動時にデバイスモード（親機/子機）を選択するウィザード
- **Web UI**: レスポンシブ対応、Serendie Design System 準拠

---

## リリース情報

### v1.0.0 (2026-04-06)

Docker コンテナ化対応リリース。

**変更点:**
- Docker Compose でコンテナ起動 (detector, bridge, mosquitto の3コンテナ構成)
- NTP 同期: アプリ起動中は systemd-timesyncd を停止しアプリの設定を優先 (timesyncd-watcher サービス)
- MQTT QoS 2 (Exactly once) に変更
- システム設定ボタンをトグル動作に変更
- Oracle Wallet をコンテナにマウント対応
- detector / bridge 間でログボリュームを共有しブリッジステータスを正しく表示

**ダウンロード:**
- [GitHub Releases](https://github.com/MasatoshiSano/color-detector-app/releases/tag/v1.0.0)
- `circle-detector-images.tar` (358MB) — Docker イメージ3つ (detector, bridge, mosquitto)

---

## Docker で起動（推奨）

### 前提条件

| 項目 | 要件 |
|------|------|
| ハードウェア | Raspberry Pi 4/5（aarch64） |
| OS | Raspberry Pi OS（Debian Bookworm/Trixie）|
| Docker | Docker Engine + Docker Compose |
| カメラ | USB カメラ（`/dev/video0`） |
| ブラウザ | Chromium（デスクトップアプリ用） |

### Step 1: Docker のインストール

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# ログアウト→再ログイン
```

### Step 2: リポジトリのクローン

```bash
cd ~
mkdir -p Apps && cd Apps
git clone https://github.com/MasatoshiSano/color-detector-app.git
cd color-detector-app
```

### Step 3: Docker イメージの準備

**方法 A: リリースからイメージを取得（ビルド不要）**

```bash
# GitHub Releases からダウンロード
wget https://github.com/MasatoshiSano/color-detector-app/releases/download/v1.0.0/circle-detector-images.tar

# イメージを読み込み
docker load -i circle-detector-images.tar
```

**方法 B: ソースからビルド**

```bash
docker compose build
```

### Step 4: 起動

```bash
# コンテナ起動
docker compose up -d

# 状態確認
docker compose ps
```

ブラウザで `http://localhost:5000` を開く。

### Step 5: デスクトップアプリとして使う

```bash
# 手動起動（ブラウザ付き）
./launch-desktop.sh

# アプリメニュー・タスクバー・自動起動を設定
./install.sh
```

`launch-desktop.sh` の動作:
1. `docker compose up -d` でコンテナ3つを起動
2. Chromium をアプリモードで起動
3. **ブラウザを閉じると `docker compose down` でコンテナも停止**

### コンテナ構成

| コンテナ | 役割 | ポート |
|---------|------|--------|
| detector | カメラ検出 + Web UI (Flask) | 5000 |
| mosquitto | MQTT ブローカー | 1883 |
| bridge | MQTT → Oracle DB ブリッジ | - |

### Docker Compose コマンド

```bash
# 起動
docker compose up -d

# 停止
docker compose down

# ログ確認
docker compose logs -f
docker compose logs detector --tail 50
docker compose logs bridge --tail 50

# 再起動
docker compose restart

# イメージ再ビルド
docker compose build
```

---

## 別 PC への移行

### イメージをエクスポート

```bash
# 3つのイメージをまとめてエクスポート
docker save color-detector-app-detector color-detector-app-bridge eclipse-mosquitto:2 \
  -o circle-detector-images.tar
```

### 別 PC でインポート

```bash
# イメージを読み込み
docker load -i circle-detector-images.tar

# ソースコードをクローン
git clone https://github.com/MasatoshiSano/color-detector-app.git
cd color-detector-app

# 設定ファイルを用意（config/settings.json）
# Oracle Wallet を配置（/home/pi/oracle_wallet/）

# 起動
docker compose up -d
```

---

## 従来の方法で起動（Docker なし）

### Python パッケージのインストール

```bash
sudo apt install -y git python3-pip python3-opencv mosquitto mosquitto-clients lsof

pip3 install --break-system-packages flask opencv-python-headless paho-mqtt numpy ntplib

# 親機で Oracle DB を使う場合
pip3 install --break-system-packages oracledb
```

### コマンドラインから起動

```bash
cd ~/Apps/color-detector-app

# Web UI のみ
python3 -m circle_detector.app
# → http://localhost:5000

# MQTT-Oracle ブリッジ（別ターミナル、親機のみ）
python3 -u mqtt_oracle_bridge.py

# 一括起動（バックエンド + ブリッジ + 自動再起動）
./run.sh
```

---

## 設定

初回起動後、ブラウザの UI から設定できます。

### 親機の場合

1. ヘッダーの **歯車アイコン** → システム設定
2. MQTT: ブローカーは `mosquitto`（Docker）または `localhost`（直接起動）
3. Oracle DB: DSN, ユーザー, パスワードを入力 → 「接続テスト」で確認
4. NTP: 必要に応じて有効化（有効化中は systemd-timesyncd を自動停止）

### 子機の場合

1. ヘッダーの **歯車アイコン** → システム設定
2. MQTT ブローカーに **親機の IP アドレス** を入力（例: `192.168.1.100`）
3. 「接続」ボタンで接続確認

### 設定ファイル（参考）

`config/settings.json`:
```json
{
  "device_mode": "parent",
  "mqtt": {
    "broker": "mosquitto",
    "port": 1883,
    "topic": "equipment/status"
  },
  "oracle": {
    "dsn": "eqstatusdb_low",
    "user": "ADMIN",
    "password": "your_password",
    "wallet_dir": "/home/pi/oracle_wallet",
    "table_name": "HF1RCM01",
    "use_wallet": true
  }
}
```

---

## 使い方

### 編集モード

1. **円を追加**: 「円設定」タブ →「新しい円を追加」ボタン
2. **円を移動**: 映像上の円をドラッグ
3. **円をリサイズ**: 円の外周部分をドラッグ
4. **色を登録**: 円を選択 →「中心色を取得」または「パレット」で色を追加
5. **グループ設定**: 「グループ」タブで円をグループ化し、ルールを設定
6. **設定保存**: ヘッダーの「設定保存」ボタン

### 実行モード

1. 「実行開始」ボタン → カメラ映像の表示有無を選択
2. 検出状態とルール評価結果がリアルタイム表示
3. 送信ログで MQTT 送信状況を確認

---

## NTP 時刻同期

- **アプリ起動中**: アプリの NTP 設定が優先（systemd-timesyncd は自動停止）
- **アプリ停止中**: systemd-timesyncd が自動再開し `ntp.nict.jp` と同期
- `timesyncd-watcher` サービスがシグナルファイル (`/run/circle-detector/ntp-active`) を監視して制御

---

## ディレクトリ構成

```
color-detector-app/
├── circle_detector/          # メインアプリケーション
│   ├── app.py                #   Flask メインアプリ（API 含む）
│   ├── camera.py             #   カメラ管理 (MJPEG ストリーミング)
│   ├── config_manager.py     #   設定管理（JSON ベース）
│   ├── detector.py           #   HSV 色検出 + 点滅検出エンジン
│   ├── mqtt_sender.py        #   MQTT 送信クライアント（QoS 2、キュー対応）
│   ├── ntp_sync.py           #   NTP 時刻同期（timesyncd 制御付き）
│   ├── rule_engine.py        #   マッピングルール評価
│   ├── templates/index.html  #   Web UI テンプレート
│   ├── static/css/style.css  #   Serendie Design System CSS
│   └── static/js/main.js     #   フロントエンド JS
│
├── mqtt_oracle_bridge.py     # MQTT → Oracle DB ブリッジ
├── equipment_status.py       # 設備ステータス定義
├── message_queue.py          # ファイルベースメッセージキュー
│
├── Dockerfile                # Docker イメージ定義
├── docker-compose.yml        # Docker Compose 構成
├── docker/                   # Mosquitto 設定
│
├── config/
│   └── settings.json         # MQTT・Oracle・デバイスモード設定
│
├── launch-desktop.sh         # デスクトップアプリ起動 (docker compose 経由)
├── run.sh                    # CLI 一括起動スクリプト
├── install.sh                # インストール（メニュー・タスクバー・自動起動）
├── circle-detector.desktop   # Linux デスクトップエントリ
│
├── systemd/                  # systemd サービス定義
│   ├── color-detector.service
│   ├── timesyncd-watcher.service
│   └── timesyncd-watcher.sh
│
├── k8s/                      # Kubernetes マニフェスト
├── icons/                    # アプリアイコン (SVG/PNG)
├── logs/                     # ログ出力先（自動作成）
└── queue/                    # 未送信メッセージキュー（自動作成）
```

## トラブルシューティング

### カメラが映らない

```bash
ls /dev/video*
fuser /dev/video0
```

### MQTT に接続できない（子機）

```bash
# 親機の Mosquitto が動いているか
docker compose ps   # 親機で確認

# ポート 1883 が開いているか
nc -zv <親機IP> 1883
```

### コンテナのログ確認

```bash
docker compose logs detector --tail 50
docker compose logs bridge --tail 50
docker compose logs mosquitto --tail 50
```

### ポート 5000 が使用中

```bash
lsof -i :5000
# Docker 以外のプロセスがあれば停止
pkill -f "circle_detector.app"
```

## ライセンス

Private
