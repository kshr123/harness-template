---
id: T-0173
kind: task
status: done
title: 昇格の保存機構を中核（harness/promotion.py）へ 1 本化する（挙動は変えない）
created: 2026-07-10
closed: 2026-07-11
depends_on: [T-0172]
verified_by:
  - tests/test_promotion_characterization.py::test_ds_only_a_strict_improvement_promotes
  - tests/test_promotion_characterization.py::test_ds_promotion_record_has_the_expected_fields
  - tests/test_promotion_characterization.py::test_agent_only_a_strict_improvement_promotes
  - tests/test_promotion_characterization.py::test_agent_promotion_record_has_the_expected_fields
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
- `_git_provenance` / `_dependencies` / `_lock_fingerprint` / `_utcnow` の複製は別課題（ISS-0016 に起票）。

## 実装の結果（このタスクで確定したこと）
- 中核 `src/harness/promotion.py` を新設し、`Promotion` 型・定数（`MANIFEST_FILE`・`PROMOTIONS_DIR`・
  `VERSION_FORMAT`）・`champion_version`・`promote` を集めた。依存は stdlib＋`harness.storage`＋`harness.gates`
  だけ（ds/agent のレジストリは import しない）。`ds/models.py`・`agent/store.py` は方針だけを持つ薄い呼び手に
  縮退（向きの正本レジストリの解決・higher_is_better の矛盾検査・保存の存在確認だけを残す）。
- `AgentPromotion` は `promotion.Promotion` の別名として公開名を保った。
- 記録 YAML の書式・キーの順序・却下メッセージ（`{work}/{name}/{version} は昇格を却下（rejected）: …`）は不変。
  既存テストは 1 行も変更していない（`git status --porcelain tests/` に既存ファイルが現れない）ことが挙動不変の証拠。

### 順序の決定（既知の軽微な差＝閾値名 typo と champion 読み込みの順序）
**「向きの解決（`directions([*thresholds, primary])`）を、現 champion の読み込みより先に行う」** を選んだ。
実装上は、呼び手（ds/models・agent/store）が `directions(...)` を解決してから中核 `promotion.promote` を呼び、
champion の読み込みは中核の中で起きる＝引数評価が先なので必ず「向きの解決 → champion 読み込み」の順になる。

理由：閾値名の typo は呼び手が書いた spec の誤りで、保存側の状態（champion が壊れているか）に依存しない。
呼び手が制御できる誤りを先に、確定的なメッセージで返す方が直しやすい。二重故障（champion の昇格記録が
壊れている＋閾値名が typo）でも、まず「その閾値名は未登録」を返す。これは抽出前の並びと同じで、例外型は
どちらの順でも同じ `ValueError`。既存テストはこの二重故障を突かないので、どちらの順でも全成功する
（＝意識して選ぶべき差であり、黙って変えてよい差ではない）。
