---
id: T-0173
kind: task
status: todo
title: 昇格の保存機構を中核（harness/promotion.py）へ 1 本化する（挙動は変えない）
created: 2026-07-10
depends_on: [T-0172]
verified_by: []
---
# T-0173 昇格の保存機構を中核へ

## 何が問題か
`champion()`・`promote_*()`・`Promotion` データクラス・定数（`MANIFEST_FILE`・`PROMOTIONS_DIR`・
`VERSION_FORMAT`）が `src/harness/ds/models.py` と `src/harness/agent/store.py` にほぼ逐語で複製されている。
`agent/store.py` の冒頭コメントは「プロファイル境界を守るため `harness.ds` を import しない」と説明するが、
それは**複製の理由にならない**。同じ問題は `storage.py` で既に解いてある（データ・モデル・スキーマに複製されて
いた保存の作法を中核へ 1 本化し、方針は呼び手に残した）。同じ手をここにも当てる。

放置すると次の 2 タスク（alias・切り戻し）を 2 か所に書くことになり、複製が倍になる。

## 構造
`src/harness/promotion.py`（中核。stdlib＋`harness.storage`＋`harness.gates` だけに依存）。
`storage.py` と同じ方針で **仕組みだけを持ち、方針は呼び手が持つ**（policy-free）：

- 仕組み＝記録の置き場（`promotions/<decided>.yaml`）・記録の読み書き・champion の解決・判定の実行。
- 方針＝どのレジストリで指標の向きを解決するか（ds は `METRICS`・agent は `AGENT_METRICS`）、
  primary に何を選ぶか、閾値をいくつにするか。これらは呼び手が解決してから渡す。

これで agent は ds を import しないまま複製を捨てられる（境界は壊れない・むしろ強くなる）。
`serve` プロファイルも champion 解決のために ds を経由する必要が無くなる（本タスクでは配線を変えない）。

## 受け入れ基準
- `promote_model` / `promote_agent` / `champion` の**挙動が変わらない**。証拠は
  「既存テストを 1 行も変更せずに全成功」（`git status --porcelain tests/` に既存ファイルが現れない）。
- `harness.promotion` は `harness.ds` / `harness.agent` を import しない（中核はプロファイルを知らない）。
- 記録の YAML の書式・キーの順序が変わらない（既存の保存を読めなくしない）。
- `uv run verify` 全成功。

## 既知の軽微な差（独立レビュー 2026-07-10・移送時に意識して決めること）
抽出前は、閾値名の typo（`ValueError`）を現 champion の読み込みより先に検出していた。今は
`directions()` の呼び出しが champion 読み込みの後にある。**現 champion の昇格記録が壊れている**かつ
**閾値名が typo** という二重故障のときだけ、先に出るメッセージが変わる。例外型は同じ `ValueError` で
実害は無い。中核へ移すときに順序を決め直すので、ここで意識的に選ぶ（黙って変えない）。

## やらないこと
- alias（`aliases/champion.yaml`）の導入は T-0174。切り戻しは T-0175。ここでは `sorted(glob)[-1]` の
  欠陥をそのまま移送する（欠陥を直すのと構造を変えるのを同じコミットに混ぜない）。
- `_git_provenance` / `_dependencies` / `_lock_fingerprint` / `_utcnow` の複製は別課題（ISS へ）。
