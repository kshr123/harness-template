---
id: T-0212
kind: task
status: todo
title: harness/stats プロファイルの器を作る（profile.py・docs/stats.md・テスト glob・config 並記）
created: 2026-07-11
depends_on: [T-0211]
verified_by: []
---
# T-0212 stats プロファイルの器

## 何が問題か
`Profile(name, pm_checks, test_globs)` は config 駆動の import（`src/harness/profiles.py`）なので
`profiles = ["harness.ds", …, "harness.stats"]` と並記できるが、`src/harness/stats/` がまだ存在しない。
器（プロファイル境界・ドキュメント正本・テストの所有宣言）が無いと、以降のタスクが置き場を持てない。

## やること
- `src/harness/stats/__init__.py`・`src/harness/stats/profile.py`（`PROFILE = Profile(name="stats", …)`）。
  ds の profile.py と同じ規約：重い依存（pymc 等）を top で import しない（extra 未導入でも import できる）。
- `test_globs` に stats のテスト（例 `test_stats_*.py`）を宣言する（`profiles = []` の複製で収集・型検査から
  外れる仕組みに乗る）。
- `.harness/config.toml` の `profiles` に `harness.stats` を並記する。
- `docs/stats.md` を新設する（code_doc_lint の正本。この時点では境界の宣言＝「何を ds と共有し、何を
  共有しないか」だけ書く。共有する：Registry・storage・fingerprint・config・GATES・results/ の作法。
  共有しない：sklearn Pipeline・run_cv・METRICS・leaderboard・FORMATS）。

## やらないこと
- レジストリ・推論コードは入れない（T-0213 以降）。
- CLI は作らない（T-0218）。
- 恒久ドキュメントに `work/EP-…` への参照を書かない（doc_source_lint）。

## 受け入れ基準
- `uv run verify` 全成功（code_doc_lint が `docs/stats.md` を正本として受け付ける）。
- `profiles` から `harness.stats` を外した（または `profiles = []` の）状態で pytest の収集が
  stats のテストを含まない（プロファイル分離の既存テストの作法で確かめる。集合は `test_globs` から導出）。
- `harness.stats` の import が pymc 未導入の環境でも成功する（遅延 import の規約）。
