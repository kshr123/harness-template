---
id: T-0137
kind: task
status: done
title: templates 資産のオーナー検査ラチェット（資産を足したら腐敗防止検査のオーナーも足す＝verify 強制）
requirements: [REQ-001]
depends_on: [T-0140]
verified_by:
  - tests/test_structure.py::test_templates_have_owner_checks
---
# T-0137 templates 資産のオーナー検査ラチェット（抜本1・機械検査）

## 狙い（なぜ *より理想* になるか）
T-0140 で `templates/` は `ci`・`schedule`・`serve`・`experiment` の 4 資産になり、各々に「腐らせない検査」が対応する
（ci→`ops.ci_lint`／schedule→`agent.schedule_lint`／serve→`serve.deploy_lint`／experiment→`tests/test_e2e_experiment.py`）。
この対応を**機械化**する：「templates/ に資産を足したら、腐敗防止検査のオーナーも同じタスクで足す」を verify が強制する
ラチェット。DEC-0009（部品は入口まで作って完了）の templates 版＝進化のたびに検査が自動でついてくる。
**これはコードの構造不変条件**（「templates/ 直下の資産集合＝宣言済みオーナー表のキー集合」）＝機械化の射程内
（owner 決定 2026-07-07：構造は機械化・文書規律は規約。EP-24 rollback と整合）。

## 設計（fable 詳細設計・確定）
- **`tests/test_structure.py` に写像テスト `test_templates_have_owner_checks` を追加**（`test_new_structure_layout` と同居）。
- **オーナー表（テスト内の宣言・理由必須）**：`_TEMPLATE_OWNERS = { "ci": ("harness.ops.ci_lint", "..理由.."),
  "schedule": ("harness.agent.schedule_lint", ".."), "serve": ("harness.serve.deploy_lint", ".."),
  "experiment": ("tests/test_e2e_experiment.py", "..") }`。値＝(オーナー参照, 理由)。coverage_lint の `_EXEMPT`／
  ci_lint の `_WORKFLOWS` と同型（黙って見逃さない・理由必須）。
- **検査 (a) キー集合の一致（ラチェットの心臓）**：`set(d.name for d in (root/"templates").iterdir() if d.is_dir())`
  ==（`_TEMPLATE_OWNERS` のキー集合）。**templates/ に未登録ディレクトリを足すと RED**（オーナーを書くまで done にできない）・
  表にあるが実体が無い（資産削除の取り残し）も RED。
- **検査 (b) オーナー参照の実在（腐り検知）**：各オーナー参照が実在する——`harness.*` はモジュールとして import 可能
  （`importlib.util.find_spec`）、`tests/*.py` はファイルが存在。表に書いた検査が消えたら RED。
- **理由文の非空**：各エントリの理由が非空（`_EXEMPT` と同型・fail closed）。
- **CLI/スキル导线は不要**（新 CLI を足さない・既存テストへの追加のみ＝coverage_lint の対象外）。

## 受け入れ基準（detailed）
- `tests/test_structure.py::test_templates_have_owner_checks` が存在し、templates/ 直下の全ディレクトリがオーナー表に
  登録され・各オーナーが実在し・理由が非空、を検査する。
- 未登録の templates/ ディレクトリを足すと RED（ラチェットが効く）。
- `uv run verify` 全成功（現状の 4 資産はすべて登録済みで緑）。

## 効かせる guard（maker≠checker・このミューテーションで RED）
1. `templates/` に未登録ディレクトリ（例 `templates/foo/`）を作る → `test_templates_have_owner_checks` が RED
   （オーナー未登録を検知＝ラチェットの心臓）。
2. オーナー表のエントリのオーナー参照を実在しないモジュール/ファイルに変える → 同テストが RED（腐り検知）。
3. オーナー表からエントリを削る（が templates/ には資産が残る）→ 同テストが RED（キー集合不一致）。

## 触ってはいけない核
各 lint（ci_lint/schedule_lint/deploy_lint）の中身・PmCheck 配線・e2e の実体・`test_new_structure_layout`・verify の fail-closed。

## verified_by
- `tests/test_structure.py::test_templates_have_owner_checks`（新規＝templates 資産↔オーナーの一致・実在・理由）

## やらないこと
各 lint の中身の変更／新 CLI・スキル（既存テストへの追加のみ）／オーナー表を機械可読の別レジストリに昇格
（消費者 1 つ＝このテストだけ・DEC-0012 で 2 個目の消費が出るまで表はテスト内に置く）／文書/散文の機械検査
（機械化の射程は構造だけ・文書規律は規約＝T-0138/0139 の方針）。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE）
設計＝fable・実装＝sonnet・レビュー＝Opus（別モデル）。統合ツリー（origin/main=88fffb5）で実測。
- **faithfulness**：`tests/test_structure.py` のみ変更。`_TEMPLATE_OWNERS`（4 資産→(オーナー参照, 理由)・coverage_lint
  `_EXEMPT`／ci_lint `_WORKFLOWS` と同型・理由必須）＋(a) キー集合一致（実 templates/ を動的に読む＝金メッキ回避）
  ＋(b) オーナー実在（`harness.*`＝find_spec／`tests/*.py`＝is_file）＋(c) 理由非空。`@pytest.mark.unit` で module 既定
  （integration）を上書き（test_ds_models の先例に倣う）。`test_new_structure_layout`・各 lint は無変更。✓
- **G-unregistered**（`mkdir templates/__probe__`）→ RED（"未登録ディレクトリ: ['__probe__']"）＝ラチェットの心臓
  （資産を足したらオーナーも足す、を verify が強制）。`rmdir` で緑復帰。✓
- **G-rot**（オーナー参照を `harness.ops.NOPE_ci_lint` に変更）→ RED（腐り検知＝表の検査が消えたら気づく）。復元 IDENTICAL。✓
- **機械化の射程との整合**：本タスクは「templates/ 直下の資産集合＝オーナー表のキー集合」というコードの構造不変条件の
  機械化＝owner 決定（構造は機械化・文書規律は規約）の射程内。文書/散文の機械検査は足していない。✓
- `uv run verify` 全成功。**APPROVE**。
