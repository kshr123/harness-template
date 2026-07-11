---
id: T-0211
kind: task
status: todo
title: stats extra（pymc・nutpie・arviz）を pyproject に足し、3.14 で入ることを日付つきで確定する
created: 2026-07-11
depends_on: []
verified_by: []
---
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
