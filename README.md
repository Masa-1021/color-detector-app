# Circle Detector

カメラ映像内の円形領域の色を検知し、パトライト（信号灯）の状態を判定して MQTT 経由で Oracle DB に送信するアプリケーション。

Raspberry Pi 上で動作し、**設定UI**（デスクトップアプリ）と**検出ランタイム**（ヘッドレス常駐）が分離された構成です。

## システム構成

```
┌─────────────────────────────────────────────────────────────┐
│                    親機 (Parent)                            │
│                                                             │
│  ┌── profile: ui ────────┐   ┌── profile: runtime ──────┐  │
│  │ config-ui (Flask)     │   │ detector-runtime         │  │
│  │ 設定編集のみ :5000     │   │ 検出ループ + MQTT送信     │  │
│  │                       │   │ (ヘッドレス)              │  │
│  └───────────────────────┘   │ ┌──────────────────────┐ │  │
│          ＝設定時のみ         │ │ bridge (Oracle送信)  │ │  │
│                               │ └──────────────────────┘ │  │
│                               └──────────────────────────┘  │
│                                        │                    │
│                               ┌────────┴────────┐           │
│                               │ mosquitto :1883 │           │
│                               └─────────────────┘           │
└─────────────────────────────────────────────────────────────┘
         ▲
         │ MQTT (TCP 1883)
┌────────┴────────┐
│   子機 (Child)   │
│ detector-runtime │
│ 検出ループのみ    │
└─────────────────┘
```

### 2つのプロファイル

| プロファイル | サービス | 用途 | 起動タイミング |
|---|---|---|---|
| **ui** | `mosquitto` + `config-ui` | 設定編集・円の配置・色のキャリブレーション | 設定時のみ |
| **runtime** | `mosquitto` + `detector-runtime` + `bridge` | 検出・MQTT送信・Oracle投入 | 常時稼働 |

**2つは同時起動不可**（カメラ `/dev/video0` 競合を避けるため）。

### デバイスモード

- **親機**: `runtime` に `bridge` を含む → MQTT → Oracle DB へINSERT
- **子機**: カメラ検出のみ。MQTT で親機にデータを送信（`bridge` なし）

---

## セットアップ

### 前提条件

| 項目 | 要件 |
|------|------|
| ハードウェア | Raspberry Pi 4/5（aarch64） |
| OS | Raspberry Pi OS (Debian Bookworm/Trixie) |
| Docker | Docker Engine + Docker Compose |
| カメラ | USB カメラ (`/dev/video0`) |
| ブラウザ | Chromium（設定UIアプリモード用） |

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

### Step 3: イメージビルド

```bash
docker compose --profile ui --profile runtime build
```

### Step 4: CLI ラッパーのインストール

```bash
sudo ln -sf $PWD/bin/circle-detector /usr/local/bin/circle-detector
circle-detector help
```

---

## 使い方

### 日常運用フロー

```bash
# ① 設定する時（カメラに円を配置・色を登録するなど）
デスクトップの「Circle Detector」アイコンをダブルクリック
  → 設定UI が起動、Chromium がアプリモードで開く
  → Chromium を閉じると UI も自動停止

または CLI から：
$ circle-detector config

# ② 検出を開始（常時稼働）
$ circle-detector start
  → mosquitto + detector-runtime + bridge が起動

# ③ 稼働確認
$ circle-detector status

# ④ ログ確認
$ circle-detector logs                     # 全コンテナ
$ circle-detector logs detector-runtime    # 検出のみ
$ circle-detector logs bridge              # ブリッジのみ

# ⑤ 設定を変更したら再読み込み（再起動不要）
$ circle-detector reload   # SIGHUP で config/*.json を再読み込み

# ⑥ 停止
$ circle-detector stop
```

### CLI コマンド一覧

| コマンド | 動作 |
|---|---|
| `circle-detector start [profile]` | 検出ランタイムを起動（profile省略時: default） |
| `circle-detector stop` | 検出ランタイムを停止 |
| `circle-detector config [profile]` | 設定UIを起動（runtime稼働中は拒否） |
| `circle-detector status` | 稼働状態と使用中の設定ディレクトリを表示 |
| `circle-detector logs [svc]` | ログを追従表示 |
| `circle-detector reload` | 検出ランタイムに設定再読み込みを通知（SIGHUP） |
| `circle-detector restart [profile]` | stop → start |
| `circle-detector profiles list` | 設定プロファイル一覧 |
| `circle-detector profiles create <name>` | defaultから複製して新規作成 |
| `circle-detector profiles delete <name>` | プロファイル削除 |
| `circle-detector help` | ヘルプ |

### 複数の設定プロファイル

複数のライン/カメラ配置に対応するため、設定は**プロファイル**として切り替え可能です。

```
config/                           # default プロファイル
├── settings.json
├── circle_detector.json
└── profiles/
    ├── line-a/                   # プロファイル "line-a"
    │   ├── settings.json
    │   └── circle_detector.json
    └── line-b/                   # プロファイル "line-b"
        ├── settings.json
        └── circle_detector.json
```

```bash
# 新プロファイルをdefaultから複製して作成（CLIから）
$ circle-detector profiles create line-a

# line-a を編集（UI）
$ circle-detector config line-a

# line-a で検出を開始
$ circle-detector start line-a
```

#### UIからのプロファイル保存

設定UIのヘッダーには現在編集中のプロファイル名（`profile: default` など）が表示されます。

- **設定保存** — 現在のプロファイルに上書き保存
- **別名保存** — 新しいプロファイル名を入力して別名で保存
  - 初期値として `<現在のプロファイル名>-YYYYMMDD-HHMM` が自動入力されるので、そのまま使うか編集可能
  - 既存名と重複した場合は上書き確認ダイアログが表示される
  - 保存後、そのプロファイルで検出を開始するには `circle-detector start <name>` を実行

---

## 初回設定

設定UIを起動（`circle-detector config` or デスクトップアイコン）→ ブラウザで `http://localhost:5000`

### 親機の場合

1. ヘッダーの **歯車アイコン** → システム設定
2. MQTT: ブローカー `mosquitto`（Docker内名）、ポート `1883`
3. Oracle DB: DSN・ユーザー・パスワード入力 →「接続テスト」
4. NTP: 必要に応じて有効化
5. 円の配置・色の登録・グループ/ルールの設定

### 子機の場合

1. デバイスモードを「子機」に切り替え
2. MQTT ブローカーに **親機の IP アドレス** を入力（例: `192.168.1.100`）
3. 「接続」で確認

### 設定ファイル

設定はすべて `config/settings.json` に保存されます。UI経由での編集を推奨。

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

## アーキテクチャ詳細

### コンテナ構成

| コンテナ | Dockerfile | プロファイル | 役割 |
|---|---|---|---|
| `mosquitto` | `eclipse-mosquitto:2` | ui, runtime | MQTTブローカー |
| `config-ui` | `Dockerfile.detector` | ui | Flask 設定UI（:5000） |
| `detector-runtime` | `Dockerfile.runtime` | runtime | ヘッドレス検出ループ |
| `bridge` | `Dockerfile.oracle-bridge` | runtime | MQTT → Oracle DB |

### キュー保存先

| コンテナ | キュー | 理由 |
|---|---|---|
| `detector-runtime` | **tmpfs (50MB)** | MQTT切断中のSD書き込み負荷を回避 |
| `bridge` | 永続ボリューム | Oracle長時間切断に備える |

### カメラの競合

`/dev/video0` は同時に1プロセスしか開けないため、`config-ui` と `detector-runtime` は同一プロファイルに同居させていません。`circle-detector start` は `ui` が稼働中なら自動で `down` します。

### NTP 時刻同期

- **検出ランタイム起動中**: ランタイム内のNTPスレッドが優先（systemd-timesyncd を停止）
- **検出ランタイム停止中**: systemd-timesyncd が自動再開し `ntp.nict.jp` と同期
- `timesyncd-watcher` サービス（ホスト側）がシグナルファイル `/run/circle-detector/ntp-active` を監視して制御

---

## ディレクトリ構成

```
color-detector-app/
├── circle_detector/
│   ├── app.py                  # Flask設定UI
│   ├── runtime.py              # ヘッドレス検出ランタイム（CLIエントリ）
│   ├── camera.py
│   ├── config_manager.py
│   ├── detector.py
│   ├── mqtt_sender.py
│   ├── ntp_sync.py
│   ├── rule_engine.py
│   ├── templates/ / static/
│
├── mqtt_oracle_bridge.py       # MQTT → Oracle DB ブリッジ
├── equipment_status.py
├── message_queue.py
│
├── Dockerfile.detector         # config-ui 用（Flask入り）
├── Dockerfile.runtime          # detector-runtime 用（軽量・Flaskなし）
├── Dockerfile.oracle-bridge    # bridge 用
├── docker-compose.yml          # profile: ui / runtime
│
├── bin/
│   └── circle-detector         # CLIラッパー
│
├── config/settings.json
├── launch-desktop.sh           # 設定UIをデスクトップアプリとして開く
├── circle-detector.desktop     # デスクトップエントリ
├── docker/                     # mosquitto 設定
├── systemd/                    # timesyncd-watcher など
├── icons/
├── logs/
└── queue/                      # bridge のみ使用（detectorはtmpfs）
```

---

## トラブルシューティング

### カメラが映らない / runtime が起動失敗

```bash
ls /dev/video*
fuser /dev/video0               # 他のプロセスが掴んでいないか
circle-detector status          # ui と runtime が同時稼働していないか
```

### MQTT に接続できない（子機）

```bash
# 親機で runtime が起動しているか
# （親機側で）
circle-detector status

# ポート 1883 が開いているか
nc -zv <親機IP> 1883
```

### Oracle DB 接続失敗

```bash
circle-detector logs bridge
# DPY-6005 等のエラーが出る場合は settings.json の dsn/user/password/wallet_dir を確認
```

### ポート 5000 が使用中

```bash
lsof -i :5000
# Dockerコンテナ以外のプロセスが掴んでいたら停止
```

### コンテナを完全にリセット

```bash
docker compose --profile ui --profile runtime down -v
docker compose --profile ui --profile runtime build --no-cache
```

---

## ライセンス

Private
