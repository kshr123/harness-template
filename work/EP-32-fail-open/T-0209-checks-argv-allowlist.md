---
id: T-0209
kind: task
status: done
title: checks.toml のコマンドを argv allowlist にして、テスト 0 件で緑になる経路を fail closed で塞ぐ
created: 2026-07-10
depends_on: [T-0198]
verified_by:
  - tests/test_verification_mechanism.py::test_checks_config_rejects_collapsed_layers
  - tests/test_verification_mechanism.py::test_checks_config_rejects_extra_k_arg
  - tests/test_verification_mechanism.py::test_checks_config_rejects_collect_only
  - tests/test_verification_mechanism.py::test_checks_config_rejects_ignore_arg
  - tests/test_verification_mechanism.py::test_checks_config_rejects_hollow_ruff_version
  - tests/test_verification_mechanism.py::test_checks_config_rejects_hollow_mypy_version
  - tests/test_verification_mechanism.py::test_checks_config_rejects_unknown_top_command
  - tests/test_verification_mechanism.py::test_checks_config_rejects_dangling_m
  - tests/test_verification_mechanism.py::test_checks_config_accepts_stage_reassignment
  - tests/test_verification_mechanism.py::test_checks_config_accepts_valid_config
  - tests/test_agent_goal.py::test_goal_rejects_empty_thresholds_at_construction
---
# T-0209 checks.toml のコマンドを argv allowlist にする（T-0198 の追補）

## 何が問題か（独立レビューが実測・2026-07-10）
T-0198 の `_verify_checks_config` は「コマンド名（先頭トークン）が現れるか」しか見ていなかった。
名前の存在だけを条件にすると、次の**悪意ゼロで踏める**書き方がすべて素通りし、「テスト 0 件のまま verify 緑」に
なる。すべて自分で再現した（tmp_path 上の checks.toml／pyproject.toml で config が受理されること）：

| 書き方 | なぜ通っていたか |
| --- | --- |
| `-m "unit and integration and e2e"`（1 行に集約） | 参照マーカーの和集合は 3 層を被覆するので (3) を満たす。だが積は空集合＝exit 5＝偽の合格 |
| 正しい `-m` に `-k zzz_never_match` を追加 | `-k` を検査していない。全 deselect→exit 5 |
| `--collect-only` を追加 | 検査していない。exit 0 で 1 件も実行しない |
| `--ignore=tests` を追加 | 検査していない。exit 0 |
| `["ruff","--version"]`／`["mypy","--version"]` に骨抜き | 先頭トークンしか見ないので (1) を満たしてしまう |

## なぜ denylist でなく allowlist か（L-017・L-019）
上の 5 通りを 1 つずつ潰すのは**検出器**であって、次のフラグ（`--deselect`・`-p`・`--co` 短縮形…）を必ず
見逃す。「既に知っている不良の形」を列挙するのは、発生源を塞がず保守対象だけを増やす（L-017）。探す形を
自分で決めるのは確認バイアス（L-019）。そこで**許すものだけを列挙し、未知は既定で拒否**する（fail closed）。
次のフラグも既定で止まる。何を走らせてよいか（＝コマンドの argv の集合）は PYRAMID／定数から機械的に導ける
ので、これは保証の (b)（機械が検出）を正しく名乗れる（対象集合が書く人の申告に依存しない）。

## 直し方
`checks.py` に走らせてよい argv の定数集合を持つ：
- ruff：`("ruff","format","--check",".")`・`("ruff","check",".")` のどちらか。
- mypy：`("mypy",)`。
- pytest：先頭 `pytest` の後は `-q` と `-m <式>` だけ。未知の引数は `ValueError`。`-m` が末尾で式が無ければ
  `ValueError`（`cmd.index("-m")+1` の素の `IndexError` にしない）。
- 上記いずれの形にも一致しないコマンド（先頭が ruff/mypy/pytest 以外、または argv が集合外）は `ValueError`。
- `-m` 式の**充足可能性**：テストは PYRAMID の層をちょうど 1 つ持つ、という前提で pytest 自身の式評価器
  （`-m` と同じ意味）に掛け、どのテストも選べない式（例 `unit and integration`）を `ValueError`。
  対象の世界は PYRAMID 定数から機械的に列挙する（3 層 × slow 等の自由マーカーの真偽）。

段階への割り当て・順序は checks.toml が自由に決めてよい（複製先の調整の自由は残す）。**何を走らせてよいか**だけ
固定する。既存 3 不変条件（未登録マーカー拒否・ruff/mypy の存在・層の被覆）は残す。exit 5 の扱い（run_check 側）
は変えない。

## 何を保証し、何を保証しないか（T-0198 の主張の修正）
T-0198 は「fail-open を塞ぐ」と書いたが、実際に保証していたのは「列挙した 3 つの経路（typo・pytest 行削除・
ruff/mypy 削除）を塞ぐ」ことだった。allowlist に変えた後は主張を強められる：**許した argv の集合の外は
すべて起動前に拒否される**（未知の引数・未知のコマンド・充足不能な式を含む）。
ただしこれは「事故防止」であって「改竄防止」ではない。この関数を書き換える手は checks.toml を書き換える手と
同じで、リポ内に不動点は無い（AGENTS「保証の 3 段階」）。後退を止めるのは差分の独立レビューと作業ツリー外の
required checks。

## やらないこと
- すり抜けを 1 つずつ潰す（denylist）。**allowlist にする。**
- checks.toml を廃止して定数に凍結する（段階割り当ては複製先が調整してよい）。
- pytest の exit 5 の扱いを変える。

## ミューテーション実測
allowlist を外す（未知引数・許可外 argv を素通りさせる）と、上のすり抜け 5 通りのテストが RED になることを
実測して記録する（本文の「実測」節）。
