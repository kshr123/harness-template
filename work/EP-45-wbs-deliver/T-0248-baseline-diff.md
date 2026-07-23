---
id: T-0248
kind: task
status: done
created: 2026-07-23
closed: 2026-07-23
start: 2026-07-23
due: 2026-07-23
effort_days: 2
requirements: [REQ-008]
depends_on: [T-0247]
verified_by:
  - tests/test_deliver_baseline.py::test_nothing_moved_means_no_changes
  - tests/test_deliver_baseline.py::test_a_moved_date_appears_with_the_commit_that_moved_it
  - tests/test_deliver_baseline.py::test_added_and_removed_units_are_listed
  - tests/test_deliver_baseline.py::test_a_status_change_is_reported
  - tests/test_deliver_baseline.py::test_the_working_tree_is_left_alone
  - tests/test_deliver_baseline.py::test_an_unknown_reference_fails_loudly
  - tests/test_deliver_baseline.py::test_the_diff_command_reports_and_says_when_nothing_moved
  - tests/test_deliver_baseline.py::test_export_at_a_past_reference_reproduces_that_plan
  - tests/test_deliver_baseline.py::test_export_at_a_past_reference_ignores_uncommitted_changes
---
# T-0248 合意した計画と、いまの計画の差を出す

## 作ったもの

- `uv run wbs diff <合意した時点>` … 動いた点だけを並べる（動いていない単位は出てこない）。
- `uv run wbs export --at <合意した時点>` … その時点の WBS をそのまま出し直す。刻む由来もその時点になる
  （いまの HEAD ではない）ので、後から出し直しても提出したものと突き合わせられる。

## 新しい保管場所を作らなかったこと（設計の要点）

変更履歴の台帳を新設すると、書き忘れた第 1 号から嘘になる。だから既にあるものを使う：

- **合意した時点＝ git のタグ**。合意したらその場で印を打つだけ。改竄できない時系列が無料で手に入る。
- **変更の理由＝その日程を動かしたコミットのメッセージ**。コミットメッセージの冒頭に作業単位の ID を
  書くことは既に検査（commit-msg-lint）が強制しているので、理由は既に書かれている。書き写さない。

比較は、指定した時点の入力を一時の場所へ取り出して**同じ導出**にかけ、出てきた行どうしを突き合わせる
＝表示・検査・比較の 3 つが同じ導出を見る。比較のために作業ツリーを切り替えない（いまの作業を邪魔しない）。

親の行の日程は子から導いた値なので、動いても「配下の変更による」と添える（同じ事実を 2 回主張しない）。
ただし落としはしない：フェーズの終わりがいつ動いたかはクライアントが最も見るところで、落とすと
「タスクは動いたがフェーズは？」を人が計算し直すことになる。

## 受け入れ基準

- [x] 2 時点を比べたとき、予定日を動かした単位・足した単位・消した単位がすべて差に現れ、動かしていない単位は現れないか。
- [x] 差の各行に、その変更を入れたコミットが添えられているか（理由を別の場所に書き写していないか）。
- [x] 合意時点の参照を指定して、その時点の WBS をそのまま再生成できるか（いまの値が混ざらないか）。
- [x] 比較のために作業ツリーが動かないか。
- [x] 存在しない参照を指定したとき、黙って空の差を返さずに失敗するか。
