---
id: T-0135
kind: task
status: done
title: 自前 lint の汎用層純化＋停止宣言の言語非依存化（差し替え）
requirements: [REQ-001]
depends_on: [T-0134]
verified_by:
  - tests/test_agent_schedule_lint.py::test_missing_stop_marker_is_error
  - tests/test_agent_schedule_lint.py::test_stop_marker_without_reference_is_error
  - tests/test_agent_schedule_lint.py::test_schedule_template_commands_resolve
  - tests/test_ci_lint.py::test_retrain_template_out_of_order_steps_flagged
  - tests/test_guardrails.py::test_workflow_lint_wired
---
# T-0135 自前 lint の汎用層純化＋停止宣言の言語非依存化（差し替え）

## 狙い（なぜ *より理想* になるか）
T-0134 で既製バリデータ（actionlint／check-jsonschema）が覆うようになった汎用形式層を、自前 lint から**削って
純化**する。「機械検査の総和を減らさない＝縮小でなく委譲の証明」（DEC-0021）。加えて「停止」の日本語単語 grep
（英語 README の複製先で即壊れる言語過剰適合）を、言語非依存の構造マーカー `# stop:` へ**進化**させる（意味論＝
「止め方の無い routine を作らない」は不変・検出だけ言語非依存に）。緑を保ったまま差し替える（method.md A 節）。

## 前提（T-0134 レビューでの申し送り・CI 被覆の連続性）＝このタスクで先に満たす
自前 lint は `uv run verify`（no-network）で走るが、actionlint/check-jsonschema は現状 pre-commit ローカルのみ。
汎用層を削る前に、**CI（`.github/workflows/ci.yaml`）で actionlint・check-jsonschema を回す配線を先に入れる**
（gitleaks が job3 で `uvx pre-commit run gitleaks --all-files` を回すのと同型）。これをやらずに削ると汎用層の被覆が
「verify/CI で走らないローカルフック」に痩せる＝keep-green-while-replacing 違反。**順序＝(1) CI 配線→(2) 汎用層剥離。**

## 設計（fable 詳細設計＋T-0134 レビュー由来の CI 前提）
### (1) CI 配線（先）
- `.github/workflows/ci.yaml` の秘密情報スキャン job（gitleaks の隣）に 2 ステップ追加：
  `uvx pre-commit run actionlint --all-files` と `uvx pre-commit run check-jsonschema --all-files`。
- `test_guardrails.py::test_workflow_lint_wired` を拡張：CI が両フックを pre-commit 経由で回す（`--all-files` 付き）
  ことを assert（`test_secrets_scan_wired` の CI 検査部と同型）。＝配線が黙って外れたら RED。

### (2) schedule_lint.py の純化（後）
- **削る（actionlint/check-jsonschema が覆う汎用形式）**：`yaml.safe_load` の妥当性検査（monitor が YAML として
  読めるか）・`cron` の 5 フィールド検査（`len(cron.split()) != 5`）。※YAML パース自体は他検査の入力に要るので
  読み込みは残すが、「読めない＝error」を自前で報告する枝は削る（actionlint が構文で落とす）。
- **残す（スキーマで表明できないプロジェクト意味論）**：`_check_permissions`（least-privilege 規約）・
  `on.workflow_dispatch` 存在（手動起動の口）・`on.schedule` に cron が**存在**すること（time-trigger 規約。
  cron の**構文**は actionlint へ委譲・**存在**は自前で残す）・`_check_scripts`（`uv run X` が `[project.scripts]`
  に実在＝腐り検知）。
- **`on:`→bool True 回避（`doc.get("on", doc.get(True))`）**：YAML 読み込みを残す限り必要なので保持（pyyaml の罠。
  ただし「workflow 構造の型」検査は actionlint へ委譲）。
- **停止宣言の言語非依存化**：`_check_stop_comment` の `re.search(r"^\s*#.*停止", ...)` を
  `re.search(r"^\s*#\s*stop:", monitor_text, re.MULTILINE|re.IGNORECASE)` に置換。参照検査（README/docs を指すか）は
  維持。`_check_stop_heading` の `README.md` 側 `r"^#{1,6}\s.*停止"` も `# stop`（英語見出し）を受ける形へ。
  雛形 `templates/schedule/monitor.yml`・`templates/schedule/README.md` を新マーカー/見出しに追従。

### (3) ci_lint.py の純化（後）
- **削る**：YAML 妥当性・workflow 構造の型（actionlint/check-jsonschema が覆う範囲）。
- **残す**：`experiment→monitor→promote` の順序（`ordered=True`）・python-version と requires-python の整合・
  `--all-extras`・scripts 実在（プロジェクト固有意味論）。retrain.yml を壊す順序変異の負テストは維持。

## 受け入れ基準（detailed）
- CI が actionlint・check-jsonschema を pre-commit 経由で回す（`test_workflow_lint_wired` の CI 検査部が通る・外すと RED）。
- schedule_lint/ci_lint から汎用形式検査（YAML 妥当性の error 枝・cron 5 フィールド・構造の型）が消え、意味論検査は残る。
- 停止宣言が `# stop:` マーカー／英語見出しで通り、日本語 `停止` 依存が消える。雛形が追従。
- 削った各検査は「actionlint/check-jsonschema が同じ壊し方を RED にする」実測を差し戻し条件にする（検査の総和を減らさない）。
- `uv run verify` 全成功。

## 効かせる guard（maker≠checker・このミューテーションで RED）
1. `# stop:` マーカーを雛形から消す → `test_missing_stop_marker_is_error` が RED（言語非依存化後も停止宣言を強制）。
2. 停止マーカーの参照（README/docs）を消す → `test_stop_marker_without_reference_is_error` が RED。
3. retrain.yml の step を並べ替え（監視→昇格の順序を崩す） → `test_retrain_template_out_of_order_steps_flagged` が RED。
4. CI から actionlint/check-jsonschema ステップを外す → `test_workflow_lint_wired`（CI 検査部）が RED。
5. （委譲の実測）cron を不正・YAML を壊す → actionlint/check-jsonschema が RED（自前が消えても総和が減らない証明）。

## 触ってはいけない核
`ordered=True` の順序検査・`promote_model` 関門・deploy_lint・`pm.Problem` の error/info 意味論・verify の fail-closed・
gitleaks 配線（`test_secrets_scan_wired`）・T-0134 の wiring（`files:` 上書き）。

## verified_by
- `tests/test_agent_schedule_lint.py::test_missing_stop_marker_is_error`（言語非依存の停止宣言・新仕様）
- `tests/test_agent_schedule_lint.py::test_stop_marker_without_reference_is_error`（参照検査・新仕様）
- `tests/test_agent_schedule_lint.py::test_schedule_template_commands_resolve`（scripts 実在・既存意味論）
- `tests/test_ci_lint.py::test_retrain_template_out_of_order_steps_flagged`（順序・既存意味論）
- `tests/test_guardrails.py::test_workflow_lint_wired`（CI 配線＋files 上書き・T-0134 拡張）
（既存テスト名は着手時に grep で確認し、旧「停止」前提の負テストは新マーカー仕様へ書き換える＝緩めるのでなく仕様追従。）

## やらないこと
意味論検査（permissions・workflow_dispatch・schedule.cron 存在・scripts 実在・順序・停止宣言）の削除／既製が覆わない
プロジェクト固有検査の委譲／CI 配線を後回しにして汎用層を先に削る（keep-green 違反）／k8s・compose へ workflow スキーマ／
新 CLI・スキル／verify に network。

## 実装メモ（sonnet・API エラーで末尾中断→Opus が完了確認）
sonnet 実装が API サーバエラーで「削除テスト名の残存参照確認中」に中断。Opus が状態検査：全対象ファイル実装済み・
`uv run verify` 全緑・削除/改名テスト名の残存参照ゼロ（`停止` の残ヒットは EP-23 の loop 停止条件を語る一般語で
schedule_lint 機構と無関係）＝実装はコヒーレントに完了と判定。順序＝CI 配線（先）→汎用層剥離（後）を守っている。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE）
設計＝fable（＋T-0134 レビュー由来の CI 前提）・実装＝sonnet・レビュー＝Opus（別モデル）。統合ツリー（EP-24 着地済み）で実測。
- **委譲の faithfulness**：schedule_lint から汎用形式（YAML 妥当性の error 枝・dict 構造検査・cron 5 フィールド）を削り、
  意味論（permissions・workflow_dispatch・cron **存在**・scripts 実在）は維持。`on:`→bool True 罠（`doc.get("on", doc.get(True))`）
  は保持。ci_lint も順序（`ordered=True`）・python-version 整合・scripts 実在を維持。停止宣言は日本語 grep→言語非依存
  `# stop:` マーカー（見出しは日英両対応で後方互換）。CI に actionlint・check-jsonschema を gitleaks と同型で配線。✓
- **効かせる guard（4 変異すべて RED を実測・全ファイル byte-identical 復元）**：
  - MUT1 `# stop:` マーカー検査を無力化 → `test_missing_stop_marker_is_error` RED。
  - MUT2 `# stop:` の参照検査（README/docs 参照）を無力化 → `test_stop_marker_without_reference_is_error` RED。
  - MUT3 CI から actionlint ステップを削除 → `test_workflow_lint_wired`（CI 検査部）RED。
  - MUT4 ci_lint の `ordered=True`→`False` → `test_retrain_template_out_of_order_steps_flagged` RED。
- **委譲の実証（検査の総和を減らさない）**：実 `templates/schedule/monitor.yml` の cron を 6 フィールドに壊し
  `uvx pre-commit run actionlint` を実走 → **actionlint が捕捉**（"invalid CRON format ... expected exactly 5 fields, found 6"）。
  自前の cron 検査を削っても被覆は既製へ移っただけ＝縮小でなく委譲を実測で証明。monitor.yml は IDENTICAL 復元。
- **CI 被覆の連続性（T-0134 申し送りの充足）**：汎用層を削る前に CI へ actionlint/check-jsonschema を配線（順序遵守）。
  `test_workflow_lint_wired` の CI 検査部が「配線が外れたら RED」を機械で守る＝keep-green-while-replacing を満たす。✓
- **done タスクの整合**：改名した 2 テストに合わせ T-0097 の verified_by を追従＋改名の来歴を prose 注記（意味論不変・
  空振り verified_by を防止）。旧「YAML error」「cron 5 フィールド」負テストは新スペック（委譲）を pin する形に書き換え
  （緩めるのでなく仕様追従）。✓
- **触ってはいけない核の不変**：`ordered=True` の順序検査・promote 関門・deploy_lint・`pm.Problem` の error/info・
  verify の fail-closed・gitleaks 配線・T-0134 の `files:` 上書き＝いずれも無変更。
- `uv run verify` 全成功。**APPROVE**。
