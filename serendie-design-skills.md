# Serendie Design System Skill

このスキルは、三菱電機のSerendie Design Systemに沿った Web/UI デザイン・コード生成を行うためのガイドラインです。  
目的は、適応型UIコンポーネントライブラリを活用し、一貫性のあるプロフェッショナルなUIを安定して生成することです。

---

# 1. Brand Identity（ブランドアイデンティティ）

## 1.1 キーワード
- 適応性（Adaptive）
- 一貫性（Consistency）
- モダン・洗練
- アクセシビリティ
- 拡張性

## 1.2 トーン＆マナー
- シンプルで機能的なデザイン
- 明確な階層構造
- ユーザビリティを最優先
- システムとしての統一感
- 柔軟性と拡張性を重視

---

# 2. Design System Architecture（デザインシステム構成）

## 2.1 主要リポジトリ
- **React Components**: [serendie/serendie](https://github.com/serendie/serendie)
  - 適応型UIコンポーネントライブラリ
  - TypeScript製
  - MIT License

- **Design Tokens**: [serendie/design-token](https://github.com/serendie/design-token)
  - W3C Design Tokens仕様準拠
  - カラー、タイポグラフィ、スペーシング等の定義

- **Icons**: [serendie/serendie-symbols](https://github.com/serendie/serendie-symbols)
  - 300以上のSVGアイコンセット
  - TypeScript型定義付き

- **Figma Utils**: [serendie/figma-utils](https://github.com/serendie/figma-utils)
  - Figma Variables ↔ JSON変換ツール
  - デザインと開発の同期を支援

## 2.2 公式リソース
- **ガイドライン**: [serendie.design](https://serendie.design)
- **Storybook**: [storybook.serendie.design](https://storybook.serendie.design)
- **Figma UI Kit**: Serendie UI Kit

---

# 3. Color Palette（カラーパレット）

## 3.1 基本方針
- Design Tokensリポジトリから取得することを推奨
- W3C Design Tokens仕様に準拠
- テーマ対応（ライト/ダーク）を考慮

## 3.2 使用方法
- `@serendie/design-token`パッケージからインポート
- CSS変数として利用可能
- Figma Variablesと同期可能

## 3.3 カスタマイズ
- サブブランドテーマ作成用テンプレート: [serendie/subbrands-template](https://github.com/serendie/subbrands-template)
- デザイントークンを上書きして独自テーマを構築可能

---

# 4. Typography（タイポグラフィ）

## 4.1 基本方針
- Design Tokensで定義されたフォントファミリーを使用
- レスポンシブなタイポグラフィスケール
- アクセシビリティを考慮したサイズ設定

## 4.2 使用方法
- Design Tokensからフォント定義を取得
- Reactコンポーネント内で自動適用
- カスタマイズが必要な場合はトークンを上書き

---

# 5. Layout（レイアウト）

## 5.1 グリッドシステム
- Design Tokensで定義されたスペーシングシステムを使用
- 8pxベースのグリッド推奨
- レスポンシブブレークポイントはコンポーネントで管理

## 5.2 適応型UI
- コンポーネントは自動的に画面サイズに適応
- モバイルファーストのアプローチ
- コンテキストに応じた表示の切り替え

## 5.3 情報整理
- 明確なセクション分け
- 視覚的階層の明確化
- ホワイトスペースの適切な活用

---

# 6. UI Components（UI コンポーネント）

## 6.1 基本方針
- `@serendie/serendie`パッケージからコンポーネントをインポート
- Storybookで各コンポーネントの使用方法を確認
- TypeScript型定義を活用

## 6.2 主要コンポーネント
- ボタン、フォーム要素、カード、テーブル等
- 各コンポーネントは適応型（Adaptive）に設計
- アクセシビリティ対応済み

## 6.3 カスタマイズ
- Design Tokensを上書きしてスタイルを変更
- コンポーネントのプロパティで動作を調整
- テーマシステムを活用した一括変更

---

# 7. Icons（アイコン）

## 7.1 基本方針
- `@serendie/serendie-symbols`からSVGアイコンをインポート
- 300以上のアイコンが利用可能
- TypeScript型定義でタイプセーフに使用可能

## 7.2 使用方法
- 必要なアイコンを個別にインポート
- サイズや色はプロパティで指定
- アクセシビリティ属性を適切に設定

---

# 8. Motion（アニメーション）

## 8.1 基本方針
- 控えめで機能的なアニメーション
- ユーザビリティを妨げない範囲で使用
- パフォーマンスを考慮した実装

## 8.2 推奨
- トランジション: 150-200ms
- フェードイン/アウト: 100-200ms
- ホバーエフェクト: 150ms
- 過度なアニメーションは避ける

---

# 9. Figma Integration（Figma連携）

## 9.1 基本方針
- `@serendie/figma-utils`を使用してFigma Variablesと同期
- W3C Design Tokens仕様でJSON形式に変換
- デザインと開発の一貫性を保つ

## 9.2 ワークフロー
1. Figmaでデザイン変数を定義
2. `figma-utils`でJSONにエクスポート
3. Design Tokensリポジトリに反映
4. Reactコンポーネントで自動適用

## 9.3 インポート/エクスポート
- Figma REST APIを使用
- 双方向の同期が可能
- バージョン管理と統合

---

# 10. Code（コード実装）の原則

## 10.1 パッケージインストール

```bash
# React Components
npm install @serendie/serendie

# Design Tokens
npm install @serendie/design-token

# Icons
npm install @serendie/serendie-symbols
```

## 10.2 React コンポーネントの使用

```typescript
import { Button, Card } from '@serendie/serendie';

function App() {
  return (
    <Card>
      <Button variant="primary">Click me</Button>
    </Card>
  );
}
```

## 10.3 Design Tokensの使用

```typescript
import { tokens } from '@serendie/design-token';

const styles = {
  color: tokens.color.primary,
  spacing: tokens.spacing.md,
  typography: tokens.typography.body,
};
```

## 10.4 Iconsの使用

```typescript
import { IconCheck, IconClose } from '@serendie/serendie-symbols';

function Component() {
  return (
    <>
      <IconCheck size={24} />
      <IconClose size={24} />
    </>
  );
}
```

## 10.5 CSS変数の利用

Design TokensはCSS変数としても利用可能：

```css
:root {
  /* Design Tokensから自動生成されるCSS変数 */
  --serendie-color-primary: ...;
  --serendie-spacing-md: ...;
  --serendie-typography-body: ...;
}
```

---

# 11. Best Practices（ベストプラクティス）

## 11.1 コンポーネント使用
- 既存のコンポーネントを優先的に使用
- カスタムコンポーネントは必要最小限に
- Storybookで動作確認

## 11.2 デザイントークン
- ハードコードされた値を避ける
- Design Tokensを常に使用
- カスタマイズはトークンレベルで行う

## 11.3 アクセシビリティ
- コンポーネントのアクセシビリティ機能を活用
- ARIA属性を適切に設定
- キーボードナビゲーションを考慮

## 11.4 パフォーマンス
- 必要なコンポーネントのみインポート
- アイコンは個別インポートでTree Shakingを有効化
- バンドルサイズを意識

---

# 12. Development Workflow（開発ワークフロー）

## 12.1 セットアップ
1. 必要なパッケージをインストール
2. Storybookでコンポーネントを確認
3. 公式ガイドライン（serendie.design）を参照

## 12.2 デザイン実装
1. Figma UI Kitでデザイン作成
2. `figma-utils`でトークンをエクスポート
3. Reactコンポーネントで実装
4. Storybookで確認

## 12.3 カスタマイズ
1. サブブランドテンプレートを使用
2. Design Tokensを上書き
3. 必要に応じてコンポーネントを拡張

---

# 13. Resources（リソース）

## 13.1 公式リソース
- **ガイドライン**: https://serendie.design
- **Storybook**: https://storybook.serendie.design
- **GitHub**: https://github.com/serendie
- **Figma UI Kit**: Serendie UI Kit

## 13.2 コミュニティ
- **X (Twitter)**: @SerendieDesign
- **GitHub Discussions**: プライベート
- **MS Teams**: プライベートチャット

## 13.3 ドキュメント
- 各リポジトリのREADMEを参照
- Storybookでコンポーネントの詳細を確認
- 公式ガイドラインでデザイン原則を理解

---

# 14. Claude に対する指示（Skill としての挙動）

* UI・デザインを生成する際は **必ずSerendie Design Systemのコンポーネントとトークンを使用すること**
* `@serendie/serendie`からコンポーネントをインポートし、既存のコンポーネントを優先的に使用すること
* Design Tokens（`@serendie/design-token`）を活用し、ハードコードされた値を避けること
* アイコンは`@serendie/serendie-symbols`から適切にインポートすること
* Storybookでコンポーネントの使用方法を確認し、正しいプロパティを使用すること
* Figma連携が必要な場合は`@serendie/figma-utils`を活用すること
* アクセシビリティを考慮し、適切なARIA属性を設定すること
* 適応型UIの特性を活かし、レスポンシブな実装を行うこと
* 公式ガイドライン（serendie.design）の原則に従うこと
* コード生成時はTypeScript型定義を活用し、タイプセーフな実装を行うこと

---

