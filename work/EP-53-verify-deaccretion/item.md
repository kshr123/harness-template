---
id: EP-53
kind: epic
status: in-progress
plan: detailed
requirements: []
depends_on: []
---
# EP-53 verify の脱・accretion（機構を統合・効かない検査を撤回する）

「`uv run verify` が何でも全部やる」という指摘への対処。fable の全体棚卸しで分かったのは：**verify は遅くない**
（全体 57 秒の 93% は pytest・18 個の不変検査は合計 2.3 秒＝4%）。本当の accretion は**機構の数と保守面**＝
テスト 1453 本の約 20% が「検査を検査するテスト」。だから直し方は「検査を飛ばす」でなく「機構を統合する／
効かない検査を撤回する」。撤回の是非はオーナー判断（AGENTS）＝承認済み。

## 含む作業
- T-0299 描画テストを verify から外す（browser マーカー）＋ full の pytest 3 回を 1 回に統合。
  幾何は Python 計算で `test_deliver_geometry`（unit）が毎回検証済み＝Chrome が要るのは JS/DOM の 3 本だけ。
- T-0300 効かない検査を撤回：`retraction_lint`（`RETRACTED={}` で常に空＝no-op）と `pm.spec_lint`
  （見出しの有無だけ＝防ぎたい失敗を防げない儀式）を不変検査から外す。retraction は撤回時だけ走る on-demand へ。
- T-0301 `data_lint` の各スキーマ規則を `TableSchema` の pydantic バリデータへ（不正スキーマを作れなくする＝(a)）。
  スキーマ間の規則（ID 重複・lineage 参照・scope）だけ lint に残す。
- T-0302 doc 系 6 検査（doclint/doc_source_lint/code_doc_lint/profile_doc_lint/coverage_lint/doc_sync）を
  1 モジュールに統合（検出ゼロ喪失・profile_doc_lint の存在検査は code_doc_lint と重複 so 廃止）。

## 含めない
- scope/fast/standard/full/verify の構造変更（fable 判定＝健全・触らない）。
- 不変検査を毎回走らせるのをやめること（2.3 秒＝安くて“黙った間違い”を防ぐ・据え置き）。
- 検査の CI/scope への降格（browser 以外は subprocess を起動せず ms 級＝降格はルーティング複雑化の損だけ）。
