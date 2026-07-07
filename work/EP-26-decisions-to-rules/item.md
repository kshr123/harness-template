---
id: EP-26
kind: epic
status: todo
plan: detailed
requirements: [REQ-001]
depends_on: [EP-24]
created: 2026-07-07
---
# EP-26 意思決定の記録（DEC）を廃し、現在のルールに畳む

## 背景（オーナー方針 2026-07-07）
テンプレートは複製して使う。`docs/decisions/`（DEC・ADR 形式：状況→選択肢→決定→影響）はハーネス自身を
作った**歴史**で、新案件がコピーして 20 個の過去決定を引き継ぐのは過剰。必要なのは「**何をするか・しないか**」
（現在のルール）だけで、変わったら**差し替え**、経緯は **git**（コミット・diff）が持つ。ADR の重い様式と
積み上がる記録は、テンプレートには膨張。→ **DEC 体系を廃止し、現在のルールに畳む**（EP-25 完了後に協調移行）。

## 何をするか
1. **現在のルールは従う場所に置く**：`AGENTS.md`（規範・各行に**一節の理由**をインライン）／`method.md`
   （進め方）／各プロファイル docs（契約）。「（DEC-xxxx）」の 81 参照は、一節の理由に畳むか落とす。
2. **`docs/decisions/` を削除**（全 20 DEC＋`_template.md`）。**深い経緯・却下案は git が保持**（削除しても履歴に残る）。
3. **method.md のメタ模型を作り直す**：7 層の「決定（DEC）」層を外す。「ルール化の流れ」から DEC 起票の段を外し
   （観察→learnings→一般性ありと判断したら即、機械検査/抽象/スキル/規約へ落とし込む→learnings 更新→削除）、
   「変更の記録は git」に改める。
4. **機械結合を外す**：`doclint` は `docs/decisions/` の走査と `DEC-XXXX` 参照検査をやめる（＋テスト更新）。
5. **索引・凡例・複製手順を更新**：README/`docs/README.md` の凡例から `DEC`、文書地図から `decisions/` を外す。
   `template-copy.md` の「残す：docs/decisions/」を外す。`learnings.md` の「状態: ルール化済み → DEC-xxxx」は
   「ルール化済み（AGENTS/検査へ）」に改める。

## DEC の畳み先マップ（被参照数つき・削除しても git に残る）
- **ルールとして既に AGENTS/method/docs にある → 参照だけ落とす**：0002(生成物 STATUS)/0004(テーブル正本)/
  0006(標準を再発明しない)/0008(作る基準)/0009(部品は使える状態まで)/0012(必要時に即)/0013,0014(範囲)/
  0015(effort・無ネットワーク)/0016(導線検査)/0017,0018,0020(loops)。理由が本文に無ければ一節足す。
- **一度きり・歴史的 → 落とす**（refs=0）：0001/0003/0007/0010(Rule of Three 解除)/0011/0021。
- **REQ は現状維持**（案件ごとに複製で消して書き直す＝正しい。将来 charter への畳み込みは別途）。

## 受け入れ基準
- `uv run verify` 全成功（doclint 更新後・`DEC-XXXX` の死にリンクゼロ・decisions/ 無しで緑）。
- `docs/decisions/` が無い。恒久ドキュメントに `DEC-` 参照が残らない（learnings の状態欄含む）。
- 各「現在のルール」が AGENTS/method/docs に一節の理由つきで立っている（規範は弱めない）。README/索引/
  複製手順が decisions/ を指さない。

## 進め方（安全な順序＝verify を緑に保つ）
- T-0160：参照を畳む（docs/skills/AGENTS の DEC 参照を一節の理由へ／落とす。decisions/ はまだ置く）→ verify 緑。
- T-0161：method.md のメタ模型を作り直す（DEC 層・DEC 起票フローを外す）→ verify 緑。
- T-0162：機械結合と削除（doclint 更新＋テスト・索引/凡例/template-copy 更新・`git rm docs/decisions/`）→ verify 緑。
