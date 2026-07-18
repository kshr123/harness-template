---
id: T-0231
kind: task
status: done
title: status --next を足す（着手候補の提案）＋残る DX 2 項目の判断を確定する
created: 2026-07-18
closed: 2026-07-18
depends_on: []
verified_by:
  - tests/test_pm.py::test_next_actionable_classifies_ready_waiting_and_outline
  - tests/test_pm.py::test_status_cli_writes_file_by_default_and_next_flag_does_not
---
## 独立レビュー（fable・maker≠checker）で見つかった欠陥と対処
- **H1（直した）**：`status` は console_script（argv を渡されない）なので、素の関数に `typer.Option` を既定値で
  置くと OptionInfo が truthy に評価され、`--next` 無しでも提案の枝に入り STATUS.md を書かなくなっていた
  （`uv run status` の中核挙動の退行）。→ `status_cmd` を module-level にして `status_main` は `typer.run` で
  包む（init_project と同じ形）。CLI 層のテストを追加（既定は STATUS.md を書く・--next は書かない）。
- L1（コメントで明示）：`to_outline` は末端の outline epic だけを挙げる（子を持つ epic は分解途中＝除外）。
# T-0231 status --next＋残る DX の判断

ISS-0013 は 3 つの DX 項目を「設計判断が要るので分離」して owner 判断に委ねていた。実測して判断を確定した：
1 つは着手（作る）、2 つは動機（消費者・観測された事故）が無いので見送る。

## 作った：status --next（ISS-0013 項目3）
`uv run status --next` で「次に着手できる作業単位」を提案する（提案・門番でない）。3 つに分ける：
- **いま着手できる**：末端の task/experiment で status=todo・depends_on が全て done。
- **依存待ち**：todo だが未完の depends_on を持つ（未完の依存 ID を添える）。
- **分解の候補**：outline のままの epic（着手前にまず detailed へ割る）。
`pm.next_actionable`／`pm.render_next` に実装、`status_main` に `--next` フラグを配線（STATUS.md は書き換えない）。
コマンド増設でなくフラグ追加なので coverage_lint（CLI コマンドの到達性）に新規配線は不要。

## 見送る（消費者・動機が無い＝churn を避ける）
- **template-init（項目1）**：複製の機械化＋複製後 verify。真の機械化は実験の識別子を train.py で
  どう持つか（パラメタ化するか per-experiment のままか）の**設計判断が先**。この設計は「次に実験を
  scaffold する時」に、その具体的な必要と一緒に決めるのが素直（今は E-0001 を丸ごとコピーして config を
  書き換える流儀で足りている）。設計を伴う一度きりの発明を、消費者が現れる前にやらない。
- **coverage ratchet（項目2）**：pytest-cov（新依存）＋baseline 保存＋CI 比較。テストは property／例示／
  CLI で既に厚く、案件が育つ前にカバレッジ床を課すのは時期尚早（ISS-0013 自身の判断）。案件が育って
  床を決める根拠ができた時に足す。今の新依存追加は動機が無い。

判断の一般形は L-025（配置・投資の基準は「観測可能な事故になるか／消費者が居るか」）。
