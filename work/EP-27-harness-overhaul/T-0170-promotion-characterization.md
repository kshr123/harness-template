---
id: T-0170
kind: task
status: done
title: 昇格判定の挙動を固定するテストを置く（実装は変更しない）
created: 2026-07-10
depends_on: [T-0169]
verified_by:
  - tests/test_promotion_characterization.py::test_ds_only_a_strict_improvement_promotes
  - tests/test_promotion_characterization.py::test_ds_threshold_failure_does_not_move_the_champion
  - tests/test_promotion_characterization.py::test_ds_first_promotion_is_decided_by_thresholds_alone
  - tests/test_promotion_characterization.py::test_ds_direction_comes_from_the_metric_registry
  - tests/test_promotion_characterization.py::test_ds_nan_candidate_fails_both_the_threshold_and_the_comparison
  - tests/test_promotion_characterization.py::test_ds_nan_champion_blocks_every_promotion
  - tests/test_promotion_characterization.py::test_ds_unknown_primary_is_rejected
  - tests/test_promotion_characterization.py::test_ds_contradicting_direction_argument_is_rejected
  - tests/test_promotion_characterization.py::test_ds_promotion_record_has_the_expected_fields
  - tests/test_promotion_characterization.py::test_agent_only_a_strict_improvement_promotes
  - tests/test_promotion_characterization.py::test_agent_threshold_failure_does_not_move_the_champion
  - tests/test_promotion_characterization.py::test_agent_nan_candidate_and_nan_champion_are_fail_closed
  - tests/test_promotion_characterization.py::test_agent_unknown_primary_is_rejected
  - tests/test_promotion_characterization.py::test_agent_promotion_record_has_the_expected_fields
---
# T-0170 昇格判定の characterization テスト

## なぜ先にこれを置くか
次の 2 つを同時にやりたいが、同時にやると等価性が誰にも確かめられない。

1. `promote_model`（ds）と `promote_agent`（agent）に重複している判定ロジックを中核へ抽出する（T-0171）。
2. エラーメッセージの造語（「絶対関門」「相対関門」）を標準用語に直す（T-0172）。

既存テストは日本語メッセージに `pytest.raises(match=...)` で依存しており、2 を行うと壊れる。
「テストを書き換えて成功させない」というルールと衝突するように見えるが、衝突していない。禁じられているのは
**挙動を変えたのにテストを弱めて緑にする**ことで、ここで変えるのは文言だけ。文言を固定したテストは、
標準用語の正しいメッセージを失敗させる＝検査の欠陥にあたる。

ただし自己申告で「等価だから書き換えてよい」と言うのは、まさに禁じられている振る舞いなので、**先に
文言に依存しない形で挙動を固定する**。順序は次のとおり：

- **T-0170（このタスク）**：挙動と構造だけを固定するテストを新設。実装は 1 行も変えない。現実装で緑になる
  ことが「旧挙動を正しく写し取った」証拠。
- **T-0171**：中核へ抽出。文言は一字一句そのまま。**既存テストも本テストも無変更で緑**＝抽出が等価である
  機械的証拠。
- **T-0172**：文言だけを標準用語へ。同じコミットで文言に依存した `match=` を構造の照合へ置き換える。
  本テストのファイルは差分に現れない（受け入れ基準に含める）。

## 固定する挙動（ds・agent の両方）
- 閾値を満たさない候補は昇格せず、champion は動かない（champion 不在でも効く）。
- champion 不在の初回昇格は閾値だけで決まる。
- 現 champion に負ける候補は昇格しない。**同点も昇格しない**（厳密に良いときだけ）。
- 向きの正本はレジストリ（`log_loss` は小さいほど良い）。昇格記録に解決後の向きが残る。
- NaN は fail closed：候補が NaN・現 champion が NaN のどちらでも昇格しない。
- 未登録の primary は `ValueError`（typo を黙って不合格にしない）。
- 昇格記録のフィールド（work・name・version・decided・primary・higher_is_better・metrics・previous_version）。

## 受け入れ基準
- 新テストが**現実装のまま**全成功する（`git diff --stat` に `src/` が現れない）。
- どのテストも例外のメッセージ文字列に依存しない（`pytest.raises(ValueError)` のみ・`match=` を使わない）。
- 期待値はすべて仕込んだ metrics と閾値の大小から導出できる。
- 変異検査：比較を `>` から `>=` に変えると同点のテストが失敗する（＝同点拒否が本当に守られている）。
- `uv run verify` 全成功。
