# Circle Detector 基本設計書（SDD）

## 1. システム概要

### 1.1 システム構成図

#### 1.1.1 分散構成（推奨）
複数のカメラ機（子機）と中継機（親機）による構成。

```
┌─────────────────────────────────────────────────────────────────────────┐
│  【子機】Raspberry Pi（カメラ機）× 複数台                               │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ ブラウザ (http://子機IP:5000)                                      │ │
│  │ ┌─────────────────────────────────────────────────────────────┐   │ │
│  │ │ Circle Detector Web UI                                       │   │ │
│  │ │ ・円の設定、色登録、ルール設定                               │   │ │
│  │ │ ・カメラ映像表示（MJPEG）                                    │   │ │
│  │ └─────────────────────────────────────────────────────────────┘   │ │
│  │                              │                                     │ │
│  │                              ▼                                     │ │
│  │ ┌─────────────────────────────────────────────────────────────┐   │ │
│  │ │ Flask + CameraManager + DetectionEngine + RuleEngine         │   │ │
│  │ └─────────────────────────────────────────────────────────────┘   │ │
│  │                              │                                     │ │
│  │                              ▼                                     │ │
│  │ ┌─────────────────────────────────────────────────────────────┐   │ │
│  │ │ MQTTSender → MQTT Broker（中継機）                           │   │ │
│  │ │ ※通信障害時は queue/pending_circle.jsonl に一時保存          │   │ │
│  │ └─────────────────────────────────────────────────────────────┘   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│        ↓ MQTT                  ↓ MQTT                  ↓ MQTT          │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  【親機】Raspberry Pi（中継機）                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Mosquitto (MQTT Broker)                                            │ │
│  │ ・複数の子機からのデータを受信                                     │ │
│  │ ・トピック: equipment/status/{sta_no3}                            │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ mqtt_oracle_bridge.py                                              │ │
│  │ ・MQTTメッセージをOracle DBに保存                                  │ │
│  │ ・通信障害時は queue/pending_oracle.jsonl に一時保存               │ │
│  └───────────────────────────────────────────────────────────────────┘ │
│                              │                                          │
│                              ▼                                          │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │ Oracle Cloud DB (HF1RCM01)                                         │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 1.1.2 単体構成（開発・テスト用）
1台のRaspberry Piで全機能を実行。

```
┌─────────────────────────────────────────────────────────────────┐
│  1台のRaspberry Pi                                               │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ ブラウザ (http://localhost:5000)                         │    │
│  │ Circle Detector Web UI                                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Flask + Camera + Detection + Rule                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ MQTTSender → Mosquitto (localhost)                       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ mqtt_oracle_bridge.py → Oracle Cloud DB                  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

#### 1.1.3 モジュール構成図

```
┌─────────────────────────────────────────────────────────────────┐
│                        クライアント（ブラウザ）                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  HTML/CSS/JavaScript                                     │   │
│  │  ・Canvas（円描画・操作）                                 │   │
│  │  ・設定パネル                                            │   │
│  │  ・MJPEG映像表示（<img>タグ）                            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/REST API
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Flask Webサーバー (Port 5000)               │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────────────┐  │
│  │ ルーティング   │ │ API エンド    │ │ MJPEG ストリーム      │  │
│  │ (app.py)      │ │ ポイント      │ │ (/video_feed)         │  │
│  └───────────────┘ └───────────────┘ └───────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐
│ CameraManager   │ │ ConfigManager   │ │ DetectionEngine         │
│ ・カメラ制御    │ │ ・設定読み書き  │ │ ・色検出                │
│ ・フレーム取得  │ │ ・JSON管理      │ │ ・点滅検出              │
│ ・MJPEG生成     │ │                 │ │ ・ルール評価            │
└─────────────────┘ └─────────────────┘ └─────────────────────────┘
                                                  │
                                                  ▼
                                        ┌─────────────────────────┐
                                        │ MQTTSender              │
                                        │ ・MQTT送信              │
                                        │ ・キュー管理（障害時）   │
                                        │ ・5秒ごとにリトライ     │
                                        └─────────────────────────┘
                                                  │
                                                  ▼ MQTT
                                        ┌─────────────────────────┐
                                        │ mqtt_oracle_bridge.py   │
                                        │ (中継機で稼働)          │
                                        └─────────────────────────┘
                                                  │
                                                  ▼
                                        ┌─────────────────────────┐
                                        │ Oracle DB (HF1RCM01)    │
                                        └─────────────────────────┘
```

---

## 2. モジュール設計

### 2.1 モジュール一覧

| モジュール | ファイル | 責務 |
|-----------|----------|------|
| App | app.py | Flaskアプリケーション、ルーティング |
| CameraManager | camera.py | カメラ制御、MJPEG配信 |
| ConfigManager | config_manager.py | 設定ファイル管理 |
| DetectionEngine | detector.py | 色検出、点滅検出 |
| RuleEngine | rule_engine.py | マッピングルール評価 |
| MQTTSender | mqtt_sender.py | MQTT送信、キュー管理 |
| Frontend | static/js/main.js | UI操作、API通信 |

---

## 3. クラス設計

### 3.1 データクラス

```python
@dataclass
class Circle:
    """円領域"""
    id: int
    name: str
    center_x: int
    center_y: int
    radius: int
    group_id: Optional[int]
    colors: List[ColorRange]

@dataclass
class ColorRange:
    """色の範囲定義"""
    name: str
    h_center: int      # 0-179
    h_range: int       # 許容範囲
    s_min: int         # 0-255
    s_max: int
    v_min: int         # 0-255
    v_max: int

@dataclass
class Group:
    """グループ（パトライト）"""
    id: int
    name: str
    sta_no2: str
    sta_no3: str
    default_value: int
    circle_ids: List[int]

@dataclass
class Rule:
    """マッピングルール"""
    id: int
    group_id: int
    priority: int
    type: str          # "single" or "composite"
    conditions: List[RuleCondition]
    value: int

@dataclass
class RuleCondition:
    """ルール条件"""
    circle_id: int
    color: str
    blinking: bool

@dataclass
class DetectionResult:
    """検出結果"""
    circle_id: int
    detected_color: Optional[str]
    is_blinking: bool
    raw_hsv: Tuple[int, int, int]

@dataclass
class SendData:
    """送信データ"""
    mk_date: str
    sta_no1: str
    sta_no2: str
    sta_no3: str
    t1_status: int
```

---

### 3.2 CameraManager クラス

```python
class CameraManager:
    """カメラ管理クラス"""

    def __init__(self, device: str = "usb", width: int = 640, height: int = 480):
        self.device = device
        self.width = width
        self.height = height
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame: Optional[np.ndarray] = None
        self.lock = threading.Lock()
        self.running = False

    def start(self) -> bool:
        """カメラを開始"""
        pass

    def stop(self):
        """カメラを停止"""
        pass

    def get_frame(self) -> Optional[np.ndarray]:
        """現在のフレームを取得"""
        pass

    def generate_mjpeg(self) -> Generator[bytes, None, None]:
        """MJPEGストリームを生成"""
        pass

    def get_color_at(self, x: int, y: int, radius: int = 5) -> Tuple[int, int, int]:
        """指定位置の平均色（HSV）を取得"""
        pass
```

---

### 3.3 ConfigManager クラス

```python
class ConfigManager:
    """設定管理クラス"""

    CONFIG_PATH = "config/circle_detector.json"

    def __init__(self):
        self.config: dict = {}
        self.circles: List[Circle] = []
        self.groups: List[Group] = []
        self.rules: List[Rule] = []

    def load(self) -> bool:
        """設定ファイルを読み込み"""
        pass

    def save(self) -> bool:
        """設定ファイルに保存"""
        pass

    def add_circle(self, circle: Circle) -> int:
        """円を追加、IDを返す"""
        pass

    def update_circle(self, circle: Circle) -> bool:
        """円を更新"""
        pass

    def delete_circle(self, circle_id: int) -> bool:
        """円を削除"""
        pass

    def add_group(self, group: Group) -> int:
        """グループを追加"""
        pass

    def update_group(self, group: Group) -> bool:
        """グループを更新"""
        pass

    def delete_group(self, group_id: int) -> bool:
        """グループを削除"""
        pass

    def add_rule(self, rule: Rule) -> int:
        """ルールを追加"""
        pass

    def update_rule(self, rule: Rule) -> bool:
        """ルールを更新"""
        pass

    def delete_rule(self, rule_id: int) -> bool:
        """ルールを削除"""
        pass

    def get_sta_no1_options(self) -> List[str]:
        """STA_NO1の選択肢を取得"""
        pass

    def to_dict(self) -> dict:
        """設定を辞書形式で取得（API用）"""
        pass
```

---

### 3.4 DetectionEngine クラス

```python
class DetectionEngine:
    """色検出エンジン"""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.blink_history: Dict[int, deque] = {}  # circle_id -> 履歴
        self.last_colors: Dict[int, str] = {}      # circle_id -> 最後の色

    def detect_circle(self, frame: np.ndarray, circle: Circle) -> DetectionResult:
        """1つの円の色を検出"""
        pass

    def detect_all(self, frame: np.ndarray) -> List[DetectionResult]:
        """全円の色を検出"""
        pass

    def _get_circle_region(self, frame: np.ndarray, circle: Circle) -> np.ndarray:
        """円領域を切り出し"""
        pass

    def _match_color(self, hsv: Tuple[int, int, int], colors: List[ColorRange]) -> Optional[str]:
        """HSV値を登録色とマッチング"""
        pass

    def _detect_blink(self, circle_id: int, current_color: str) -> bool:
        """点滅を検出"""
        pass
```

---

### 3.5 RuleEngine クラス

```python
class RuleEngine:
    """マッピングルール評価エンジン"""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager

    def evaluate(self, group: Group, results: List[DetectionResult]) -> int:
        """グループのルールを評価し、送信値を決定"""
        pass

    def _evaluate_rule(self, rule: Rule, results: List[DetectionResult]) -> bool:
        """1つのルールを評価"""
        pass

    def _evaluate_single(self, rule: Rule, results: List[DetectionResult]) -> bool:
        """単一円ルールを評価"""
        pass

    def _evaluate_composite(self, rule: Rule, results: List[DetectionResult]) -> bool:
        """複合ルールを評価"""
        pass

    def evaluate_all_groups(self, results: List[DetectionResult]) -> Dict[int, int]:
        """全グループを評価、{group_id: value}を返す"""
        pass
```

---

### 3.6 MQTTSender クラス

```python
class MQTTSender:
    """MQTT送信クラス"""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.queue = FileQueue("queue/pending_circle.jsonl")

    def connect(self) -> bool:
        """MQTTブローカーに接続"""
        pass

    def disconnect(self):
        """切断"""
        pass

    def send(self, data: SendData) -> bool:
        """データを送信（失敗時はキュー保存）"""
        pass

    def _on_connect(self, client, userdata, flags, rc):
        """接続コールバック"""
        pass

    def _on_disconnect(self, client, userdata, rc):
        """切断コールバック"""
        pass

    def process_queue(self):
        """キューを処理（バックグラウンド）"""
        pass
```

---

## 4. API設計

### 4.1 REST API 一覧

| メソッド | エンドポイント | 説明 |
|----------|----------------|------|
| GET | /api/config | 現在の設定を取得 |
| POST | /api/config | 設定を保存 |
| GET | /api/circles | 円一覧を取得 |
| POST | /api/circles | 円を追加 |
| PUT | /api/circles/{id} | 円を更新 |
| DELETE | /api/circles/{id} | 円を削除 |
| GET | /api/groups | グループ一覧を取得 |
| POST | /api/groups | グループを追加 |
| PUT | /api/groups/{id} | グループを更新 |
| DELETE | /api/groups/{id} | グループを削除 |
| GET | /api/rules | ルール一覧を取得 |
| POST | /api/rules | ルールを追加 |
| PUT | /api/rules/{id} | ルールを更新 |
| DELETE | /api/rules/{id} | ルールを削除 |
| GET | /api/status | 現在の検出状態を取得 |
| POST | /api/run/start | 実行モード開始 |
| POST | /api/run/stop | 実行モード停止 |
| GET | /api/color/{x}/{y} | 指定座標の色を取得 |
| GET | /video_feed | MJPEG映像ストリーム |

---

### 4.2 API詳細

#### GET /api/config
```json
// Response
{
  "station": {
    "sta_no1": "PLANT01",
    "sta_no1_options": ["PLANT01", "PLANT02"]
  },
  "detection": {
    "send_mode": "on_change",
    "send_interval_sec": 1,
    "show_video_in_run_mode": true
  },
  "circles": [...],
  "groups": [...],
  "rules": [...]
}
```

#### POST /api/circles
```json
// Request
{
  "name": "ランプ1",
  "center_x": 100,
  "center_y": 100,
  "radius": 25,
  "group_id": 1
}

// Response
{
  "success": true,
  "id": 1
}
```

#### GET /api/status
```json
// Response
{
  "running": true,
  "results": [
    {
      "circle_id": 1,
      "detected_color": "赤",
      "is_blinking": false
    }
  ],
  "group_values": {
    "1": 10,
    "2": 20
  },
  "last_send": "2026-02-11T15:30:00"
}
```

#### GET /api/color/{x}/{y}
```json
// Response
{
  "x": 100,
  "y": 100,
  "hsv": [0, 200, 255],
  "rgb": [255, 50, 50],
  "suggested_name": "赤"
}
```

---

## 5. デザインシステム

### 5.1 Serendie Design System 適用方針

本アプリケーションは、三菱電機のSerendie Design Systemのデザイン原則に準拠したUIを実装する。
Flask + vanilla JavaScript構成のため、Reactコンポーネントは使用せず、デザイントークンとスタイルガイドを適用する。

#### 5.1.1 参照リソース
| リソース | URL | 用途 |
|----------|-----|------|
| ガイドライン | https://serendie.design | デザイン原則 |
| Storybook | https://storybook.serendie.design | コンポーネント参考 |
| Design Tokens | @serendie/design-token | カラー・スペーシング定義 |

#### 5.1.2 ブランドアイデンティティ
- **適応性（Adaptive）**: 画面サイズに応じた自動レイアウト調整
- **一貫性（Consistency）**: 統一されたカラー・タイポグラフィ
- **アクセシビリティ**: ARIA属性、キーボードナビゲーション対応

#### 5.1.3 デザイントークン（CSS変数）
```css
:root {
  /* カラー */
  --sd-color-primary: #0066CC;
  --sd-color-primary-hover: #0052A3;
  --sd-color-secondary: #6B7280;
  --sd-color-success: #10B981;
  --sd-color-warning: #F59E0B;
  --sd-color-error: #EF4444;
  --sd-color-background: #FFFFFF;
  --sd-color-surface: #F9FAFB;
  --sd-color-border: #E5E7EB;
  --sd-color-text-primary: #111827;
  --sd-color-text-secondary: #6B7280;

  /* スペーシング（8pxベースグリッド） */
  --sd-spacing-0: 0;
  --sd-spacing-1: 4px;
  --sd-spacing-2: 8px;
  --sd-spacing-3: 12px;
  --sd-spacing-4: 16px;
  --sd-spacing-5: 20px;
  --sd-spacing-6: 24px;
  --sd-spacing-8: 32px;
  --sd-spacing-10: 40px;
  --sd-spacing-12: 48px;

  /* タイポグラフィ */
  --sd-font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  --sd-font-size-xs: 12px;
  --sd-font-size-sm: 14px;
  --sd-font-size-md: 16px;
  --sd-font-size-lg: 18px;
  --sd-font-size-xl: 20px;
  --sd-font-size-2xl: 24px;
  --sd-font-weight-normal: 400;
  --sd-font-weight-medium: 500;
  --sd-font-weight-bold: 700;

  /* ボーダー */
  --sd-radius-sm: 4px;
  --sd-radius-md: 8px;
  --sd-radius-lg: 12px;
  --sd-radius-full: 9999px;

  /* シャドウ */
  --sd-shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
  --sd-shadow-md: 0 4px 6px rgba(0, 0, 0, 0.1);
  --sd-shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.1);

  /* トランジション */
  --sd-transition-fast: 150ms ease;
  --sd-transition-normal: 200ms ease;
  --sd-transition-slow: 300ms ease;
}

/* ダークモード（将来対応用） */
@media (prefers-color-scheme: dark) {
  :root {
    --sd-color-background: #111827;
    --sd-color-surface: #1F2937;
    --sd-color-border: #374151;
    --sd-color-text-primary: #F9FAFB;
    --sd-color-text-secondary: #9CA3AF;
  }
}
```

#### 5.1.4 レスポンシブブレークポイント
| 画面サイズ | 分類 | レイアウト |
|-----------|------|-----------|
| 1024px以上 | PC/タブレット横 | 2カラム（映像+設定パネル横並び） |
| 768px〜1023px | タブレット縦 | 2カラム（設定パネル縮小） |
| 767px以下 | スマートフォン | 1カラム（縦積み+タブ切替） |

#### 5.1.5 コンポーネントスタイル指針

**ボタン**
```css
.btn {
  font-family: var(--sd-font-family);
  font-size: var(--sd-font-size-sm);
  font-weight: var(--sd-font-weight-medium);
  padding: var(--sd-spacing-2) var(--sd-spacing-4);
  border-radius: var(--sd-radius-md);
  transition: all var(--sd-transition-fast);
  cursor: pointer;
}

.btn-primary {
  background: var(--sd-color-primary);
  color: white;
  border: none;
}

.btn-primary:hover {
  background: var(--sd-color-primary-hover);
}

.btn-secondary {
  background: var(--sd-color-surface);
  color: var(--sd-color-text-primary);
  border: 1px solid var(--sd-color-border);
}
```

**カード**
```css
.card {
  background: var(--sd-color-background);
  border: 1px solid var(--sd-color-border);
  border-radius: var(--sd-radius-lg);
  box-shadow: var(--sd-shadow-sm);
  padding: var(--sd-spacing-4);
}
```

**フォーム要素**
```css
.input, .select {
  font-family: var(--sd-font-family);
  font-size: var(--sd-font-size-sm);
  padding: var(--sd-spacing-2) var(--sd-spacing-4);
  border: 1px solid var(--sd-color-border);
  border-radius: var(--sd-radius-md);
  transition: border-color var(--sd-transition-fast);
}

.input:focus, .select:focus {
  outline: none;
  border-color: var(--sd-color-primary);
  box-shadow: 0 0 0 3px rgba(0, 102, 204, 0.1);
}
```

#### 5.1.6 アニメーション指針
| 用途 | 時間 | イージング |
|------|------|-----------|
| ホバー効果 | 150ms | ease |
| フェードイン/アウト | 200ms | ease |
| ダイアログ表示 | 200ms | ease-out |
| トースト通知 | 300ms | ease |

#### 5.1.7 アクセシビリティ
- **キーボード操作**: Tab/Shift+Tab でフォーカス移動、Enter/Space で操作
- **ARIA属性**: ダイアログ(role="dialog")、ボタン(aria-label)、ステータス(aria-live)
- **コントラスト比**: テキスト 4.5:1 以上、アイコン 3:1 以上
- **フォーカスインジケータ**: 明確なフォーカスリング表示

---

## 6. 画面設計詳細

### 6.1 画面遷移図
```
┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │
│   編集モード    │ ←→  │   実行モード    │
│                 │     │                 │
└─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐
│ 色設定ダイアログ │
└─────────────────┘
┌─────────────────┐
│ルール設定ダイアログ│
└─────────────────┘
```

### 6.2 コンポーネント構成

```
App
├── Header
│   ├── Title
│   ├── ModeToggle (編集/実行)
│   └── ConnectionStatus
├── MainContent
│   ├── VideoPanel
│   │   ├── MJPEGStream
│   │   └── CircleOverlay (Canvas)
│   └── SettingsPanel
│       ├── StationSettings
│       │   └── STA_NO1 Dropdown
│       ├── GroupList
│       │   └── GroupItem
│       │       ├── GroupInfo (STA_NO2, STA_NO3)
│       │       └── RuleButton
│       └── CircleEditor (選択中の円)
│           ├── CircleInfo
│           ├── ColorList
│           └── DeleteButton
├── Dialogs
│   ├── ColorPickerDialog
│   └── RuleEditorDialog
└── Footer
    ├── SaveButton
    ├── LoadButton
    └── StatusBar
```

---

## 7. 処理フロー

### 7.1 円作成フロー
```
1. ユーザーがカメラ映像上でマウスダウン
2. マウスダウン位置を中心点として記録
3. マウス移動中、中心点からの距離を半径として描画
4. マウスアップで半径確定
5. POST /api/circles で円を保存
6. 設定パネルに円情報を表示
```

### 7.2 色登録フロー
```
1. 円を選択
2. 「色を追加」ボタンクリック
3. ColorPickerDialog表示
4. 方法A: 「画面から取得」
   - カメラ映像上でクリック
   - GET /api/color/{x}/{y} で色取得
   - HSV範囲を自動設定
5. 方法B: カラーパレット
   - HSV/RGBを手動入力
6. 色名を入力
7. 保存
```

### 7.3 実行モードフロー
```
1. POST /api/run/start
2. バックグラウンドスレッド開始
3. ループ:
   a. フレーム取得
   b. 全円の色を検出 (DetectionEngine.detect_all)
   c. 点滅判定
   d. ルール評価 (RuleEngine.evaluate_all_groups)
   e. 前回と値が変化した場合（or 定期送信）:
      - MQTTSender.send()
   f. フロントに状態を通知（WebSocket or ポーリング）
4. POST /api/run/stop で停止
```

### 7.4 送信フロー
```
1. RuleEngineから送信値を受け取る
2. SendData作成
   - mk_date: 現在時刻 (YYYYMMDDHHmmss)
   - sta_no1: 設定から
   - sta_no2, sta_no3: グループから
   - t1_status: 評価結果
3. MQTT送信試行
4. 成功: ログ記録
5. 失敗: FileQueueに保存
6. バックグラウンドでキュー再送
```

---

## 8. データフロー

### 8.1 編集モード
```
[ユーザー操作]
      │
      ▼
[Frontend (JavaScript)]
      │
      ▼ REST API
[Flask (app.py)]
      │
      ▼
[ConfigManager]
      │
      ▼
[circle_detector.json]
```

### 8.2 実行モード
```
[CameraManager] ─── フレーム ──→ [DetectionEngine]
                                      │
                                      ▼ 検出結果
                                 [RuleEngine]
                                      │
                                      ▼ 送信値
                                 [MQTTSender]
                                      │
                                      ▼
                            [mqtt_oracle_bridge.py]
                                      │
                                      ▼
                                 [Oracle DB]
```

---

## 9. エラー処理

### 9.1 カメラエラー
| エラー | 処理 |
|--------|------|
| カメラ未接続 | エラーメッセージ表示、再接続ボタン |
| フレーム取得失敗 | 最後のフレームを使用、リトライ |

### 9.2 MQTT エラー
| エラー | 処理 |
|--------|------|
| 接続失敗 | キューに保存、バックグラウンドでリトライ |
| 送信失敗 | キューに保存 |

### 9.3 設定エラー
| エラー | 処理 |
|--------|------|
| JSON読み込み失敗 | デフォルト設定を使用 |
| バリデーションエラー | エラーメッセージ表示 |

---

## 10. セキュリティ考慮

### 10.1 ローカル運用前提
- 外部公開しない（localhost のみ）
- 認証機能は実装しない

### 10.2 入力バリデーション
- 円の座標: 画面サイズ内
- 半径: 1以上、画面サイズ/2以下
- 文字列: エスケープ処理

---

## 11. テスト計画

### 11.1 単体テスト
| モジュール | テスト内容 |
|-----------|-----------|
| DetectionEngine | 色検出精度、点滅検出 |
| RuleEngine | 単一/複合ルール評価 |
| ConfigManager | 設定読み書き |

### 11.2 結合テスト
| テスト | 内容 |
|--------|------|
| API | 全エンドポイントのリクエスト/レスポンス |
| 実行モード | 検出→評価→送信の一連フロー |

### 11.3 システムテスト
| テスト | 内容 |
|--------|------|
| 編集操作 | 円の作成/編集/削除 |
| 長時間稼働 | 1時間連続稼働 |
| 障害復旧 | MQTT切断→再接続 |

---

## 12. 実装スケジュール

| フェーズ | 内容 |
|---------|------|
| Phase 1 | バックエンド基盤（Flask, Camera, Config） |
| Phase 2 | フロントエンド基盤（映像表示, 円描画） |
| Phase 3 | 色検出・ルールエンジン |
| Phase 4 | MQTT送信連携 |
| Phase 5 | テスト・調整 |

---

## 13. 変更履歴

| 日付 | バージョン | 変更内容 |
|------|------------|----------|
| 2026-02-11 | 1.0 | 初版作成 |
| 2026-02-11 | 1.1 | 分散構成（子機・親機）アーキテクチャ追加 |
| 2026-02-11 | 1.2 | Serendie Design System適用方針追加（セクション5） |
| 2026-02-11 | 1.3 | ドキュメント整合性修正（デザイントークン番号形式統一、CameraManager引数追加） |
