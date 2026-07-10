---
id: T-0166
kind: task
status: done
title: retrain.yml の壊れた参照・指標名・work を直し、ci_lint にスクリプト参照の実在検査を追加
created: 2026-07-10
depends_on: [EP-27]
verified_by:
  - tests/test_ci_lint.py::test_missing_script_reference_flagged
  - tests/test_ci_lint.py::test_existing_script_reference_not_flagged
  - tests/test_ci_lint.py::test_placeholder_script_reference_not_flagged
  - tests/test_ci_lint.py::test_repo_retrain_template_passes
---
# T-0166 retrain.yml の 3 つの欠陥と ci_lint の穴を直す

## 背景
`templates/ci/.github/workflows/retrain.yml` は複製先が編集する前提の雛形だが、既定のままだと必ず失敗する
3 つの欠陥があった。

1. 再学習 step が `work/EP-06-ds-experiment-loop/E-0001-interaction-feature/code/train.py` を実行する。
   このファイルは存在しない（実験の雛形は T-0140 で `templates/experiment/train.py` へ移設済み。
   `work/EP-06-.../E-0001-.../` には `item.md`・`SPEC.md`・`results/` しか残っていない）。
2. 昇格 step が `thresholds={"auc": 0.85}, primary="auc"` を使う。`auc` は `harness.ds.eval.METRICS` に
   未登録の指標名（正しくは `roc_auc`）で、`promote_model` は未登録名で `ValueError` を送出する。
3. 昇格 step の `work="EP-06-ds-experiment-loop/E-0001-interaction-feature"` が、
   `templates/experiment/train.py` の保存先 `WORK_ID = "E-0001"` と一致せず `FileNotFoundError` になる。

`src/harness/ops/ci_lint.py` は「`train.py` という断片を含む step があるか」しか見ておらず、
1 の腐敗（参照先の非実在）を検出できなかった。

さらに `templates/experiment/data/*.yaml`（5 ファイル）の `lineage.code` が、複製時に消える
`work/EP-06-ds-experiment-loop/E-0001-interaction-feature/code/train.py` を指していた
（`templates/experiment/train.py` 自身の `CODE_REF` と食い違っていた）。

`docs/template-copy.md` の課題引き継ぎの記述も、`issues/ISS-0002`〜`0005` を一律の例として挙げていたが、
`ISS-0002`・`0003`・`0004` は `state: resolved` かつ `promoted_to`（`T-0069`・`T-0068`・`T-0052`）を持つため、
手順どおり `work/` を消すと `src/harness/issues.py` が「promoted_to の指す先が無い」を error にする。
引き継げるのは `promoted_to` を持たない `ISS-0005` だけだった。

## やったこと
1. `ci_lint` に「`templates/ci/**/*.yml` の各 step の `run` が参照するリポジトリ内の `.py` の実在」検査を
   追加した（`_check_script_refs`）。抽出はトークン全体が英数字・`_`・`.`・`/`・`-` だけのものに限る保守的な
   方式＝`$VAR`・`<...>` のようなプレースホルダはこの文字集合に収まらないため対象外（誤検知しない）。
   `_WORKFLOWS` 表に載っていないワークフロー yml も対象（全ワークフロー共通の検査）。
2. `retrain.yml` の 3 点を直した：train.py の参照を `templates/experiment/train.py` に、
   `auc` を `roc_auc` に、`work=` を `"E-0001"`（train.py の `WORK_ID`）に、それぞれ合わせた。
3. `templates/experiment/data/*.yaml`（5 ファイル）の `lineage.code` を `templates/experiment/train.py`
   （`CODE_REF` と同じ）に揃えた。
4. `docs/template-copy.md` の課題引き継ぎの記述を、「`promoted_to` を持たない open の課題だけ残せる。
   `promoted_to` が付いた resolved 済みは必ず消す」という趣旨に直し、現存で該当するのが `ISS-0005` だけで
   あることを本文に明記した。

## 検査の期待値の導出
`tests/test_ci_lint.py` の `_copy_templates` は実テンプレート（`templates/ci`・`templates/experiment`）を
一時ディレクトリへコピーする「生きた fixture」。新しい検査のテストは、この fixture の run コマンドへ
実在しない `.py` 参照を追記する／実在する参照に差し替える／プレースホルダを混ぜる、という構成の差分から
error の有無を導く（実装の出力を写した固定値ではない）。

検査を実装した直後（retrain.yml を直す前）は `test_repo_retrain_template_passes`
（自リポの retrain.yml を検査して 0 件を期待する回帰の番人）が、
`work/EP-06-ds-experiment-loop/E-0001-interaction-feature/code/train.py` の非実在を検出して失敗することを
確認した。retrain.yml を直した後は緑に戻る。

`uv run verify` 全成功。
