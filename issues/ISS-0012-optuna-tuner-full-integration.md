---
id: ISS-0012
kind: question
state: resolved
found_in: T-0057
created: 2026-07-06
closed: 2026-07-18
promoted_to: T-0230
title: optuna チューナーの完全統合（extra 追加＋テスト経路＋data tuners コマンド）
---
> 解決（2026-07-18・T-0230）：Python 3.14 で optuna>=4＋optuna-integration>=4 が入ることを実測し、pyproject に
> optuna extra を追加（--all-extras に入る）。OptunaSearchCV のテスト（良い側を選ぶ・importorskip）を足した。
> data tuners の CLI は T-0066 で完了済み。3 つの残タスクがすべて閉じた。

# ISS-0012 optuna チューナーの完全統合

## 事象
T-0057（チューニング継ぎ目）で optuna チューナー（OptunaSearchCV）を条件登録したが、当リポの verify 環境
（`uv sync --all-extras`）に optuna/optuna-integration が入っていない＝optuna 経路は登録コードがあるのに CI で
一度も実行されない。加えて `Registry(catalog="data tuners")` の案内が指すコマンド `uv run data tuners` は
CLI 未配線（cli.py に無い）。random/grid/halving（sklearn 素通し）は全経路テスト済み。

## 根拠・影響
- 「開発・verify 環境は all-extras＝optional のテストを skip しない」（AGENTS.md）の趣旨に対し、optuna だけ抜ける。
- optuna>=4 で OptunaSearchCV は別配布物 `optuna-integration`（`optuna_integration`）へ移管済み。T-0057 では検出を
  `_optuna_available()`（新旧両配置を find_spec）に、import を新旧フォールバックに直し、extras_hint も設定済み
  （「登録されるのに使えない」罠は解消）。残るのは「実際に入れてテストする」こと。

## 対処（決めたら）
1. pyproject に `optuna = ["optuna>=4", "optuna-integration>=4"]` extra を足し、all-extras に含める。
2. `tests/test_ds_tune.py` に OptunaSearchCV 経路のテスト（`pytest.importorskip("optuna_integration")`＋小さな探索が良い側を選ぶ）。
3. ~~CLI に `data tuners`（`render_catalog(TUNERS)`）を足す~~ → **T-0066 で完了**（`data selectors`/`data tuners` を配線・
   test_catalog_commands_run が出力を検査）。残るは 1（optuna extra 追加）・2（optuna 経路のテスト）＝依存が重いので owner 判断。
- 依存が重い（optuna＋optuna-integration）ので、入れるかは owner 判断。当面は random/grid/halving で十分（seam は完成済み）。
