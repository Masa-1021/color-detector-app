# Circle Detector 詳細設計書

## 1. フロントエンド詳細設計

### 1.0 Serendie Design System 適用

#### 1.0.0 概要
本アプリケーションは三菱電機のSerendie Design Systemのデザイン原則に準拠する。
Flask + vanilla JavaScript構成のため、CSS変数によるデザイントークン方式で実装する。

#### 1.0.1 CSS変数定義（style.css冒頭）
```css
/**
 * Serendie Design System - Design Tokens
 * Reference: https://serendie.design
 */
:root {
  /* === Colors === */
  /* Primary */
  --sd-color-primary: #0066CC;
  --sd-color-primary-hover: #0052A3;
  --sd-color-primary-active: #003D7A;
  --sd-color-primary-light: #E6F0FA;

  /* Secondary */
  --sd-color-secondary: #6B7280;
  --sd-color-secondary-hover: #4B5563;

  /* Semantic */
  --sd-color-success: #10B981;
  --sd-color-success-light: #D1FAE5;
  --sd-color-warning: #F59E0B;
  --sd-color-warning-light: #FEF3C7;
  --sd-color-error: #EF4444;
  --sd-color-error-light: #FEE2E2;
  --sd-color-info: #3B82F6;
  --sd-color-info-light: #DBEAFE;

  /* Neutral */
  --sd-color-background: #FFFFFF;
  --sd-color-surface: #F9FAFB;
  --sd-color-surface-hover: #F3F4F6;
  --sd-color-border: #E5E7EB;
  --sd-color-border-strong: #D1D5DB;
  --sd-color-text-primary: #111827;
  --sd-color-text-secondary: #6B7280;
  --sd-color-text-disabled: #9CA3AF;
  --sd-color-text-inverse: #FFFFFF;

  /* === Spacing (8px base grid) === */
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
  --sd-spacing-16: 64px;

  /* === Typography === */
  --sd-font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Hiragino Sans',
                    'Noto Sans JP', Roboto, 'Helvetica Neue', Arial, sans-serif;
  --sd-font-family-mono: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono',
                         'Source Code Pro', monospace;

  --sd-font-size-xs: 0.75rem;   /* 12px */
  --sd-font-size-sm: 0.875rem;  /* 14px */
  --sd-font-size-md: 1rem;      /* 16px */
  --sd-font-size-lg: 1.125rem;  /* 18px */
  --sd-font-size-xl: 1.25rem;   /* 20px */
  --sd-font-size-2xl: 1.5rem;   /* 24px */
  --sd-font-size-3xl: 1.875rem; /* 30px */

  --sd-font-weight-normal: 400;
  --sd-font-weight-medium: 500;
  --sd-font-weight-semibold: 600;
  --sd-font-weight-bold: 700;

  --sd-line-height-tight: 1.25;
  --sd-line-height-normal: 1.5;
  --sd-line-height-relaxed: 1.75;

  /* === Border Radius === */
  --sd-radius-none: 0;
  --sd-radius-sm: 4px;
  --sd-radius-md: 8px;
  --sd-radius-lg: 12px;
  --sd-radius-xl: 16px;
  --sd-radius-full: 9999px;

  /* === Shadows === */
  --sd-shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --sd-shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  --sd-shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
  --sd-shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);

  /* === Transitions === */
  --sd-transition-fast: 150ms ease;
  --sd-transition-normal: 200ms ease;
  --sd-transition-slow: 300ms ease;
  --sd-transition-colors: color 150ms ease, background-color 150ms ease, border-color 150ms ease;

  /* === Z-Index === */
  --sd-z-dropdown: 1000;
  --sd-z-sticky: 1020;
  --sd-z-fixed: 1030;
  --sd-z-modal-backdrop: 1040;
  --sd-z-modal: 1050;
  --sd-z-popover: 1060;
  --sd-z-tooltip: 1070;
  --sd-z-toast: 1080;
}

/* Dark Mode (future support) */
[data-theme="dark"] {
  --sd-color-background: #0F172A;
  --sd-color-surface: #1E293B;
  --sd-color-surface-hover: #334155;
  --sd-color-border: #334155;
  --sd-color-border-strong: #475569;
  --sd-color-text-primary: #F1F5F9;
  --sd-color-text-secondary: #94A3B8;
  --sd-color-text-disabled: #64748B;
  --sd-color-primary-light: #1E3A5F;
}
```

#### 1.0.2 基本コンポーネントスタイル
```css
/* === Reset & Base === */
*, *::before, *::after {
  box-sizing: border-box;
}

body {
  font-family: var(--sd-font-family);
  font-size: var(--sd-font-size-md);
  line-height: var(--sd-line-height-normal);
  color: var(--sd-color-text-primary);
  background-color: var(--sd-color-background);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* === Buttons === */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--sd-spacing-2);
  padding: var(--sd-spacing-2) var(--sd-spacing-4);
  font-family: var(--sd-font-family);
  font-size: var(--sd-font-size-sm);
  font-weight: var(--sd-font-weight-medium);
  line-height: var(--sd-line-height-tight);
  border-radius: var(--sd-radius-md);
  border: 1px solid transparent;
  cursor: pointer;
  transition: var(--sd-transition-colors), box-shadow var(--sd-transition-fast);
  white-space: nowrap;
}

.btn:focus-visible {
  outline: 2px solid var(--sd-color-primary);
  outline-offset: 2px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background-color: var(--sd-color-primary);
  color: var(--sd-color-text-inverse);
}

.btn-primary:hover:not(:disabled) {
  background-color: var(--sd-color-primary-hover);
}

.btn-primary:active:not(:disabled) {
  background-color: var(--sd-color-primary-active);
}

.btn-secondary {
  background-color: var(--sd-color-surface);
  color: var(--sd-color-text-primary);
  border-color: var(--sd-color-border);
}

.btn-secondary:hover:not(:disabled) {
  background-color: var(--sd-color-surface-hover);
  border-color: var(--sd-color-border-strong);
}

.btn-danger {
  background-color: var(--sd-color-error);
  color: var(--sd-color-text-inverse);
}

.btn-danger:hover:not(:disabled) {
  background-color: #DC2626;
}

.btn-icon {
  padding: var(--sd-spacing-2);
}

.btn-sm {
  padding: var(--sd-spacing-1) var(--sd-spacing-3);
  font-size: var(--sd-font-size-xs);
}

.btn-lg {
  padding: var(--sd-spacing-3) var(--sd-spacing-6);
  font-size: var(--sd-font-size-md);
}

/* === Form Elements === */
.form-group {
  margin-bottom: var(--sd-spacing-4);
}

.form-label {
  display: block;
  margin-bottom: var(--sd-spacing-1);
  font-size: var(--sd-font-size-sm);
  font-weight: var(--sd-font-weight-medium);
  color: var(--sd-color-text-secondary);
}

.form-input,
.form-select {
  width: 100%;
  padding: var(--sd-spacing-2) var(--sd-spacing-3);
  font-family: var(--sd-font-family);
  font-size: var(--sd-font-size-sm);
  color: var(--sd-color-text-primary);
  background-color: var(--sd-color-background);
  border: 1px solid var(--sd-color-border);
  border-radius: var(--sd-radius-md);
  transition: var(--sd-transition-colors), box-shadow var(--sd-transition-fast);
}

.form-input:hover,
.form-select:hover {
  border-color: var(--sd-color-border-strong);
}

.form-input:focus,
.form-select:focus {
  outline: none;
  border-color: var(--sd-color-primary);
  box-shadow: 0 0 0 3px var(--sd-color-primary-light);
}

.form-input::placeholder {
  color: var(--sd-color-text-disabled);
}

/* === Cards === */
.card {
  background-color: var(--sd-color-background);
  border: 1px solid var(--sd-color-border);
  border-radius: var(--sd-radius-lg);
  box-shadow: var(--sd-shadow-sm);
}

.card-header {
  padding: var(--sd-spacing-4);
  border-bottom: 1px solid var(--sd-color-border);
}

.card-body {
  padding: var(--sd-spacing-4);
}

.card-footer {
  padding: var(--sd-spacing-4);
  border-top: 1px solid var(--sd-color-border);
  background-color: var(--sd-color-surface);
}

/* === Dialogs/Modals === */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background-color: rgba(0, 0, 0, 0.5);
  z-index: var(--sd-z-modal-backdrop);
  animation: fadeIn var(--sd-transition-normal);
}

.modal {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background-color: var(--sd-color-background);
  border-radius: var(--sd-radius-xl);
  box-shadow: var(--sd-shadow-xl);
  z-index: var(--sd-z-modal);
  max-height: 90vh;
  overflow-y: auto;
  animation: slideIn var(--sd-transition-normal);
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes slideIn {
  from { opacity: 0; transform: translate(-50%, -48%); }
  to { opacity: 1; transform: translate(-50%, -50%); }
}

/* === Toast Notifications === */
.toast-container {
  position: fixed;
  bottom: var(--sd-spacing-4);
  right: var(--sd-spacing-4);
  z-index: var(--sd-z-toast);
  display: flex;
  flex-direction: column;
  gap: var(--sd-spacing-2);
}

.toast {
  display: flex;
  align-items: center;
  gap: var(--sd-spacing-3);
  padding: var(--sd-spacing-3) var(--sd-spacing-4);
  background-color: var(--sd-color-background);
  border-radius: var(--sd-radius-md);
  box-shadow: var(--sd-shadow-lg);
  animation: slideInRight var(--sd-transition-slow);
}

.toast-success { border-left: 4px solid var(--sd-color-success); }
.toast-error { border-left: 4px solid var(--sd-color-error); }
.toast-warning { border-left: 4px solid var(--sd-color-warning); }
.toast-info { border-left: 4px solid var(--sd-color-info); }

@keyframes slideInRight {
  from { opacity: 0; transform: translateX(100%); }
  to { opacity: 1; transform: translateX(0); }
}

/* === Status Badge === */
.badge {
  display: inline-flex;
  align-items: center;
  padding: var(--sd-spacing-1) var(--sd-spacing-2);
  font-size: var(--sd-font-size-xs);
  font-weight: var(--sd-font-weight-medium);
  border-radius: var(--sd-radius-full);
}

.badge-success {
  background-color: var(--sd-color-success-light);
  color: var(--sd-color-success);
}

.badge-error {
  background-color: var(--sd-color-error-light);
  color: var(--sd-color-error);
}

.badge-warning {
  background-color: var(--sd-color-warning-light);
  color: var(--sd-color-warning);
}

/* === Accessibility === */
.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Focus ring for keyboard navigation */
:focus-visible {
  outline: 2px solid var(--sd-color-primary);
  outline-offset: 2px;
}

/* Reduce motion for users who prefer it */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

### 1.1 レスポンシブ対応

#### 1.1.1 ブレークポイント
| 画面サイズ | 分類 | レイアウト |
|-----------|------|-----------|
| 1024px以上 | PC/タブレット横 | 2カラム（映像+設定パネル横並び） |
| 768px〜1023px | タブレット縦 | 2カラム（設定パネル縮小） |
| 767px以下 | スマートフォン | 1カラム（縦積み+タブ切替） |

#### 1.1.2 スマートフォンレイアウト（編集モード）
```
┌─────────────────────────────┐
│ Circle Detector    [≡] [●] │  ← ハンバーガーメニュー
├─────────────────────────────┤
│ [映像] [設定] [グループ]    │  ← タブ切替
├─────────────────────────────┤
│ ┌─────────────────────────┐ │
│ │                         │ │
│ │    カメラ映像           │ │  映像は横幅100%
│ │    (タッチで円作成)     │ │  アスペクト比維持
│ │                         │ │
│ │   ●  ●                  │ │
│ └─────────────────────────┘ │
│                             │
│ ┌─────────────────────────┐ │
│ │ [+ 円追加] [スポイト]   │ │  ← ツールバー
│ └─────────────────────────┘ │
├─────────────────────────────┤
│ ▼ 選択中: 円1              │  ← 選択した円の情報
│   ■赤 ■緑 [+ 色追加]       │
│   [削除]                    │
├─────────────────────────────┤
│ [保存] [実行モード開始 ▶]  │
└─────────────────────────────┘
```

#### 1.1.3 スマートフォンレイアウト（実行モード）
```
┌─────────────────────────────┐
│ ● 実行中         [停止 ■]  │
├─────────────────────────────┤
│ ┌─────────────────────────┐ │
│ │    カメラ映像           │ │  映像表示ON/OFF可
│ │    (省電力時は非表示)   │ │
│ └─────────────────────────┘ │
├─────────────────────────────┤
│ ┌─────────────────────────┐ │
│ │ パトライト1    値: 10   │ │
│ │ ├ 円1: ■赤              │ │
│ │ └ 円2: ■緑              │ │
│ ├─────────────────────────┤ │
│ │ パトライト2    値: 20   │ │
│ │ └ 円3: ■黄 (点滅)       │ │
│ └─────────────────────────┘ │
├─────────────────────────────┤
│ 送信: 125  エラー: 0       │
│ 15:30:05 EQUIP01→10 ✓     │
└─────────────────────────────┘
```

#### 1.1.4 タッチ操作対応
| PC操作 | スマホ操作 |
|--------|-----------|
| クリック | タップ |
| ドラッグ | タッチ＆スライド |
| ホバー | 長押し（プレビュー） |
| 右クリック | 長押しメニュー |

#### 1.1.5 円作成（タッチ操作）
```
1. 「円追加」ボタンをタップ → 追加モードON
2. 映像上でタッチ開始 → 中心点決定
3. 指をスライド → 半径がリアルタイム表示
4. 指を離す → 円確定
5. ピンチイン/アウト → 半径微調整（オプション）
```

#### 1.1.6 CSS設計方針（レスポンシブ）
```css
/* モバイルファースト */
.main-content {
    display: flex;
    flex-direction: column;
}

.video-panel {
    width: 100%;
    max-width: 640px;
    margin: 0 auto;
}

.settings-panel {
    width: 100%;
}

/* タブレット以上 */
@media (min-width: 768px) {
    .main-content {
        flex-direction: row;
    }
    .video-panel {
        flex: 1;
    }
    .settings-panel {
        width: 320px;
    }
}

/* PC */
@media (min-width: 1024px) {
    .settings-panel {
        width: 400px;
    }
}
```

---

### 1.2 画面レイアウト

#### 1.2.1 全体構成（編集モード）
```
┌─────────────────────────────────────────────────────────────────────────┐
│ Header                                                         h:50px  │
│ ┌─────────────────────────────────────────────────────────────────────┐│
│ │ [Logo] Circle Detector          [編集モード ○ ● 実行モード] [接続●] ││
│ └─────────────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────────┤
│ Main Content                                                           │
│ ┌─────────────────────────────────┬───────────────────────────────────┐│
│ │ Video Panel          640x480   │ Settings Panel          w:320px  ││
│ │ ┌─────────────────────────────┐│ ┌─────────────────────────────────┐││
│ │ │                             ││ │ ▼ 基本設定                      │││
│ │ │                             ││ │   STA_NO1: [▼ PLANT01    ]     │││
│ │ │     カメラ映像              ││ │   送信モード: [▼ 変化時のみ]    │││
│ │ │     + 円オーバーレイ        ││ ├─────────────────────────────────┤││
│ │ │                             ││ │ ▼ グループ（パトライト）        │││
│ │ │   ●────● 円1               ││ │   [+ 新規グループ]              │││
│ │ │      ●  円2                 ││ │   ┌─────────────────────────┐  │││
│ │ │                             ││ │   │ ▶ パトライト1          │  │││
│ │ │                             ││ │   │   STA_NO2: [LINE01   ] │  │││
│ │ └─────────────────────────────┘│ │   │   STA_NO3: [EQUIP01  ] │  │││
│ │                                │ │   │   円: 1, 2             │  │││
│ │ ツールバー                     │ │   │   [ルール設定]         │  │││
│ │ [円追加] [削除] [スポイト]     │ │   └─────────────────────────┘  │││
│ │                                │ ├─────────────────────────────────┤││
│ └────────────────────────────────┘│ │ ▼ 選択中の円                   │││
│                                   │ │   ID: 1  名前: [ランプ1    ]   │││
│                                   │ │   位置: (100, 100) 半径: 25    │││
│                                   │ │   グループ: [▼ パトライト1]    │││
│                                   │ │   ── 登録色 ──                 │││
│                                   │ │   ■ 赤  [編集][削除]           │││
│                                   │ │   ■ 緑  [編集][削除]           │││
│                                   │ │   [+ 色を追加]                 │││
│                                   │ │   [円を削除]                   │││
│                                   │ └─────────────────────────────────┘││
│                                   └───────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────────┤
│ Footer                                                         h:40px  │
│ ┌─────────────────────────────────────────────────────────────────────┐│
│ │ [設定保存] [設定読込]                    最終更新: 15:30:00         ││
│ └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

#### 1.2.2 実行モード
```
┌─────────────────────────────────────────────────────────────────────────┐
│ Header                                                                  │
│ ┌─────────────────────────────────────────────────────────────────────┐│
│ │ [Logo] Circle Detector - 実行中  [編集モード ● ○ 実行モード] [接続●]││
│ └─────────────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────┬───────────────────────────────────┐│
│ │ Video Panel                     │ Status Panel                     ││
│ │ ┌─────────────────────────────┐│ ┌─────────────────────────────────┐││
│ │ │                             ││ │ ▼ パトライト1                   │││
│ │ │    カメラ映像               ││ │   送信値: 10                    │││
│ │ │    [映像ON/OFF]             ││ │   ┌───────────────────────────┐ │││
│ │ │                             ││ │   │ 円1: ■赤 (点滅なし)      │ │││
│ │ │                             ││ │   │ 円2: ■緑 (点滅なし)      │ │││
│ │ │                             ││ │   └───────────────────────────┘ │││
│ │ └─────────────────────────────┘│ ├─────────────────────────────────┤││
│ │                                │ │ ▼ パトライト2                   │││
│ │                                │ │   送信値: 20                    │││
│ │                                │ │   ┌───────────────────────────┐ │││
│ │                                │ │   │ 円3: ■黄 (点滅中)        │ │││
│ │                                │ │   └───────────────────────────┘ │││
│ │                                │ ├─────────────────────────────────┤││
│ │                                │ │ ▼ 送信ログ                      │││
│ │                                │ │   15:30:05 EQUIP01 → 10 ✓      │││
│ │                                │ │   15:30:04 EQUIP02 → 20 ✓      │││
│ │                                │ │   15:30:03 EQUIP01 → 10 ✓      │││
│ └────────────────────────────────┘│ └─────────────────────────────────┘││
│                                   └───────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────────────┤
│ Footer                                                                  │
│ │ 稼働時間: 00:15:30  送信数: 125  エラー: 0  キュー: 0               ││
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 操作フロー詳細

#### 1.3.1 円の作成
```
状態遷移図:

  [通常状態]
      │
      │ 「円追加」ボタンクリック
      ▼
  [円追加モード] ─── カーソル: crosshair
      │
      │ カメラ映像上でマウスダウン
      ▼
  [ドラッグ中] ─── 中心点固定、マウス位置まで半径を描画
      │
      │ マウスアップ
      ▼
  [円確定] ─── POST /api/circles
      │
      │ 成功
      ▼
  [通常状態] ─── 新しい円が選択状態
```

**JavaScript処理:**
```javascript
// 状態管理
const state = {
    mode: 'normal',  // 'normal' | 'adding_circle' | 'dragging'
    dragStart: null, // {x, y}
    currentRadius: 0
};

// マウスイベント
canvas.onmousedown = (e) => {
    if (state.mode === 'adding_circle') {
        state.mode = 'dragging';
        state.dragStart = getMousePos(e);
    }
};

canvas.onmousemove = (e) => {
    if (state.mode === 'dragging') {
        const pos = getMousePos(e);
        state.currentRadius = Math.sqrt(
            Math.pow(pos.x - state.dragStart.x, 2) +
            Math.pow(pos.y - state.dragStart.y, 2)
        );
        redrawCanvas();  // プレビュー描画
    }
};

canvas.onmouseup = (e) => {
    if (state.mode === 'dragging') {
        if (state.currentRadius >= 10) {  // 最小半径
            createCircle(state.dragStart, state.currentRadius);
        }
        state.mode = 'normal';
    }
};
```

#### 1.3.2 色の登録（スポイト）
```
  [円選択状態]
      │
      │ 「色を追加」→「画面から取得」
      ▼
  [スポイトモード] ─── カーソル: スポイトアイコン
      │
      │ カメラ映像上でクリック
      ▼
  [色取得] ─── GET /api/color/{x}/{y}
      │
      │ 色情報受信
      ▼
  [色編集ダイアログ] ─── 色名入力、HSV範囲調整
      │
      │ 保存
      ▼
  [通常状態] ─── 円に色が追加
```

### 1.4 コンポーネント仕様

#### 1.4.1 VideoCanvas コンポーネント
```javascript
class VideoCanvas {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.img = document.createElement('img');      // MJPEG
        this.canvas = document.createElement('canvas'); // オーバーレイ
        this.ctx = this.canvas.getContext('2d');
    }

    // 円を描画
    drawCircle(circle, isSelected) {
        this.ctx.beginPath();
        this.ctx.arc(circle.center_x, circle.center_y, circle.radius, 0, 2 * Math.PI);
        this.ctx.strokeStyle = isSelected ? '#00ff00' : '#ffffff';
        this.ctx.lineWidth = isSelected ? 3 : 2;
        this.ctx.stroke();

        // ラベル
        this.ctx.fillStyle = '#ffffff';
        this.ctx.font = '12px sans-serif';
        this.ctx.fillText(circle.name, circle.center_x - 10, circle.center_y - circle.radius - 5);
    }

    // 全円を再描画
    redraw(circles, selectedId) {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        circles.forEach(c => this.drawCircle(c, c.id === selectedId));
    }
}
```

#### 1.4.2 ColorPickerDialog コンポーネント
```html
<div id="color-picker-dialog" class="dialog">
    <div class="dialog-header">
        <h3>色の設定</h3>
        <button class="close-btn">&times;</button>
    </div>
    <div class="dialog-body">
        <!-- 取得方法選択 -->
        <div class="tab-buttons">
            <button class="tab active" data-tab="eyedropper">画面から取得</button>
            <button class="tab" data-tab="palette">カラーパレット</button>
        </div>

        <!-- スポイトタブ -->
        <div class="tab-content" id="eyedropper-tab">
            <p>カメラ映像上でクリックして色を取得</p>
            <div class="color-preview">
                <div class="preview-box" id="picked-color"></div>
                <span id="picked-color-info">H:0 S:0 V:0</span>
            </div>
        </div>

        <!-- パレットタブ -->
        <div class="tab-content hidden" id="palette-tab">
            <div class="hsv-sliders">
                <label>H (色相): <input type="range" id="h-slider" min="0" max="179"></label>
                <label>S (彩度): <input type="range" id="s-slider" min="0" max="255"></label>
                <label>V (明度): <input type="range" id="v-slider" min="0" max="255"></label>
            </div>
        </div>

        <!-- 共通設定 -->
        <div class="color-settings">
            <label>色名: <input type="text" id="color-name" placeholder="例: 赤"></label>
            <label>H許容範囲: ±<input type="number" id="h-range" value="10" min="1" max="90"></label>
            <label>S範囲: <input type="number" id="s-min"> - <input type="number" id="s-max"></label>
            <label>V範囲: <input type="number" id="v-min"> - <input type="number" id="v-max"></label>
        </div>
    </div>
    <div class="dialog-footer">
        <button class="btn-secondary" id="color-cancel">キャンセル</button>
        <button class="btn-primary" id="color-save">保存</button>
    </div>
</div>
```

#### 1.4.3 RuleEditorDialog コンポーネント
```html
<div id="rule-editor-dialog" class="dialog large">
    <div class="dialog-header">
        <h3>マッピングルール設定 - パトライト1</h3>
    </div>
    <div class="dialog-body">
        <!-- ルール一覧 -->
        <div class="rule-list">
            <div class="rule-item" data-rule-id="1">
                <span class="priority">優先度: 100</span>
                <span class="description">円1が赤 → 10</span>
                <button class="edit-btn">編集</button>
                <button class="delete-btn">削除</button>
            </div>
            <div class="rule-item" data-rule-id="2">
                <span class="priority">優先度: 90</span>
                <span class="description">円1が赤 + 円2が緑 → 30</span>
                <button class="edit-btn">編集</button>
                <button class="delete-btn">削除</button>
            </div>
        </div>

        <button class="btn-add" id="add-rule">+ ルールを追加</button>

        <!-- ルール編集フォーム -->
        <div class="rule-form hidden" id="rule-form">
            <h4>ルール編集</h4>
            <label>優先度: <input type="number" id="rule-priority" value="100"></label>
            <label>送信値: <input type="number" id="rule-value"></label>

            <div class="conditions">
                <h5>条件</h5>
                <div class="condition-item">
                    <select class="circle-select">
                        <option value="1">円1 (ランプ1)</option>
                        <option value="2">円2 (ランプ2)</option>
                    </select>
                    <span>が</span>
                    <select class="color-select">
                        <option value="赤">赤</option>
                        <option value="緑">緑</option>
                    </select>
                    <label><input type="checkbox" class="blinking-check"> 点滅中</label>
                    <button class="remove-condition">×</button>
                </div>
            </div>
            <button class="btn-secondary" id="add-condition">+ 条件追加</button>
        </div>

        <!-- デフォルト値 -->
        <div class="default-value">
            <label>ルール不一致時のデフォルト値: <input type="number" id="default-value" value="0"></label>
        </div>
    </div>
    <div class="dialog-footer">
        <button class="btn-secondary" id="rule-cancel">閉じる</button>
        <button class="btn-primary" id="rule-save">保存</button>
    </div>
</div>
```

---

## 1.5 データクラス・共通クラス定義

### 1.5.1 データクラス（SDDと統一）

```python
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

@dataclass
class Circle:
    """円領域"""
    id: int
    name: str
    center_x: int
    center_y: int
    radius: int
    group_id: Optional[int]
    colors: List['ColorRange'] = field(default_factory=list)

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
    circle_ids: List[int] = field(default_factory=list)

@dataclass
class Rule:
    """マッピングルール"""
    id: int
    group_id: int
    priority: int
    type: str          # "single" or "composite"
    conditions: List['RuleCondition'] = field(default_factory=list)
    value: int = 0

@dataclass
class RuleCondition:
    """ルール条件"""
    circle_id: int
    color: str
    blinking: bool = False

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

### 1.5.2 CameraManager クラス

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
        if self.device == "usb":
            self.cap = cv2.VideoCapture(0)
        elif self.device == "rpi":
            self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        else:
            self.cap = cv2.VideoCapture(self.device)

        if not self.cap.isOpened():
            return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.running = True
        return True

    def stop(self):
        """カメラを停止"""
        self.running = False
        if self.cap:
            self.cap.release()

    def get_frame(self) -> Optional[np.ndarray]:
        """現在のフレームを取得"""
        if not self.cap or not self.running:
            return None
        ret, frame = self.cap.read()
        if ret:
            with self.lock:
                self.frame = frame
            return frame
        return None

    def generate_mjpeg(self) -> Generator[bytes, None, None]:
        """MJPEGストリームを生成"""
        while self.running:
            frame = self.get_frame()
            if frame is not None:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            time.sleep(0.033)  # 約30fps

    def get_color_at(self, x: int, y: int, radius: int = 5) -> Tuple[int, int, int]:
        """指定位置の平均色（HSV）を取得"""
        with self.lock:
            if self.frame is None:
                return (0, 0, 0)
            # 周囲の領域を切り出して平均を計算
            y1, y2 = max(0, y - radius), min(self.frame.shape[0], y + radius)
            x1, x2 = max(0, x - radius), min(self.frame.shape[1], x + radius)
            roi = self.frame[y1:y2, x1:x2]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            return tuple(np.mean(hsv, axis=(0, 1)).astype(int))
```

### 1.5.3 ConfigManager クラス

```python
class ConfigManager:
    """設定管理クラス"""

    CONFIG_PATH = "config/circle_detector.json"

    def __init__(self):
        self.config: dict = {}
        self.circles: List[Circle] = []
        self.groups: List[Group] = []
        self.rules: List[Rule] = []
        self._next_circle_id = 1
        self._next_group_id = 1
        self._next_rule_id = 1

    def load(self) -> bool:
        """設定ファイルを読み込み"""
        if not os.path.exists(self.CONFIG_PATH):
            self._init_default()
            return False

        try:
            with open(self.CONFIG_PATH, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self._parse_config()
            return True
        except Exception as e:
            print(f"Config load error: {e}")
            self._init_default()
            return False

    def save(self) -> bool:
        """設定ファイルに保存"""
        try:
            self.config['circles'] = [asdict(c) for c in self.circles]
            self.config['groups'] = [asdict(g) for g in self.groups]
            self.config['rules'] = [asdict(r) for r in self.rules]
            self.config['updated'] = datetime.now().isoformat()

            os.makedirs(os.path.dirname(self.CONFIG_PATH), exist_ok=True)
            with open(self.CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Config save error: {e}")
            return False

    def add_circle(self, circle: Circle) -> int:
        """円を追加、IDを返す"""
        circle.id = self._next_circle_id
        self._next_circle_id += 1
        self.circles.append(circle)
        return circle.id

    def get_circle(self, circle_id: int) -> Optional[Circle]:
        """円を取得"""
        return next((c for c in self.circles if c.id == circle_id), None)

    def update_circle(self, circle: Circle) -> bool:
        """円を更新"""
        for i, c in enumerate(self.circles):
            if c.id == circle.id:
                self.circles[i] = circle
                return True
        return False

    def delete_circle(self, circle_id: int) -> bool:
        """円を削除"""
        self.circles = [c for c in self.circles if c.id != circle_id]
        return True

    def add_group(self, group: Group) -> int:
        """グループを追加"""
        group.id = self._next_group_id
        self._next_group_id += 1
        self.groups.append(group)
        return group.id

    def add_rule(self, rule: Rule) -> int:
        """ルールを追加"""
        rule.id = self._next_rule_id
        self._next_rule_id += 1
        self.rules.append(rule)
        return rule.id

    def get_sta_no1_options(self) -> List[str]:
        """STA_NO1の選択肢を取得"""
        return self.config.get('station', {}).get('sta_no1_options', ['PLANT01'])

    def to_dict(self) -> dict:
        """設定を辞書形式で取得（API用）"""
        return {
            'station': self.config.get('station', {}),
            'detection': self.config.get('detection', {}),
            'circles': [asdict(c) for c in self.circles],
            'groups': [asdict(g) for g in self.groups],
            'rules': [asdict(r) for r in self.rules]
        }

    def _init_default(self):
        """デフォルト設定を初期化"""
        self.config = {
            'version': '1.0',
            'station': {'sta_no1': 'PLANT01', 'sta_no1_options': ['PLANT01']},
            'detection': {'send_mode': 'on_change', 'send_interval_sec': 1}
        }
        self.circles = []
        self.groups = []
        self.rules = []

    def _parse_config(self):
        """設定をパース"""
        # circles
        self.circles = []
        for c in self.config.get('circles', []):
            colors = [ColorRange(**col) for col in c.get('colors', [])]
            circle = Circle(
                id=c['id'], name=c['name'],
                center_x=c['center_x'], center_y=c['center_y'],
                radius=c['radius'], group_id=c.get('group_id'),
                colors=colors
            )
            self.circles.append(circle)
            self._next_circle_id = max(self._next_circle_id, c['id'] + 1)

        # groups
        self.groups = []
        for g in self.config.get('groups', []):
            group = Group(**g)
            self.groups.append(group)
            self._next_group_id = max(self._next_group_id, g['id'] + 1)

        # rules
        self.rules = []
        for r in self.config.get('rules', []):
            conditions = [RuleCondition(**cond) for cond in r.get('conditions', [])]
            rule = Rule(
                id=r['id'], group_id=r['group_id'], priority=r['priority'],
                type=r['type'], conditions=conditions, value=r['value']
            )
            self.rules.append(rule)
            self._next_rule_id = max(self._next_rule_id, r['id'] + 1)
```

### 1.5.4 DetectionEngine クラス

```python
class DetectionEngine:
    """色検出エンジン"""

    def __init__(self, config_manager: ConfigManager, blink_config: dict = None):
        self.config = config_manager
        self.blink_detector = BlinkDetector(blink_config or {})

    def detect_all(self, frame: np.ndarray) -> List[DetectionResult]:
        """全円の色を検出"""
        results = []
        for circle in self.config.circles:
            result = self.detect_circle(frame, circle)
            results.append(result)
        return results

    def detect_circle(self, frame: np.ndarray, circle: Circle) -> DetectionResult:
        """1つの円の色を検出（詳細は2.2〜2.5節参照）"""
        # 実装は後続のセクションで定義
        pass
```

---

## 2. 色検出アルゴリズム詳細設計

### 2.1 処理フロー

```
[フレーム取得]
      │
      ▼
[円領域切り出し] ─── マスク処理で円形に
      │
      ▼
[BGR → HSV変換]
      │
      ▼
[平均HSV計算] ─── マスク内ピクセルの平均
      │
      ▼
[登録色とのマッチング] ─── 各色のHSV範囲と比較
      │
      ├─ マッチあり → 色名を返す
      │
      └─ マッチなし → None（未検出）
      │
      ▼
[点滅判定] ─── 履歴から判定
      │
      ▼
[DetectionResult]
```

### 2.2 円領域切り出し

```python
def _get_circle_region(self, frame: np.ndarray, circle: Circle) -> Tuple[np.ndarray, np.ndarray]:
    """
    円領域を切り出し、マスクを生成

    Args:
        frame: 入力フレーム (BGR)
        circle: 円情報

    Returns:
        (切り出し領域, マスク)
    """
    # バウンディングボックス計算
    x1 = max(0, circle.center_x - circle.radius)
    y1 = max(0, circle.center_y - circle.radius)
    x2 = min(frame.shape[1], circle.center_x + circle.radius)
    y2 = min(frame.shape[0], circle.center_y + circle.radius)

    # 領域切り出し
    roi = frame[y1:y2, x1:x2].copy()

    # 円形マスク作成
    mask = np.zeros(roi.shape[:2], dtype=np.uint8)
    center_in_roi = (circle.center_x - x1, circle.center_y - y1)
    cv2.circle(mask, center_in_roi, circle.radius, 255, -1)

    return roi, mask
```

### 2.3 平均HSV計算

```python
def _calculate_average_hsv(self, roi: np.ndarray, mask: np.ndarray) -> Tuple[int, int, int]:
    """
    マスク領域内の平均HSVを計算

    Args:
        roi: 切り出し領域 (BGR)
        mask: 円形マスク

    Returns:
        (H, S, V) の平均値
    """
    # BGR → HSV
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # マスク内のピクセルのみ抽出
    masked_pixels = hsv[mask > 0]

    if len(masked_pixels) == 0:
        return (0, 0, 0)

    # 色相（H）は循環するため特別な処理
    # 0と179が近い値になるよう、sin/cosで平均を取る
    h_values = masked_pixels[:, 0].astype(float)
    h_rad = h_values * np.pi / 90  # 0-179 → 0-2π

    h_sin = np.mean(np.sin(h_rad))
    h_cos = np.mean(np.cos(h_rad))
    h_avg = np.arctan2(h_sin, h_cos) * 90 / np.pi
    if h_avg < 0:
        h_avg += 180

    # S, V は単純平均
    s_avg = np.mean(masked_pixels[:, 1])
    v_avg = np.mean(masked_pixels[:, 2])

    return (int(h_avg), int(s_avg), int(v_avg))
```

### 2.4 色マッチング

```python
def _match_color(self, hsv: Tuple[int, int, int], colors: List[ColorRange]) -> Optional[str]:
    """
    HSV値を登録色とマッチング

    Args:
        hsv: 検出したHSV値
        colors: 登録色リスト

    Returns:
        マッチした色名、なければNone
    """
    h, s, v = hsv

    for color in colors:
        # 色相（H）の判定 - 循環を考慮
        h_min = color.h_center - color.h_range
        h_max = color.h_center + color.h_range

        h_match = False
        if h_min < 0:
            # 例: h_center=5, range=10 → -5~15 → 175~180 または 0~15
            h_match = (h >= h_min + 180) or (h <= h_max)
        elif h_max >= 180:
            # 例: h_center=175, range=10 → 165~185 → 165~179 または 0~5
            h_match = (h >= h_min) or (h <= h_max - 180)
        else:
            h_match = h_min <= h <= h_max

        # 彩度（S）と明度（V）の判定
        s_match = color.s_min <= s <= color.s_max
        v_match = color.v_min <= v <= color.v_max

        if h_match and s_match and v_match:
            return color.name

    return None
```

### 2.5 点滅検出

```python
class BlinkDetector:
    """点滅検出クラス"""

    def __init__(self, config: dict):
        self.window_ms = config.get('window_ms', 2000)
        self.min_changes = config.get('min_changes', 3)
        self.min_interval_ms = config.get('min_interval_ms', 100)
        self.max_interval_ms = config.get('max_interval_ms', 1500)

        # 履歴: {circle_id: deque of (timestamp, color)}
        self.history: Dict[int, deque] = {}

    def update(self, circle_id: int, color: Optional[str]) -> bool:
        """
        色を記録し、点滅かどうかを判定

        Args:
            circle_id: 円ID
            color: 検出された色（Noneも可）

        Returns:
            点滅中かどうか
        """
        now = time.time() * 1000  # ミリ秒

        if circle_id not in self.history:
            self.history[circle_id] = deque(maxlen=100)

        history = self.history[circle_id]

        # 前回と色が変わった場合のみ記録
        if not history or history[-1][1] != color:
            history.append((now, color))

        # 古い履歴を削除
        cutoff = now - self.window_ms
        while history and history[0][0] < cutoff:
            history.popleft()

        # 点滅判定
        return self._is_blinking(history)

    def _is_blinking(self, history: deque) -> bool:
        """
        履歴から点滅を判定

        条件:
        1. window_ms内にmin_changes回以上の色変化
        2. 各変化の間隔がmin_interval_ms～max_interval_msの範囲
        """
        if len(history) < self.min_changes + 1:
            return False

        # 変化間隔を計算
        intervals = []
        for i in range(1, len(history)):
            interval = history[i][0] - history[i-1][0]
            intervals.append(interval)

        # 条件チェック
        valid_intervals = [
            i for i in intervals
            if self.min_interval_ms <= i <= self.max_interval_ms
        ]

        return len(valid_intervals) >= self.min_changes
```

### 2.6 検出結果の統合

```python
def detect_circle(self, frame: np.ndarray, circle: Circle) -> DetectionResult:
    """
    1つの円の色を検出

    Args:
        frame: 入力フレーム
        circle: 円情報

    Returns:
        検出結果
    """
    # 円領域取得
    roi, mask = self._get_circle_region(frame, circle)

    # 平均HSV計算
    hsv = self._calculate_average_hsv(roi, mask)

    # 色マッチング
    color_name = self._match_color(hsv, circle.colors)

    # 点滅判定
    is_blinking = self.blink_detector.update(circle.id, color_name)

    return DetectionResult(
        circle_id=circle.id,
        detected_color=color_name,
        is_blinking=is_blinking,
        raw_hsv=hsv
    )
```

---

## 3. マッピングルールエンジン詳細設計

### 3.1 ルール評価フロー

```
[全円の検出結果]
      │
      ▼
[グループごとにループ]
      │
      ▼
[グループ内のルールを優先度順にソート]
      │
      ▼
[各ルールを順に評価]
      │
      ├─ 単一円ルール → _evaluate_single()
      │
      └─ 複合ルール → _evaluate_composite()
            │
            ▼
      [マッチした場合]
            │
            └─ そのルールのvalueを返す（評価終了）
            │
      [全ルール不一致]
            │
            └─ デフォルト値を返す
```

### 3.2 ルールエンジン実装

```python
class RuleEngine:
    """マッピングルール評価エンジン"""

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager

    def evaluate_group(self, group: Group, results: List[DetectionResult]) -> int:
        """
        グループのルールを評価し、送信値を決定

        Args:
            group: グループ情報
            results: 全円の検出結果

        Returns:
            送信値（T1_STATUS）
        """
        # グループに属するルールを取得
        group_rules = [r for r in self.config.rules if r.group_id == group.id]

        # 優先度順にソート（降順）
        sorted_rules = sorted(group_rules, key=lambda r: r.priority, reverse=True)

        # 検出結果をdict化（高速アクセス用）
        result_map = {r.circle_id: r for r in results}

        # ルールを順に評価
        for rule in sorted_rules:
            if self._evaluate_rule(rule, result_map):
                return rule.value

        # 全ルール不一致 → デフォルト値
        return group.default_value

    def _evaluate_rule(self, rule: Rule, result_map: Dict[int, DetectionResult]) -> bool:
        """
        1つのルールを評価

        Args:
            rule: ルール情報
            result_map: {circle_id: DetectionResult}

        Returns:
            ルールがマッチしたかどうか
        """
        if rule.type == 'single':
            return self._evaluate_single(rule.conditions[0], result_map)
        elif rule.type == 'composite':
            return self._evaluate_composite(rule.conditions, result_map)
        else:
            return False

    def _evaluate_single(self, condition: RuleCondition, result_map: Dict[int, DetectionResult]) -> bool:
        """
        単一条件を評価

        Args:
            condition: 条件
            result_map: 検出結果マップ

        Returns:
            条件がマッチしたかどうか
        """
        result = result_map.get(condition.circle_id)
        if not result:
            return False

        # 色が一致
        color_match = result.detected_color == condition.color

        # 点滅状態が一致
        blink_match = result.is_blinking == condition.blinking

        return color_match and blink_match

    def _evaluate_composite(self, conditions: List[RuleCondition], result_map: Dict[int, DetectionResult]) -> bool:
        """
        複合条件を評価（AND条件）

        Args:
            conditions: 条件リスト
            result_map: 検出結果マップ

        Returns:
            全条件がマッチしたかどうか
        """
        for condition in conditions:
            if not self._evaluate_single(condition, result_map):
                return False
        return True

    def evaluate_all_groups(self, results: List[DetectionResult]) -> Dict[int, int]:
        """
        全グループを評価

        Args:
            results: 全円の検出結果

        Returns:
            {group_id: value} の辞書
        """
        group_values = {}

        for group in self.config.groups:
            value = self.evaluate_group(group, results)
            group_values[group.id] = value

        return group_values
```

### 3.3 ルール評価例

#### 例1: 単一円ルール
```python
# ルール定義
rule = Rule(
    id=1,
    group_id=1,
    priority=100,
    type='single',
    conditions=[
        RuleCondition(circle_id=1, color='赤', blinking=False)
    ],
    value=10
)

# 検出結果
results = [
    DetectionResult(circle_id=1, detected_color='赤', is_blinking=False, raw_hsv=(0, 200, 200))
]

# 評価
# circle_id=1 が '赤' で blinking=False → マッチ → 10を返す
```

#### 例2: 単一円 + 点滅ルール
```python
# ルール定義
rule = Rule(
    id=2,
    group_id=1,
    priority=90,
    type='single',
    conditions=[
        RuleCondition(circle_id=3, color='緑', blinking=True)
    ],
    value=20
)

# 検出結果
results = [
    DetectionResult(circle_id=3, detected_color='緑', is_blinking=True, raw_hsv=(60, 200, 200))
]

# 評価
# circle_id=3 が '緑' で blinking=True → マッチ → 20を返す
```

#### 例3: 複合ルール
```python
# ルール定義
rule = Rule(
    id=3,
    group_id=1,
    priority=80,
    type='composite',
    conditions=[
        RuleCondition(circle_id=1, color='赤', blinking=False),
        RuleCondition(circle_id=2, color='緑', blinking=False)
    ],
    value=30
)

# 検出結果
results = [
    DetectionResult(circle_id=1, detected_color='赤', is_blinking=False, raw_hsv=(0, 200, 200)),
    DetectionResult(circle_id=2, detected_color='緑', is_blinking=False, raw_hsv=(60, 200, 200))
]

# 評価
# circle_id=1 が '赤' + circle_id=2 が '緑' （両方点滅なし）→ マッチ → 30を返す
```

### 3.4 優先度による評価順序

```python
# ルール一覧（グループ1）
rules = [
    Rule(id=1, priority=100, ...),  # 最優先
    Rule(id=2, priority=90, ...),
    Rule(id=3, priority=80, ...),
]

# 評価順序
# 1. priority=100 のルール → マッチしなければ次へ
# 2. priority=90 のルール → マッチしなければ次へ
# 3. priority=80 のルール → マッチしなければ次へ
# 4. 全て不一致 → default_value を返す
```

---

## 4. MQTT送信（既存流用）

### 4.1 既存モジュールの利用

```python
# equipment_status.py から流用
from equipment_status import MQTTPublisher, MQTTConfig

# message_queue.py から流用
from message_queue import FileQueue
```

### 4.2 送信データ形式

```python
# 送信するJSONペイロード
payload = {
    "mk_date": "20260211153000",  # YYYYMMDDHHmmss
    "sta_no1": "PLANT01",
    "sta_no2": "LINE01",
    "sta_no3": "EQUIP01",
    "t1_status": 10
}

# トピック
topic = "equipment/status/EQUIP01"
```

### 4.3 MQTTSender クラス

```python
class MQTTSender:
    """MQTT送信クラス（ファイルキュー永続化対応）"""

    RETRY_INTERVAL = 5.0  # 5秒ごとにリトライ

    def __init__(self, config: dict):
        self.mqtt_config = MQTTConfig(
            broker=config['mqtt']['broker'],
            port=config['mqtt']['port'],
            topic=config['mqtt']['topic'],
            enabled=config['mqtt']['enabled']
        )
        self.publisher = MQTTPublisher(self.mqtt_config)
        self.queue = FileQueue("queue/pending_circle.jsonl", max_retries=10000)

        self.sta_no1 = config['station']['sta_no1']
        self.running = False
        self.retry_thread = None

        # 統計
        self.stats = {
            "sent": 0,
            "queued": 0,
            "retried": 0,
            "errors": 0
        }

    def start(self):
        """バックグラウンドリトライスレッドを開始"""
        self.running = True
        self.retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
        self.retry_thread.start()

        # 起動時に未送信キューを確認
        pending = self.queue.get_count()
        if pending > 0:
            print(f"[MQTT] {pending} messages pending from previous session")

    def stop(self):
        """停止"""
        self.running = False
        if self.retry_thread:
            self.retry_thread.join(timeout=2.0)

    def _retry_loop(self):
        """5秒ごとにキューを確認して再送"""
        while self.running:
            try:
                pending_count = self.queue.get_count()

                if pending_count > 0:
                    # キューから1件取得して送信
                    pending = self.queue.get_pending(limit=1)
                    if pending:
                        msg = pending[0]
                        success = self._send_raw(msg.data)

                        if success:
                            self.queue.remove(msg.id)
                            self.stats["retried"] += 1
                            remaining = self.queue.get_count()
                            print(f"[MQTT] Retry sent (remaining: {remaining})")
                        else:
                            self.queue.increment_retry(msg.id)

            except Exception as e:
                pass

            time.sleep(self.RETRY_INTERVAL)

    def _send_raw(self, data: dict) -> bool:
        """生データを送信"""
        try:
            return self.publisher.publish_raw(data, subtopic=data.get("sta_no3", ""))
        except:
            return False

    def send(self, group: Group, value: int) -> bool:
        """
        グループの値を送信

        Args:
            group: グループ情報
            value: 送信値

        Returns:
            送信成功かどうか
        """
        data = {
            "mk_date": datetime.now().strftime("%Y%m%d%H%M%S"),
            "sta_no1": self.sta_no1,
            "sta_no2": group.sta_no2,
            "sta_no3": group.sta_no3,
            "t1_status": value
        }

        # MQTT送信
        success = self._send_raw(data)

        if success:
            self.stats["sent"] += 1
        else:
            # 失敗時はキューに保存
            self.queue.add(data)
            self.stats["queued"] += 1

        return success

    def get_stats(self) -> dict:
        """統計情報を取得"""
        return {
            **self.stats,
            "pending": self.queue.get_count()
        }
```

### 4.4 通信障害時のフロー

```
[送信試行]
    │
    ├─ 成功 → stats["sent"]++、完了
    │
    └─ 失敗 → キューに保存 (queue/pending_circle.jsonl)
              stats["queued"]++

[バックグラウンド（5秒ごと）]
    │
    ▼
[キュー確認]
    │
    ├─ キューが空 → 何もしない
    │
    └─ キューにデータあり
          │
          ▼
       [1件取得して送信]
          │
          ├─ 成功 → キューから削除、stats["retried"]++
          │
          └─ 失敗 → リトライカウント++
                    (max_retries超過で破棄)
```

### 4.5 キューファイル形式

ファイル: `queue/pending_circle.jsonl`

```jsonl
{"id": "msg_20260211153001_1", "data": {"mk_date": "20260211153000", "sta_no1": "PLANT01", "sta_no2": "LINE01", "sta_no3": "EQUIP01", "t1_status": 10}, "created_at": "2026-02-11T15:30:01", "retry_count": 0}
{"id": "msg_20260211153002_2", "data": {"mk_date": "20260211153001", "sta_no1": "PLANT01", "sta_no2": "LINE01", "sta_no3": "EQUIP02", "t1_status": 20}, "created_at": "2026-02-11T15:30:02", "retry_count": 1}
```

### 4.6 既存モジュール流用

| モジュール | ファイル | 流用内容 |
|-----------|---------|---------|
| FileQueue | message_queue.py | キュー管理（追加/削除/リトライ） |
| MQTTPublisher | equipment_status.py | MQTT接続・送信 |

---

## 5. 変更履歴

| 日付 | バージョン | 変更内容 |
|------|------------|----------|
| 2026-02-11 | 1.0 | 初版作成 |
| 2026-02-11 | 1.1 | Serendie Design System適用方針追加（セクション1.0） |
| 2026-02-11 | 1.2 | セクション番号修正（1.6→1.5） |
