# 設備稼働状況ログ機能 仕様書

## 1. 概要

色検知アプリで検出した信号灯の色・点滅状態から設備の稼働状況を判定し、MQTTを経由してOracle DBに記録する機能。

## 2. 機能要件

### 2.1 稼働状況の判定ルール

| 信号灯状態 | 稼働状況 | ステータスコード |
|-----------|---------|-----------------|
| 緑点滅 | 運転準備 | 1 |
| 緑点灯 | 自動運転 | 2 |
| 黄点灯 | 通過運転 | 3 |
| 黄点滅 | 段換中 | 16 |
| 赤点灯 | 異常中 | 14 |

**判定ロジック:**
- 緑: 点灯→自動運転(2)、点滅→運転準備(1)
- 黄: 点灯→通過運転(3)、点滅→段換中(16)
- 赤: 点灯→異常中(14)

### 2.2 点滅検出ロジック

- 一定期間（例: 2秒間）の色変化パターンを監視
- 同じ色が ON/OFF を繰り返す場合 → 点滅と判定
- 色が安定している場合 → 点灯と判定
- 点滅判定パラメータ:
  - 監視期間: 2000ms（設定可能）
  - 最小点滅回数: 2回以上
  - 点滅周期: 200ms〜1000ms

### 2.3 DBテーブル仕様

**テーブル名**: `HF1RCM01`

| カラム名 | 型 | 説明 | 例 |
|---------|-----|------|-----|
| MK_DATE | VARCHAR(14) | タイムスタンプ（YYYYMMDDhhmmss形式） | 20260205143025 |
| STA_NO1 | VARCHAR(10) | 固定値1（工場コード等） | PLANT01 |
| STA_NO2 | VARCHAR(10) | 固定値2（ラインコード等） | LINE01 |
| STA_NO3 | VARCHAR(10) | 領域固定値（設備コード等） | EQ001 |
| T1_STATUS | NUMBER(2) | 稼働状況コード | 2 |

## 3. 設定ファイル仕様

### 3.1 領域設定拡張（regions_config.json）

```json
{
  "version": "2.0",
  "created": "2026-02-05T14:30:00",
  "mqtt": {
    "broker": "mqtt.example.com",
    "port": 1883,
    "topic": "factory/equipment/status",
    "username": "",
    "password": "",
    "client_id": "color_detector_01"
  },
  "oracle": {
    "host": "oracle.example.com",
    "port": 1521,
    "service_name": "ORCL",
    "username": "user",
    "password": "pass",
    "table_name": "HF1RCM01"
  },
  "station": {
    "sta_no1": "PLANT01",
    "sta_no2": "LINE01"
  },
  "regions": [
    {
      "id": 1,
      "name": "設備A信号灯",
      "x": 100,
      "y": 100,
      "width": 50,
      "height": 50,
      "threshold": 30,
      "sta_no3": "EQ001",
      "enabled": true
    },
    {
      "id": 2,
      "name": "設備B信号灯",
      "x": 200,
      "y": 100,
      "width": 50,
      "height": 50,
      "threshold": 30,
      "sta_no3": "EQ002",
      "enabled": true
    }
  ],
  "blink_detection": {
    "window_ms": 2000,
    "min_changes": 2,
    "min_interval_ms": 200,
    "max_interval_ms": 1000
  }
}
```

## 4. システム構成（Mosquitto使用）

### 4.0 Phase 1〜3 構成（Oracle未接続）

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  カメラ入力      │────▶│  色検知アプリ    │────▶│  Mosquitto      │
│  (USBカメラ)    │     │  (Python)       │     │  (MQTT Broker)  │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                              │                          │
                              ▼                          ▼
                     ┌─────────────────┐        ┌─────────────────┐
                     │  ローカルログ    │        │  ファイル保存    │
                     │  (JSONL)        │        │  (JSON/CSV)     │
                     └─────────────────┘        └─────────────────┘
```

**この段階でできること:**
- 色検知＋点滅判定＋稼働状況コード変換
- MQTTでメッセージ送信
- ローカルファイルにログ保存
- `mosquitto_sub`でリアルタイム監視

### 4.0.1 Phase 4 構成（Oracle接続時）

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  カメラ入力      │────▶│  色検知アプリ    │────▶│  Mosquitto      │
│  (USBカメラ)    │     │  (Python)       │     │  (MQTT Broker)  │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                              │                          │
                              │                          ▼
                              │                 ┌─────────────────┐
                              │                 │  MQTT→Oracle    │
                              │                 │  ブリッジ        │
                              │                 │  (Python)       │
                              │                 └────────┬────────┘
                              │                          │
                              ▼                          ▼
                     ┌─────────────────┐        ┌─────────────────┐
                     │  ローカルログ    │        │  Oracle DB      │
                     │  (JSONL)        │        │  HF1RCM01       │
                     └─────────────────┘        └─────────────────┘
```

**メリット:**
- 疎結合: 色検知アプリとDB接続を分離
- 信頼性: MQTTのQoS（Quality of Service）でメッセージ保証
- 拡張性: 複数のサブスクライバーで購読可能（モニタリング、アラート等）
- 耐障害性: DB障害時もMQTTキューにメッセージを保持
- 段階的導入: Oracleがなくても動作確認可能

### 4.1 Mosquittoセットアップ（Raspberry Pi）

```bash
# Mosquittoのインストール
sudo apt update
sudo apt install -y mosquitto mosquitto-clients

# 自動起動設定
sudo systemctl enable mosquitto
sudo systemctl start mosquitto

# ステータス確認
sudo systemctl status mosquitto
```

### 4.2 Mosquitto設定ファイル

`/etc/mosquitto/conf.d/equipment.conf`:
```conf
# リスナー設定
listener 1883

# 匿名接続を許可（開発用）
allow_anonymous true

# ログ設定
log_dest file /var/log/mosquitto/mosquitto.log
log_type all

# 永続化（メッセージをディスクに保存）
persistence true
persistence_location /var/lib/mosquitto/

# QoS 1/2メッセージの保持
max_queued_messages 1000
```

設定反映:
```bash
sudo systemctl restart mosquitto
```

### 4.3 動作確認

```bash
# ターミナル1: サブスクライブ（受信待ち）
mosquitto_sub -h localhost -t "equipment/status/#" -v

# ターミナル2: パブリッシュ（テスト送信）
mosquitto_pub -h localhost -t "equipment/status/EQ001" \
  -m '{"mk_date":"20260205150000","sta_no1":"PLANT01","sta_no2":"LINE01","sta_no3":"EQ001","t1_status":2}'
```

## 5. データフロー

### 5.1 色検知→状態判定→MQTT送信

1. カメラから映像取得
2. 各領域の平均色を計算
3. 色変化を検出
4. 点滅パターンを分析
5. 稼働状況コードを決定
6. MQTTメッセージを送信

### 5.2 MQTTメッセージ形式

```json
{
  "mk_date": "20260205143025",
  "sta_no1": "PLANT01",
  "sta_no2": "LINE01",
  "sta_no3": "EQ001",
  "t1_status": 2,
  "raw_data": {
    "color_name": "green",
    "is_blinking": false,
    "rgb": {"r": 0, "g": 255, "b": 0}
  }
}
```

### 5.3 ローカルバックアップファイル（Oracle未接続時）

MQTTメッセージと同じ形式でJSONLファイルに保存:

**ファイルパス**: `./equipment_logs/status_YYYYMMDD.jsonl`

```jsonl
{"mk_date":"20260205143025","sta_no1":"PLANT01","sta_no2":"LINE01","sta_no3":"EQ001","t1_status":2}
{"mk_date":"20260205143130","sta_no1":"PLANT01","sta_no2":"LINE01","sta_no3":"EQ001","t1_status":1}
{"mk_date":"20260205143245","sta_no1":"PLANT01","sta_no2":"LINE01","sta_no3":"EQ002","t1_status":14}
```

**用途:**
- Oracle接続前の動作確認
- 障害時のバックアップ
- 後からOracleに一括インポート可能

## 6. 状態遷移

```
                    ┌──────────────────┐
                    │     初期化        │
                    │   (状態: 不明)    │
                    └────────┬─────────┘
                             │
                             ▼
    ┌────────────────────────────────────────────────────┐
    │                   色検出ループ                      │
    │  ┌─────────────────────────────────────────────┐  │
    │  │  点灯判定        点滅判定                     │  │
    │  │  ・緑点灯→2     ・緑点滅→1                  │  │
    │  │  ・黄点灯→3     ・黄点滅→16                 │  │
    │  │  ・赤点灯→14                                │  │
    │  └─────────────────────────────────────────────┘  │
    └────────────────────────────────────────────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  状態変化検出?    │
                    └────────┬─────────┘
                             │ Yes
                             ▼
                    ┌──────────────────┐
                    │  MQTT送信        │
                    │  + ローカルログ   │
                    └──────────────────┘
```

## 7. エラーハンドリング

| エラー種別 | 対応 |
|-----------|------|
| MQTT接続失敗 | リトライ（3回）後、ローカルキューに蓄積 |
| 色判定不能 | 前回の状態を維持、警告ログ出力 |
| 点滅判定不安定 | ヒステリシス適用、頻繁な切り替え防止 |

## 8. コマンドライン引数（追加）

```bash
python3 color_change_detector.py \
  -i usb \
  -c equipment_config.json \
  --mqtt-broker mqtt.example.com \
  --mqtt-port 1883 \
  --mqtt-topic factory/equipment/status \
  --sta-no1 PLANT01 \
  --sta-no2 LINE01
```

| 引数 | 説明 | デフォルト |
|-----|------|-----------|
| --mqtt-broker | MQTTブローカーホスト | localhost |
| --mqtt-port | MQTTポート | 1883 |
| --mqtt-topic | MQTTトピック | equipment/status |
| --sta-no1 | 固定値1 | "" |
| --sta-no2 | 固定値2 | "" |
| --enable-mqtt | MQTT送信有効化 | False |

## 9. UI追加要素

### 9.1 領域設定ダイアログ

領域追加時に以下を設定可能にする：
- 領域名（従来通り）
- STA_NO3（設備コード）
- 有効/無効フラグ

### 9.2 ステータス表示

画面下部に現在の稼働状況を表示：
```
[設備A] 自動運転(2) | [設備B] 段換中(16) | [設備C] 異常(14)
```

## 10. 実装フェーズ

### Phase 1: 点滅検出機能 ← 今回実装
- 点滅/点灯の判定ロジック実装
- 稼働状況コードへの変換
- UI表示の追加（現在の稼働状況表示）

### Phase 2: 設定拡張 ← 今回実装
- 領域ごとのSTA_NO3設定
- STA_NO1, STA_NO2の設定
- 設定ファイルの拡張（JSON形式）

### Phase 3: MQTT連携（Mosquitto） ← 今回実装
- Mosquittoインストール・設定
- paho-mqttライブラリ導入
- 色検知アプリからのメッセージ送信機能
- ファイルへのバックアップ保存（Oracle未接続時用）

### Phase 4: MQTT→Oracleブリッジ ← Oracle Cloud準備後
- Oracle Cloud Free Tierでデータベース作成
- 別プロセスでMQTTを購読
- oracledbでDB接続（ウォレット使用）
- HF1RCM01テーブルへのINSERT

## 11. 依存ライブラリ

### Phase 1〜3: 色検知アプリ側（今回）
```
paho-mqtt>=1.6.0    # MQTT通信（Mosquittoへの送信）
```

インストール:
```bash
pip3 install paho-mqtt
```

### Phase 4: MQTT→Oracleブリッジ側（Oracle Cloud準備後）
```
paho-mqtt>=1.6.0    # MQTT通信（Mosquittoからの受信）
oracledb>=2.0.0     # Oracle接続（thin mode、Instant Client不要）
```

インストール:
```bash
pip3 install oracledb
```

※ `oracledb` の thin mode は追加ソフトウェア不要でOracle Cloudに接続可能

## 12. Oracle Cloud Free Tier セットアップ

### 12.1 アカウント作成

1. https://www.oracle.com/cloud/free/ にアクセス
2. 「無料で始める」をクリック
3. メールアドレス、国（Japan）を入力
4. アカウント情報を入力（クレジットカード不要）
5. リージョン選択: **Japan East (Tokyo)** 推奨

### 12.2 Autonomous Database 作成

1. Oracle Cloud Console にログイン
2. 「Autonomous Database」→「Autonomous Database の作成」
3. 設定:
   - **表示名**: equipment_status_db
   - **データベース名**: EQSTATUSDB
   - **ワークロード**: Transaction Processing
   - **デプロイメント**: Serverless
   - **Always Free**: ✓ 有効
   - **ADMIN パスワード**: 設定する
4. 「Autonomous Database の作成」をクリック

### 12.3 接続情報の取得

1. 作成したDBをクリック
2. 「DB接続」→「ウォレットのダウンロード」
3. ウォレットパスワードを設定してダウンロード
4. `Wallet_EQSTATUSDB.zip` を展開

### 12.4 テーブル作成

SQL Developer Web または SQLcl で実行:

```sql
CREATE TABLE HF1RCM01 (
    MK_DATE   VARCHAR2(14) NOT NULL,
    STA_NO1   VARCHAR2(10),
    STA_NO2   VARCHAR2(10),
    STA_NO3   VARCHAR2(10),
    T1_STATUS NUMBER(2),
    CONSTRAINT PK_HF1RCM01 PRIMARY KEY (MK_DATE, STA_NO3)
);

-- インデックス（検索用）
CREATE INDEX IDX_HF1RCM01_STA ON HF1RCM01 (STA_NO1, STA_NO2, STA_NO3);
CREATE INDEX IDX_HF1RCM01_DATE ON HF1RCM01 (MK_DATE);

-- 確認
SELECT table_name FROM user_tables WHERE table_name = 'HF1RCM01';
```

### 12.5 Python接続設定

```python
import oracledb

# Thin mode（ウォレット使用）
connection = oracledb.connect(
    user="ADMIN",
    password="your_password",
    dsn="eqstatusdb_tp",
    config_dir="/path/to/wallet",
    wallet_location="/path/to/wallet",
    wallet_password="wallet_password"
)
```

### 12.6 設定ファイル例

```json
{
  "oracle_cloud": {
    "user": "ADMIN",
    "password": "your_password",
    "dsn": "eqstatusdb_tp",
    "wallet_dir": "/home/sano/oracle_wallet",
    "wallet_password": "wallet_password",
    "table_name": "HF1RCM01"
  }
}
```

## 13. MQTT→Oracleブリッジ仕様

### 12.1 ブリッジスクリプト概要

```python
#!/usr/bin/env python3
"""
mqtt_oracle_bridge.py
MQTTメッセージをOracle DBに書き込むブリッジ
"""

import json
import paho.mqtt.client as mqtt
import oracledb

class MQTTOracleBridge:
    def __init__(self, mqtt_config, oracle_config):
        self.mqtt_config = mqtt_config
        self.oracle_config = oracle_config
        self.connection = None

    def connect_oracle(self):
        self.connection = oracledb.connect(
            user=self.oracle_config['username'],
            password=self.oracle_config['password'],
            dsn=f"{self.oracle_config['host']}:{self.oracle_config['port']}/{self.oracle_config['service_name']}"
        )

    def on_message(self, client, userdata, msg):
        data = json.loads(msg.payload.decode())
        self.insert_status(data)

    def insert_status(self, data):
        cursor = self.connection.cursor()
        sql = """
            INSERT INTO HF1RCM01 (MK_DATE, STA_NO1, STA_NO2, STA_NO3, T1_STATUS)
            VALUES (:mk_date, :sta_no1, :sta_no2, :sta_no3, :t1_status)
        """
        cursor.execute(sql, {
            'mk_date': data['mk_date'],
            'sta_no1': data['sta_no1'],
            'sta_no2': data['sta_no2'],
            'sta_no3': data['sta_no3'],
            't1_status': data['t1_status']
        })
        self.connection.commit()
        cursor.close()

    def run(self):
        self.connect_oracle()
        client = mqtt.Client()
        client.on_message = self.on_message
        client.connect(self.mqtt_config['broker'], self.mqtt_config['port'])
        client.subscribe(self.mqtt_config['topic'])
        client.loop_forever()
```

### 12.2 ブリッジ起動コマンド

```bash
python3 mqtt_oracle_bridge.py \
  --mqtt-broker localhost \
  --mqtt-topic "equipment/status/#" \
  --oracle-host oracle.example.com \
  --oracle-port 1521 \
  --oracle-service ORCL \
  --oracle-user user \
  --oracle-pass pass
```

### 12.3 systemdサービス化（自動起動）

`/etc/systemd/system/mqtt-oracle-bridge.service`:
```ini
[Unit]
Description=MQTT to Oracle Bridge
After=network.target mosquitto.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/sano/pose_detection
ExecStart=/usr/bin/python3 mqtt_oracle_bridge.py --config /etc/mqtt_oracle_bridge.json
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

有効化:
```bash
sudo systemctl daemon-reload
sudo systemctl enable mqtt-oracle-bridge
sudo systemctl start mqtt-oracle-bridge
```

## 14. 補足

### 14.1 点滅検出の詳細アルゴリズム

```python
class BlinkDetector:
    def __init__(self, window_ms=2000, min_changes=2):
        self.history = deque(maxlen=100)  # (timestamp, color_name)
        self.window_ms = window_ms
        self.min_changes = min_changes

    def add_sample(self, timestamp_ms, color_name):
        self.history.append((timestamp_ms, color_name))

    def is_blinking(self, target_color):
        """指定色が点滅しているか判定"""
        now = self.history[-1][0] if self.history else 0
        window_start = now - self.window_ms

        # ウィンドウ内のサンプルを取得
        samples = [(t, c) for t, c in self.history if t >= window_start]

        # 色の変化回数をカウント
        changes = 0
        prev_is_target = None
        for t, c in samples:
            is_target = (c == target_color)
            if prev_is_target is not None and is_target != prev_is_target:
                changes += 1
            prev_is_target = is_target

        return changes >= self.min_changes
```

### 14.2 状態判定の優先順位

1. 赤点灯 → 異常中(14)  ※最優先
2. 黄点滅 → 段換中(16)
3. 黄点灯 → 通過運転(3)
4. 緑点滅 → 運転準備(1)
5. 緑点灯 → 自動運転(2)
6. その他 → 不明(0)
