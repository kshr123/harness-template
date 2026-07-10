---
id: T-0172
kind: task
status: done
title: 昇格判定の造語（絶対関門・相対関門）を標準用語に置き換える
created: 2026-07-10
depends_on: [T-0171]
verified_by:
  - tests/test_ds_models.py::test_promotion_value_threshold_and_champion_move
  - tests/test_ds_models.py::test_promotion_change_threshold_reject
  - tests/test_agent_store.py::test_promote_agent_value_and_change_thresholds
  - tests/test_gates.py::test_change_threshold_fails_when_the_candidate_lacks_the_metric_even_without_a_baseline
  - tests/test_gates.py::test_evaluate_collects_every_failure_not_just_the_first
  - tests/test_promotion_characterization.py::test_ds_only_a_strict_improvement_promotes
  - tests/test_promotion_characterization.py::test_agent_only_a_strict_improvement_promotes
---
# T-0172 造語の是正

## 何が問題だったか
「関門」「絶対関門」「相対関門」は私（エージェント）の造語で、出典が無い。とくに「相対関門」は
**何と何を比べるのか**が名前から読めない（現 champion か・baseline か・前の版か）。実装は現 champion との
比較だった。データサイエンティストやエンジニアが読んで一意に分かる標準用語で書き直す。

| 造語 | 置き換え | 出典 |
| --- | --- | --- |
| 絶対関門 | `value_threshold` | TensorFlow Extended の `tfma.MetricThreshold` |
| 相対関門 | `change_threshold`（`baseline: champion`） | 同上（`GenericChangeThreshold`） |
| 関門で不合格 | 昇格を却下（rejected） | SageMaker Model Registry の `ModelApprovalStatus` |

## テストを書き換えてよい理由
既存のテストは日本語メッセージに `pytest.raises(match="絶対関門")` で依存していた。文言を直すとこれが失敗する。
「テストを書き換えて成功させない」というルールが禁じているのは、**挙動を変えたのにテストを弱めて緑にする**こと。
ここで変えるのは文言だけで、挙動は変えていない。それを自己申告にしないために、T-0170 で
**文言に依存しない characterization テスト**を先に置いてある。

このコミットで確かめられること：
- `tests/test_promotion_characterization.py` は**差分に現れない**（`git status` で確認）。挙動を守る側は無変更。
- 書き換えたのは文言に結びついた `match=` の 4 か所だけで、いずれも**より強い**照合に置き換えた
  （文字列の部分一致 → 落ちた判定の `kind`・`reason` の構造比較）。

## あわせて直したもの
- **`change_threshold` の判定順の欠陥**：baseline 不在（初回昇格）を先に見ていたので、候補が primary 指標を
  測っていないときに素通りしていた。候補の未測定を先に見るよう直した（テスト先行）。
  抽出前は `promote_*` 側の `if primary not in record.metrics` が担っていた検査で、抽出時に落としていた。
- **例外に構造を持たせた**：`gates.PromotionError`（`ValueError` の下位型なので CLI の `except ValueError` は
  そのまま効く）が `decision` を持つ。呼び手はメッセージを解析しなくてよい。
- **落ちた判定を全件出す**。以前は最初の 1 件で止めていたので、閾値を直して再実行すると今度は比較で落ちる、
  という往復が起きていた。
- **テスト関数名の造語**（`absolute_and_relative_gates`・`relative_reject`）も改名し、`verified_by` で
  参照している完了済みの 3 タスク（T-0016・T-0090・T-0120）の記録も同時に直した（指す先が無いと `pm.lint` が失敗する）。
- `src/`・`tests/`・`templates/` から「関門」を一掃した（`work/`・`docs/archive/` は当時の記録なので残す）。
- 改善量の表示を丸めた（`-0.30000000000000004` は引き算の桁で、読む人には無意味）。

## 受け入れ基準
- `grep -rn 関門 src/ tests/ templates/ docs/`（archive を除く）が 0 件。
- `tests/test_promotion_characterization.py` が差分に現れない。
- 落ちた判定が 2 つあるとき、メッセージに 2 つとも出る。
- `uv run verify` 全成功。
