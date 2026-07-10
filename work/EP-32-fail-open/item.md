---
id: EP-32
kind: epic
status: in-progress
plan: detailed
requirements: []
depends_on: []
created: 2026-07-10
---
# EP-32 fail-open を塞ぐ（検証が「何も走らせず緑」になる経路を閉じる）

## 何が問題か
`uv run verify` の実体は `checks.toml`（言語ツールのコマンド）と `PM_CHECKS`（プロジェクト管理の検査）。
このうち `checks.toml` 経由の pytest には、静かに全テストを消しても緑になる経路がある。

- pytest は「選んだ目印に該当するテストが 0 件」を終了コード 5 で表す。`checks.py` はこれを合格として
  読み飛ばす（複製先が層を正当に空にできるようにする、意図した寛容さ）。
- ところがマーカーを綴り違え（`unit`→`unitt`）ると全 deselect で 0 件になり、exit 5 経由で
  「テストが 1 件も無いのに緑」になる。改名リファクタや複製で悪意なく踏む。
- pytest コマンドを丸ごと消す・`commands = []` に置換しても、同じく緑になる。

このエピックは「検証が実質何も確かめずに緑になる（fail-open）」経路を、走らせる前の不変条件で閉じる。

## 方針
exit 5 の寛容さ自体は残す（複製先が層を正当に空にできる余地を消さない）。代わりに、
**`checks.toml` が満たすべき不変条件を、走らせる前に検査して、満たさなければ起動を拒否する**。
不変条件の対象集合はツール自身の定数（`LEVELS`・`testing.PYRAMID`）と `pyproject.toml` の登録から
機械的に導けるので、これは自己申告の台帳ではない。

## タスク
- T-0198 checks.toml のマーカー不変条件（起動時の precondition）
