---
id: T-0228
kind: task
status: done
title: 来歴ヘルパ 4 つを harness.provenance に 1 本化（ds/models・agent/store の逐語複製を解消）
created: 2026-07-18
closed: 2026-07-18
depends_on: []
verified_by:
  - tests/test_provenance.py::test_git_provenance_reads_commit_and_branch
  - tests/test_provenance.py::test_dependencies_reports_installed_and_skips_missing
  - tests/test_provenance.py::test_lock_fingerprint_matches_storage_fingerprint
  - tests/test_provenance.py::test_git_provenance_none_outside_a_repo
---
# T-0228 来歴ヘルパを harness.provenance に 1 本化

## 事象
保存物の由来書き（provenance）を集める 4 関数 `_git_provenance`・`_dependencies`・`_lock_fingerprint`・
`_utcnow` が `ds/models.py` と `agent/store.py` にほぼ逐語で複製されていた。片方だけ直す退行（encoding の
明示や dirty の定義を一方でだけ直す等）が起きうる＝黙って不整合になる経路（条件(2)）。

## 直し方
- 新設 `src/harness/provenance.py`（policy-free な中核部品＝`storage.py` と同じ層。昇格判定でも保存形式でも
  ない）に `utcnow()`・`dependencies(tracked)`・`git_provenance(root)`・`lock_fingerprint(root)` を置く。
  `dependencies` は追跡する配布物の集合を引数で受ける（models と store で集合が違うため）。
- `ds/models.py`・`agent/store.py` は本体を消して `provenance.*` を直接呼ぶ。**ただし `_utcnow` だけは
  各モジュールに薄い委譲（`return provenance.utcnow()`）を残す**：テストが `module._utcnow` を monkeypatch で
  固定する入口だから（版＝時刻なので再利用拒否・順序の検査に使う）。
- docs/core.md の相互運用契約の表に `provenance.py` を 1 行追加（code_doc_lint の順向き検査に対応）。

## 受け入れ基準（満たした・verify 緑）
- 挙動を tests/test_provenance.py で固定（git 来歴・依存版・lock 指紋・非 git リポで None）。
- 既存の `_utcnow` を monkeypatch する保存・昇格テスト（ds/agent 両方）がそのまま通る＝差し替え点は保った。
