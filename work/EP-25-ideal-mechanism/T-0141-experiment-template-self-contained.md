---
id: T-0141
kind: task
status: done
title: 実験雛形を完全自己完結にする（schema を templates へ・load_schemas に templates スコープ追加）
requirements: [REQ-001]
depends_on: [T-0140]
closed: 2026-07-07
verified_by:
  - tests/test_e2e_experiment.py::test_e0001_smoke
  - tests/test_e2e_experiment.py::test_e0001_regression_smoke
  - tests/test_e2e_experiment.py::test_e0001_multiclass_smoke
  - tests/test_ds_schema.py::test_load_schemas_reads_template_scope
---
# T-0141 実験雛形の完全自己完結（T-0140 の残課題を解決）

## 狙い（なぜ *より理想* になるか）
T-0140 で実験雛形（train.py・config）を `templates/experiment/`（残す領域）へ移したが、`train.py` が schema 解決で
`work/EP-06/E-0001/data`（消す領域）を**後方参照**する残課題が残った（`_E0001_SCHEMA_DIR`）。「残す領域の資産が
消す領域を参照する」のは T-0140 の自己完結目的への部分的矛盾＝複製先が work/ を消すと雛形の full/--test が schema を
見失いうる。**schema 定義を雛形に持ち歩かせて完全自己完結にする。**

## 事実（着手時に確認済み）
- `load_schemas(root)`（`src/harness/ds/schema.py`）は **共有＝`docs/data/*.yaml`** と **実験スコープ＝`root/work/**/data/*.yaml`**
  だけを glob する（templates/ は読まない）。`store.save/load`（`ds/store.py`）と data-lint（`ds/cli.py`）が消費。
- `work/EP-06/E-0001/data/*.yaml`（5 本：`e0001_folds`・`e0001_oof_baseline/interaction/mc_baseline/reg_baseline`）は
  **テーブル定義（schema）**＝この train.py が毎回生成する folds/oof の**構造定義**（run 固有の値でなく雛形材料）。
- `train.py::prepare_root` は temp/`--root` 時に `_E0001_SCHEMA_DIR` から `root/work/E-0001/data/` へ schema を copy し、
  full 時（repo 根）は copy せず repo 根の `work/E-0001/data` に在る前提。
- テストは schema **ソース位置**を直接参照しない（e2e は生成物 parquet を tmp で見るだけ）。schema を移しても e2e は不変。

## 設計（確定）＝schema を templates へ・load_schemas に templates スコープ追加
1. **schema を移動**：`git mv work/EP-06/E-0001/data/*.yaml → templates/experiment/data/`（train.py と同居＝雛形が持ち歩く）。
   `work/EP-06/E-0001/data/` は空になる（run 出力の parquet は元々 gitignore の生成物なので空でよい）。
2. **`load_schemas` に templates スコープを追加**：`docs/data`（共有）・`work/**/data`（実験）に加え
   **`templates/**/data/*.yaml`（雛形提供）**も読む。これで full モード（repo 根）と data-lint が templates の schema を見つける
   （`work/**/data` と対称の 1 行追加）。docstring・schema.py 冒頭コメント（正本の置き場）も更新。`templates/**/data` は
   現状 `templates/experiment/data` だけがマッチ（k8s/compose は `data/` 配下でない）。
3. **train.py**：`_E0001_SCHEMA_DIR = HERE / "data"`（templates 同居＝後方参照が消える）。`prepare_root` の copy ロジックは
   temp/`--root` 用に維持（temp root には templates/ が無いので、雛形の `HERE/data` から `root/work/E-0001/data` へ copy する
   のは不変・ソースが work→templates に変わるだけ）。full モードは load_schemas が templates を読むので copy 不要のまま。
4. **導線・記録**：`work/EP-06/E-0001/item.md` の T-0140 注記を「schema 定義も `templates/experiment/data/` へ移設（T-0141）＝
   再現記録は results/ が保持」に更新。`docs/template-copy.md` の「残す」に `templates/experiment/data/`（雛形の schema）が
   含まれることを確認（`templates/experiment/` 配下なので既に「残す」に入っているはず・必要なら 1 語補足）。
   schema.py 冒頭の「正本の置き場」列挙に templates を追加＝doclint/参照の整合。

## 受け入れ基準（detailed）
- `templates/experiment/data/*.yaml`（5 本）が存在し、`work/EP-06/E-0001/data/` に schema yaml が無い（後方参照が消える）。
- `train.py::_E0001_SCHEMA_DIR` が `HERE/"data"`＝`work/` を指さない（`grep` で `work/EP-06` 参照が train.py から消える）。
- `load_schemas` が `templates/**/data/*.yaml` も読む（新テスト `test_load_schemas_reads_template_scope` で固定）。
- e2e スモーク（binary/regression/multiclass）が緑・data-lint 緑（templates の schema を検証）・done 実験 E-0001 の pm 検査が緑
  （results/ が残る）。`uv run verify` 全成功。

## 効かせる guard（maker≠checker・このミューテーションで RED）
1. `load_schemas` から templates スコープの glob を外す → `test_load_schemas_reads_template_scope` が RED
   （＋full モード/data-lint が e0001 schema を見失う）。
2. `templates/experiment/data/` の schema（例 `e0001_folds.yaml`）を壊す/消す → e2e スモークが RED（store.save の検証が落ちる）。
3. `_E0001_SCHEMA_DIR` を古い work パスへ戻す → 複製自己完結の退行（templates に schema がある今、work パスは空＝
   temp copy が空になり e2e RED）。

## 触ってはいけない核
train.py の実験意味論・`--test` 契約・results の指紋検査・done 実験の pm 検査・`ExperimentSpec`・store.save/load の検証契約・
`docs/data`（共有）と `work/**/data`（実験）の既存スコープ（templates を**足す**のであって既存を消さない）。

## verified_by
- `tests/test_e2e_experiment.py::{test_e0001_smoke,test_e0001_regression_smoke,test_e0001_multiclass_smoke}`
  （雛形が templates の schema で自己完結して実行できる）
- `tests/test_schema.py::test_load_schemas_reads_template_scope`（新規＝templates スコープが読まれる。実ファイル名は
  着手時に grep で確認し test_schema.py が無ければ test_data_lint.py 等 schema を扱う既存ファイルへ）

## やらないこと
`docs/data`/`work/**/data` の既存スコープの削除／run 出力 parquet の版管理（生成物）／results・SPEC の移動（再現記録は work）／
schema の意味論・store の検証契約の変更／新 CLI・スキル／verify に network／実験機構の他部分の作り替え。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE）
設計＝Opus（T-0140 残課題の解決・事実調査に基づく）・実装＝sonnet・レビュー＝Opus（別モデルが実装＝maker≠checker 成立）。
他ターミナルの EP-24（docs 造語掃除）と並行・統合ツリーで実測。
- **faithfulness**：schema 5 本を `git mv` で `templates/experiment/data/` へ（work/E-0001/data は schema yaml が空・results/
  は残置）。`load_schemas` に templates スコープ（`templates/**/data`）を work と対称に 1 ブロック追加・既存スコープ（docs/data・
  work/**/data）は不変・docstring/module コメントも更新。train.py `_E0001_SCHEMA_DIR = HERE/"data"`（work/ 後方参照が消滅）・
  prepare_root の copy ロジックは temp/root 用に不変（ソースだけ work→templates）。✓
- **G1**（`load_schemas` から templates glob を外す）→ `test_load_schemas_reads_template_scope` が RED（＋full/data-lint が
  templates schema を見失う）。✓
- **G3（自己完結の退行検知）**（`_E0001_SCHEMA_DIR` を旧 work パスへ戻す）→ e2e スモークが RED。work/E-0001/data は今や空
  なので、旧 work 参照に戻すと temp copy が空になり store.save の検証が落ちる＝**「残す領域が消す領域を参照する」退行を機械が
  止める**。復元 IDENTICAL。✓
- **自己完結の実測（実装者・確認）**：`templates/experiment/` だけを work/ 無しで scratch にコピーし
  `python train.py --test --root <tmp>` → passed=True・EXIT=0。複製先が work/ を消しても雛形が自立する＝残課題そのものの解消。✓
- **触ってはいけない核の不変**：実験意味論・`--test` 契約・results 指紋・done 実験 pm 検査・store 検証契約・既存 schema スコープ
  ＝いずれも無変更。他ターミナル（EP-24 docs 本文）の領域に触れていない。✓
- `uv run verify` 全成功。**APPROVE**（T-0140 の残課題を完全に解決）。
