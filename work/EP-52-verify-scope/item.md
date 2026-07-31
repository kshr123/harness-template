---
id: EP-52
kind: epic
status: done
plan: detailed
requirements: []
depends_on: []
---
# EP-52 検証にスコープ軸を足す（編集ループを速く・完了ゲートは完全なまま）

「`uv run verify` が何をしても全部回すのは無駄」という指摘への対処。設計は fable レビュー（深さ×スコープの2軸・
影響グラフは既存の `Profile.test_globs` を使う・迷ったら全実行）。背骨（完了＝検証にすべて成功／空振りで緑を
作らない）は崩さない：スコープは**参考実行の層だけ**に置き、`verify` と CI は完全なまま。

## 含む作業
- T-0298 `uv run check --scope diff`（新設）＝git 差分から回すものを絞る参考実行。散文だけ→不変条件のみ
  （Chrome も pytest も回さない）／プロファイル変更→その領域だけ／検査インフラ・中核・分類不能→全実行（fail-closed）。

## 含めない
- `verify` 自体のスコープ化（＝done の証拠がルーティング正しさに依存する＝背骨が崩れる。オーナー確認済みで不採用）。
- Chrome の fail-open ガード（前回オーナーが過剰として落とした。狭いリスクとして受容）。
- pytest-testmon 等（prose・frontmatter・TOML を見られず、この repo の検査入力が死角＝(b)を装った(c)になる）。
