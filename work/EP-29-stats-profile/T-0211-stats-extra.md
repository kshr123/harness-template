---
id: T-0211
kind: task
status: done
title: stats extra（pymc・nutpie・arviz）を pyproject に足し、3.14 で入ることを日付つきで確定する
created: 2026-07-11
depends_on: []
verified_by:
  - tests/test_stats_stack.py::test_stats_stack_imports
  - tests/test_stats_stack.py::test_inference_data_netcdf_roundtrip
---
## 実装（done・2026-07-13）
- pyproject に extra `stats = [pymc>=6.0, nutpie>=0.16, arviz>=1.2, h5netcdf>=1.0, h5py>=3.0]`。netCDF 保存は
  h5netcdf バックエンドが h5py を要求するため両方を明示（実測：h5py が無いと to_netcdf が ImportError）。
- **all-extras 共存を確認**：pymc 経由の numba 0.65.1（cp314 wheel あり）が numpy を 2.4.6 に固定し、
  `uv sync --all-extras` 全体が 2.4.6 に揃う。既存の全 verify（ruff・mypy・pytest）は 2.4.6 で緑（numpy 型
  スタブ差で出た 3 箇所を修正：unsupervised.py の adapter・scoring.py の y_true 型）。環境分割は不要。
- 実行の実測：pymc 既定サンプラー・nutpie の両方で最小モデルの pm.sample が走り、r_hat/ess/divergences を
  arviz 1.2 で取得できる。netCDF の保存→読込一往復が値まで一致（test_stats_stack）。
- **arviz 1.2 の API 差を記録**（T-0217 で使う）：from_dict は `{group: {var: arr}}` の入れ子・az.loo の戻りは
  `.elpd_loo` 属性を持たない（1.x で ELPDData の形が変わった）。

# T-0211 stats プロファイルの依存を optional extra にする

## 何が問題か
stats プロファイルの依存（pymc・nutpie・arviz）はまだ pyproject に無い。依存の可否は日付つきの事実で
すぐ古くなるので、「載る」と計画に書いてあるだけでは着手できない（L-020）。

計画時点の実測（2026-07-11・PyPI JSON 直読）：
- nutpie 0.16.11：cp314 wheel あり（`requires_python >= 3.12`）
- pytensor 3.1.2：cp314 wheel あり（`>= 3.12, < 3.15`）
- pymc 6.1.0・arviz 1.2.0：pure-python wheel
- `uv pip install --dry-run pymc nutpie arviz` は 3.14 venv で解決に成功（pytensor 3.1.2 が選ばれる）

## やること
- pyproject の optional extra `stats` に pymc・nutpie・arviz を足す（lightgbm・statsmodels と同じ作法）。
- `InferenceData` の netCDF 保存に要るライブラリ（netcdf4 か h5netcdf。**どちらが 3.14 に入るかは未確認**）を
  実測して extra に含める。両方入らなければ zarr 等の代替を実測し、結論を本ファイルに日付つきで書く。
- `uv sync --all-extras` の環境で `import pymc, nutpie, arviz` と、極小の `InferenceData` の保存→読込の一往復が
  動くことを確かめる（開発・verify 環境は全部入りの規約）。

## やらないこと
- `src/harness/stats/` のコードは書かない（器は T-0212）。
- pin の固定（バージョン上限）は根拠が出るまで書かない。

## 受け入れ基準
- `uv sync --all-extras` が 3.14 で成功し、`uv run verify` が全成功（既存テストに一切手を入れない）。
- `.venv` で `import pymc, nutpie, arviz` が成功する（別の立場が同じコマンドで確かめられる）。
- `InferenceData` の保存→読込の一往復が成功する（保存ライブラリの選定が実測で確定している）。
- 実測の結果（版・wheel の有無・日付）が本ファイルに追記されている。
