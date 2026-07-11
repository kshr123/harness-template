---
id: T-0222
kind: task
status: todo
title: DIMRED に帰納的な住人を増やす（umap・openTSNE の条件登録）
created: 2026-07-11
depends_on: [T-0220]
verified_by: []
---
# T-0222 次元圧縮の住人

## 何が問題か
`DIMRED` の住人は pca と tsne（sklearn・transform 無し＝(A) 専用）の 2 つだけ。非線形の埋め込みを
(B) 経路（新規行を変換）で使う口が無い。実測（2026-07-11・Python 3.14）：
- sklearn の `TSNE` に `transform` は無い（`hasattr(TSNE(), "transform")` が False）。
- openTSNE 1.0.4 は 3.14 に入り、`fit(X).transform(新規行)` が動く（帰納的）。

## やること
- umap-learn と openTSNE を optional extra にし、条件登録で住人を足す（`inductive=True`）。
  seed の配線（決定性）と前処理前置（中央値埋め＋標準化）は既存住人と同じ流儀。
- 既存の `tsne`（sklearn・inductive=False）は (A) 専用のまま残す（openTSNE は別 kind。上書きしない）。

## やらないこと
- PaCMAP（`transform(X, basis=X_train)` という独自契約の吸収は、実需要が来てから別タスクで判断する。
  包みを先に作るのは消費者の居ない抽象）。
- phate 等の網羅。
- DIMRED の (B)（ENCODERS）接続の変更（pca は既に ENCODERS に在る。umap を (B) に足すかは実需要待ち）。

## 受け入れ基準
- 新住人が T-0220 の帰納性テストにテスト側の変更なしで合格する（fit に使っていない新規行を変換できる）。
- umap／openTSNE 未導入の環境でも import が成功し、カタログに出ない（条件登録・extras_hint）。
- 同じ `(df, seed)` で 2 回埋め込むと同じ座標（決定性は seed の明示引数で。着手時に各ライブラリの
  決定性の作法を実測すること——umap は random_state 指定で並列が切れる等の癖がある。未確認）。
- `uv run verify` 全成功。
