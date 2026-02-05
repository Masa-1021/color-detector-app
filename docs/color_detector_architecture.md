# 色検知アプリ アーキテクチャ

## 1. システム全体構成

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Raspberry Pi 5                                  │
│                                                                             │
│  ┌─────────────┐    ┌──────────────────────────────────────────────────┐   │
│  │             │    │           color_change_detector.py               │   │
│  │  USBカメラ   │───▶│  ┌─────────────┐  ┌─────────────────────────┐   │   │
│  │             │    │  │ ColorDetector│  │EquipmentStatusManager │   │   │
│  └─────────────┘    │  │  (色検出)    │  │  (稼働状況判定)        │   │   │
│                     │  └──────┬──────┘  └───────────┬─────────────┘   │   │
│                     │         │                     │                  │   │
│                     │         ▼                     ▼                  │   │
│                     │  ┌─────────────┐  ┌─────────────────────────┐   │   │
│                     │  │ChangeDetector│  │    BlinkDetector       │   │   │
│                     │  │ (色変化検出) │  │    (点滅検出)          │   │   │
│                     │  └──────┬──────┘  └───────────┬─────────────┘   │   │
│                     │         │                     │                  │   │
│                     └─────────┼─────────────────────┼──────────────────┘   │
│                               │                     │                      │
│                               ▼                     ▼                      │
│                     ┌─────────────────┐   ┌─────────────────┐              │
│                     │   ColorLogger   │   │  MQTTPublisher  │              │
│                     │  (JSONLログ)    │   │   (MQTT送信)    │              │
│                     └────────┬────────┘   └────────┬────────┘              │
│                              │                     │                       │
└──────────────────────────────┼─────────────────────┼───────────────────────┘
                               │                     │
                               ▼                     ▼
                    ┌─────────────────┐    ┌─────────────────┐
                    │  ローカルファイル │    │   Mosquitto     │
                    │  ./color_logs/  │    │  (MQTT Broker)  │
                    │  ./equipment_logs│    └────────┬────────┘
                    └─────────────────┘              │
                                                     ▼
                                          ┌─────────────────┐
                                          │  Oracle Cloud   │
                                          │  (HF1RCM01)     │
                                          └─────────────────┘
```

## 2. ファイル構成

```
pose_detection/
├── color_change_detector.py    # メインアプリケーション
├── equipment_status.py         # 設備稼働状況モジュール
│
├── docs/
│   ├── spec_equipment_status_logger.md  # 仕様書
│   └── color_detector_architecture.md   # 本ドキュメント
│
├── oracle_env/                 # Python仮想環境（Oracle用）
│   └── bin/python
│
├── oracle_wallet/              # Oracle Cloud接続用ウォレット
│   ├── cwallet.sso
│   ├── tnsnames.ora
│   └── sqlnet.ora
│
├── color_logs_YYYYMMDD_HHMMSS/ # 色変化ログ（従来）
│   └── color_change_*.jsonl
│
└── equipment_logs/             # 設備稼働状況ログ
    └── status_YYYYMMDD.jsonl
```

## 3. クラス構成

### 3.1 color_change_detector.py

```
┌─────────────────────────────────────────────────────────────────┐
│                    ColorChangeDetectorApp                       │
│  - camera: CameraInput                                          │
│  - roi_manager: ROIManager                                      │
│  - color_detector: ColorDetector                                │
│  - change_detector: ChangeDetector                              │
│  - equipment_manager: EquipmentStatusManager  ← 新規追加        │
│  - mqtt_publisher: MQTTPublisher              ← 新規追加        │
│  - ui: UIRenderer                                               │
│  - logger: ColorLogger                                          │
├─────────────────────────────────────────────────────────────────┤
│  + run()                                                        │
│  + _init_equipment_status()                   ← 新規追加        │
│  + _on_equipment_status_change()              ← 新規追加        │
└─────────────────────────────────────────────────────────────────┘
         │
         │ uses
         ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   CameraInput   │  │   ROIManager    │  │  ColorDetector  │
│  - cap          │  │  - regions[]    │  │  - COLOR_RANGES │
│  + open()       │  │  + add()        │  │  + detect()     │
│  + read()       │  │  + remove()     │  │  + _get_color() │
│  + release()    │  │  + save/load()  │  └─────────────────┘
└─────────────────┘  └─────────────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │     Region      │
                     │  - id, name     │
                     │  - x, y, w, h   │
                     │  - threshold    │
                     │  - sta_no3  ← 新規│
                     │  - enabled  ← 新規│
                     └─────────────────┘
```

### 3.2 equipment_status.py

```
┌─────────────────────────────────────────────────────────────────┐
│                   EquipmentStatusManager                        │
│  - config: EquipmentConfig                                      │
│  - blink_detector: BlinkDetector                                │
│  - current_status: Dict[region_id, StatusCode]                  │
│  - on_status_change: Callback                                   │
├─────────────────────────────────────────────────────────────────┤
│  + update(region_id, color_name) → StatusCode                   │
│  + get_status(region_id) → StatusCode                           │
│  + get_status_name(region_id) → str                             │
│  + create_message(region_id, config) → StatusMessage            │
└─────────────────────────────────────────────────────────────────┘
         │
         │ uses
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BlinkDetector                              │
│  - config: BlinkConfig                                          │
│  - history: Dict[region_id, deque[(timestamp, color)]]          │
├─────────────────────────────────────────────────────────────────┤
│  + add_sample(region_id, color_name, timestamp_ms)              │
│  + get_state(region_id) → (dominant_color, is_blinking)         │
│  + reset(region_id)                                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              MQTTPublisher（ネットワーク障害対応版）              │
│  - config: MQTTConfig                                           │
│  - client: mqtt.Client                                          │
│  - connected: bool                                              │
│  - offline_queue: deque  ← オフラインキュー（最大1000件）        │
│  - stats: Dict           ← 送信統計                             │
├─────────────────────────────────────────────────────────────────┤
│  + connect() → bool                                             │
│  + publish(message, subtopic) → bool  ← オフライン時はキューへ   │
│  + try_reconnect()            ← 自動再接続                      │
│  + get_queue_size() → int                                       │
│  + get_stats() → Dict                                           │
│  + disconnect()               ← 終了時にキューをフラッシュ       │
└─────────────────────────────────────────────────────────────────┘
```

## 4. データフロー

### 4.1 色検出フロー

```
カメラフレーム
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  ColorDetector.detect(frame, region)                │
│    1. 領域(ROI)を切り出し                            │
│    2. 平均BGR色を計算                                │
│    3. HSVに変換                                     │
│    4. 色名を判定 (red/green/yellow/black/...)       │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼ ColorInfo(r,g,b,h,s,v,name)
                       │
        ┌──────────────┴──────────────┐
        ▼                             ▼
┌───────────────────┐      ┌───────────────────────────┐
│  ChangeDetector   │      │  EquipmentStatusManager   │
│  (色変化検出)      │      │  (稼働状況判定)            │
│                   │      │                           │
│  RGB距離 > 閾値?  │      │  BlinkDetector.add_sample │
│  デバウンス経過?  │      │  BlinkDetector.get_state  │
└────────┬──────────┘      │  _determine_status        │
         │                 └─────────────┬─────────────┘
         ▼                               ▼
   色変化イベント                   稼働状況コード
   ColorChangeEvent                EquipmentStatusCode
         │                               │
         ▼                               ▼
┌───────────────────┐      ┌───────────────────────────┐
│   ColorLogger     │      │  状態変化時:               │
│   (JSONLファイル)  │      │  - LocalStatusLogger      │
└───────────────────┘      │  - MQTTPublisher          │
                           └───────────────────────────┘
```

### 4.2 点滅検出フロー

```
時系列の色サンプル（2秒間のウィンドウ）
┌────────────────────────────────────────────────────────────┐
│ t=0    t=300  t=600  t=900  t=1200 t=1500 t=1800 t=2100   │
│ green  black  green  black  green  black  green  black    │
└────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  変化回数カウント      │
              │  green→black: 4回     │
              │  black→green: 3回     │
              │  合計: 7回            │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  点滅判定              │
              │  変化回数 ≥ 3?  → YES │
              │  間隔 100-1500ms? → YES│
              │  結果: 点滅           │
              └───────────┬───────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  稼働状況判定          │
              │  緑 + 点滅            │
              │  → 運転準備(1)        │
              └───────────────────────┘
```

## 5. 稼働状況コード判定ロジック

```
                    ┌─────────────┐
                    │  色を検出   │
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
      ┌────────┐      ┌────────┐      ┌────────┐
      │  赤    │      │ 黄/橙  │      │  緑    │
      └───┬────┘      └───┬────┘      └───┬────┘
          │               │               │
          ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ 異常中   │    │ 点滅?    │    │ 点滅?    │
    │   (14)   │    └────┬─────┘    └────┬─────┘
    └──────────┘         │               │
                    ┌────┴────┐     ┌────┴────┐
                    ▼         ▼     ▼         ▼
              ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
              │ 段換中 │ │通過運転│ │運転準備│ │自動運転│
              │  (16)  │ │  (3)   │ │  (1)   │ │  (2)   │
              │ 点滅   │ │ 点灯   │ │ 点滅   │ │ 点灯   │
              └────────┘ └────────┘ └────────┘ └────────┘
```

## 6. ネットワーク障害対応フロー

```
                    ┌─────────────────┐
                    │   publish()     │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  接続中？        │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │ Yes                         │ No
              ▼                             ▼
    ┌─────────────────┐           ┌─────────────────┐
    │  MQTT送信試行   │           │ オフラインキュー │
    └────────┬────────┘           │   に追加        │
             │                    │ (最大1000件)    │
             ▼                    └─────────────────┘
    ┌─────────────────┐
    │  送信成功？     │
    └────────┬────────┘
             │
    ┌────────┴────────┐
    │ Yes             │ No
    ▼                 ▼
  完了         ┌─────────────────┐
               │ オフラインキュー │
               │   に追加        │
               └─────────────────┘


【再接続時の動作】

┌─────────────────┐
│  接続復旧検出   │
│ (_on_connect)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ キューに         │
│ メッセージあり？ │
└────────┬────────┘
         │ Yes
         ▼
┌─────────────────┐
│  _flush_queue() │
│  キュー内の全    │
│  メッセージ送信  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  送信完了ログ   │
│  "X messages    │
│   sent"         │
└─────────────────┘


【データ保護の多重化】

    ┌─────────────────┐
    │  稼働状況変化    │
    └────────┬────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌─────────┐    ┌─────────────┐
│ローカル │    │   MQTT      │
│ファイル │    │  Publisher  │
│ (常に)  │    └──────┬──────┘
└─────────┘           │
                      ▼
              ┌─────────────────┐
              │  オンライン？    │
              └────────┬────────┘
                       │
          ┌────────────┴────────────┐
          │ Yes                     │ No
          ▼                         ▼
    ┌──────────┐            ┌──────────────┐
    │ 即時送信 │            │オフライン    │
    │ Mosquitto│            │キュー        │
    └──────────┘            │(メモリ内)    │
                            └──────────────┘
                                   │
                                   ▼ 接続復旧時
                            ┌──────────────┐
                            │ 自動送信     │
                            └──────────────┘
```

### 障害対応まとめ

| 障害パターン | 対応 | データ |
|-------------|------|--------|
| 一時的なネットワーク断 | オフラインキュー → 復旧時送信 | 失われない |
| 長時間のネットワーク断 | キュー（1000件）+ ローカルファイル | 失われない |
| キュー溢れ | 古いメッセージを破棄、ローカルには残る | ローカルに残る |
| Mosquitto停止 | オフラインキュー + ローカルファイル | 失われない |
| アプリ異常終了 | ローカルファイルに残る | 部分的に残る |

## 7. MQTTメッセージ形式

### 6.1 トピック

```
equipment/status/{STA_NO3}

例: equipment/status/EQ001
```

### 6.2 ペイロード（JSON）

```json
{
  "mk_date": "20260205143025",
  "sta_no1": "PLANT01",
  "sta_no2": "LINE01",
  "sta_no3": "EQ001",
  "t1_status": 2,
  "color_name": "green",
  "is_blinking": false
}
```

## 7. コマンドライン引数

| 引数 | 説明 | デフォルト |
|------|------|-----------|
| `-i, --input` | 入力ソース (usb, rpi, /dev/videoX, file.mp4) | usb |
| `-c, --config` | 領域設定ファイル | None |
| `-t, --threshold` | 色変化検出閾値 | 30 |
| `-d, --debounce` | デバウンス時間(ms) | 500 |
| `--mqtt` | MQTT送信有効化 | False |
| `--mqtt-broker` | MQTTブローカーホスト | localhost |
| `--mqtt-port` | MQTTブローカーポート | 1883 |
| `--mqtt-topic` | MQTTトピック | equipment/status |
| `--sta-no1` | ステーション番号1（工場コード） | "" |
| `--sta-no2` | ステーション番号2（ラインコード） | "" |

## 8. 起動例

```bash
# 基本（色変化検出のみ）
python3 color_change_detector.py -i usb

# MQTT有効（設備稼働状況送信）
python3 color_change_detector.py -i usb \
  --mqtt \
  --sta-no1 PLANT01 \
  --sta-no2 LINE01

# 設定ファイル使用
python3 color_change_detector.py -i usb \
  -c equipment_config.json \
  --mqtt
```

## 9. ログファイル形式

### 9.1 色変化ログ（./color_logs_*/）

```jsonl
{"timestamp":"2026-02-05T14:30:25","frame_number":150,"event_type":"color_change","region_id":1,"region_name":"設備A","prev_color":{"r":0,"g":255,"b":0,"name":"green"},"current_color":{"r":0,"g":0,"b":0,"name":"black"}}
```

### 9.2 設備稼働状況ログ（./equipment_logs/）

```jsonl
{"mk_date":"20260205143025","sta_no1":"PLANT01","sta_no2":"LINE01","sta_no3":"EQ001","t1_status":2,"color_name":"green","is_blinking":false}
{"mk_date":"20260205143130","sta_no1":"PLANT01","sta_no2":"LINE01","sta_no3":"EQ001","t1_status":1,"color_name":"green","is_blinking":true}
```

## 10. Oracle DBテーブル構造

```sql
CREATE TABLE HF1RCM01 (
    MK_DATE   VARCHAR2(14) NOT NULL,  -- YYYYMMDDhhmmss
    STA_NO1   VARCHAR2(10),           -- 工場コード
    STA_NO2   VARCHAR2(10),           -- ラインコード
    STA_NO3   VARCHAR2(10),           -- 設備コード
    T1_STATUS NUMBER(2),              -- 稼働状況コード
    CONSTRAINT PK_HF1RCM01 PRIMARY KEY (MK_DATE, STA_NO3)
);
```
