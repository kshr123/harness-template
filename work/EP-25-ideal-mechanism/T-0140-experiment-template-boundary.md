---
id: T-0140
kind: task
status: done
title: 実験正本雛形を templates/experiment/ へ移設（複製で残る資産の境界を正す）
requirements: [REQ-001]
depends_on: [T-0135]
verified_by:
  - tests/test_e2e_experiment.py::test_e0001_smoke
  - tests/test_doclint.py::test_real_repo_docs_have_no_dead_links
  - tests/test_doclint.py::test_template_copy_paths_resolve
---
# T-0140 実験正本雛形を templates/experiment/ へ移設（差し替え）

## 狙い（なぜ *より理想* になるか）
基盤の正本資産（実験雛形＝新案件がコピーする「残す領域」）が、`work/EP-06-.../E-0001-.../`＝複製時に**消す領域**に
住んでいる矛盾を解消する。`tests/test_e2e_experiment.py:21-23` と experiment スキルが正本雛形を work/ に直書き＝
「複製で必ず壊れる結線」（template-copy.md 自身が「壊れやすい点 1」と自白）。正本を `templates/experiment/`（ci・
schedule・serve が既に住む「残す資産」の置き場）へ移すと、この壊れやすさが**構造的に消滅**する（縮小でなく根絶）。
あわせて template-copy.md のドリフト（「EP-01〜08 を消す」列挙のまま・EP-09〜25 が抜け）を doclint 走査対象に載せ、
複製手順の腐りを機械検知する。

## 現状の事実（着手時に grep 確認済み）
- `templates/` は `ci`・`schedule`・`serve` が住む「残す資産」置き場（DEC 済み境界）。
- `work/EP-06-.../E-0001-interaction-feature/` の中身：`code/train.py`・`config.yaml`・`config-regression.yaml`・
  `config-multiclass.yaml`（正本雛形＝コピー元）／`item.md`・`SPEC.md`・`results/`・`data/`（done 実験の再現記録）。
- `tests/test_e2e_experiment.py:21-23` が `work/EP-06-.../E-0001-.../code/train.py` を直叩き。
- `.claude/skills/experiment/SKILL.md:10` が fallback コピー元に同 work/ パスを指定。
- `docs/template-copy.md`：21 行「EP-01〜08 を消す」列挙・30-31 行「e2e パス直書き＝壊れやすい点 1」。
- `src/harness/doclint.py:32` `_FIXED_FILES = ("AGENTS.md","CLAUDE.md","docs/method.md","docs/learnings.md")`＝
  template-copy.md は未走査（パス参照の腐りを検知できない）。

## 設計（fable 詳細設計・確定）＝move/keep の切り分け
- **移す（正本雛形＝残す資産）**：`code/train.py`＋`config*.yaml`（3 本）→ `templates/experiment/`。移設後の配置は
  `templates/experiment/train.py`・`templates/experiment/config*.yaml`（`code/` の階層は畳む＝templates 直下の他資産と同じ平ら）。
- **残す（done 実験の再現記録＝消す領域だが歴史）**：`work/EP-06-.../E-0001-.../` の `item.md`・`SPEC.md`・`results/`・
  `data/` はそのまま。**重複コピーは作らない**（train.py/config を work 側に残すと「どちらが正本か」のドリフトが再発＝
  移設の目的に反する）。`E-0001/item.md` に 1 行追記：「code＋config の正本は `templates/experiment/`（T-0140 で移設）。
  本フォルダは再現記録（results/・data/）を保持」。**done 実験の pm 検査（results/ に指標・設定・データ指紋が同居）は
  results/ が残るので通り続ける**（コードの所在は検査対象でない）。
- **e2e の追従**：`tests/test_e2e_experiment.py` の `_EXPERIMENT`/`_TRAIN` を `templates/experiment/` へ向ける。configs も
  同様。出力（results/data）はテストの `tmp_path` に書く既存挙動を維持（train.py は `--test` で合成データを生成＝
  work/ の `data/*.yaml`〔過去 run の成果物〕に実行時依存しないことを確認する）。
- **experiment スキルの追従**：`.claude/skills/experiment/SKILL.md:10` の fallback コピー元を
  `templates/experiment/` へ。「直近の実験フォルダ（無ければ `templates/experiment/`）を丸ごとコピー」の意味を保つ。
- **template-copy.md の脱ドリフト（最小修正・全面 How-to 化は EP-24 の領分＝しない）**：(a) 「消す」一覧の
  「`work/EP-01-foundation` 〜 `work/EP-08-agent-first-entry`」を**脱列挙化**（「`work/` 配下の前案件エピック
  （`EP-*`・`T-*`・`E-*`）を消す」＝範囲を数えない＝将来のエピック追加で再ドリフトしない）。(b) 「残す」一覧に
  `templates/experiment/`（正本雛形）を追加。(c) 「壊れやすい点 1（e2e パス直書き）」の節を、正本が残す領域へ移った旨に
  更新（or 削除）＝複製時にこのパスを手で直す必要が無くなったことを明記。
- **doclint 拡張**：`doclint._FIXED_FILES` に `docs/template-copy.md` を追加＝複製手順のパス参照（`templates/experiment/`・
  `tests/...`・`work/...`）が今後腐ったら verify が RED。新テスト `test_template_copy_paths_resolve`（template-copy.md の
  パス参照がすべて実在）を doclint テストに追加。

## 受け入れ基準（detailed）
- `templates/experiment/train.py`＋`config*.yaml` が存在し、`work/EP-06-.../E-0001-.../code/` と work 側 config が消えている
  （重複なし）。`E-0001/item.md` に移設の注記。`results/`・`data/`・`SPEC.md` は残存。
- `tests/test_e2e_experiment.py` が `templates/experiment/` を叩いて緑（e2e スモーク）。experiment スキル fallback が追従。
- `docs/template-copy.md` が脱列挙化＋`templates/experiment/` を「残す」に追加＋壊れやすい点更新。`doclint._FIXED_FILES` に
  template-copy.md 追加＋`test_template_copy_paths_resolve` が実在。
- `uv run verify` 全成功（done 実験 E-0001 の pm 検査も通る）。

## 効かせる guard（maker≠checker・このミューテーションで RED）
1. `templates/experiment/train.py` を壊す → `test_e0001_smoke`（e2e）が RED（実行できる正本資産を移設先でも腐らせない）。
2. template-copy.md に実在しないパス（旧 `work/EP-06-.../code/train.py`）を残す → `test_template_copy_paths_resolve`／
   doclint 死にリンクが RED（複製手順のドリフトを機械検知）。
3. E-0001 の `results/` を空にする → 既存の done 実験検査（pm）が RED（再現記録の同居を維持）。

## 触ってはいけない核
train.py の中身（実験の意味論）・`--test` スモーク契約・results の指紋検査・done 実験の pm 検査・`ExperimentSpec`
（extra=forbid）・experiment スキルの config 手順の本体。

## verified_by
- `tests/test_e2e_experiment.py::test_e0001_smoke`（パス変更・アサーション不変＝移設先で実行できる）
- `tests/test_doclint.py::test_real_repo_docs_have_no_dead_links`（template-copy.md の死にリンク検知）
- `tests/test_doclint.py::test_template_copy_paths_resolve`（新規＝複製手順のパス実在）
（実テスト名は着手時に grep で確認。e2e の実名が `test_e0001_smoke` でなければ実在名に合わせる。）

## やらないこと
train.py/config の work 側への重複コピー残し（ドリフト再発）／results・data・SPEC の移動（再現記録は work に残す）／
template-copy.md の全面 How-to 化（EP-24 T-0132 の領分）／新 CLI・スキル／実験の意味論変更／verify に network。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE＋残課題）
設計＝fable・実装＝sonnet（ID 衝突を発見し T-0136→T-0140 へ改番＝EP-24 に既存 T-0136 があった good catch）・
レビュー＝Opus（別モデル）。別ターミナルが EP-24 の docs 機械化（doc_standards/glossary/DEC-0019）を撤去した rollback
（origin/main=9f0f3bc）の上に統合して実測。
- **統合の健全性**：作業ツリーは rollback を正しく反映（doc_standards.py 無し・checks.py に doc_standards 参照ゼロ）。
  T-0140 の template-copy.md 編集は rollback 版の上に**純加算**（rollback を巻き戻していない）。doclint（≠撤去された
  doc_standards）は健在で T-0140 が拡張。`uv run verify` 全緑。✓
- **G-e2e**（`templates/experiment/train.py` を壊す）→ `test_e0001_smoke` ほか e2e スモークが RED。移設先でも「実行
  できる正本資産を腐らせない」既存思想が生きている。✓
- **G-drift**（template-copy.md に旧パス `work/EP-06-.../code/train.py` を残す）→ `test_template_copy_paths_resolve`
  ＋`test_real_repo_docs_have_no_dead_links` の**両方**が RED。doclint が template-copy.md を覆うようになり、複製手順の
  ドリフトを機械検知する（`_FIXED_FILES` 追加が効いている）。✓
- **move/keep の faithfulness**：`git mv` で code/train.py＋config*.yaml を `templates/experiment/`（残す領域）へ・
  work 側に重複を残さず（ドリフト再発なし）・results/data/SPEC/item.md は work に残置（done 実験 E-0001 の pm 検査は
  results/ が残るので通過）。experiment スキル fallback・e2e パスも追従。✓
- **残課題（self-containment の部分達成・要フォロー）**：sonnet が正直に報告したとおり、fable 設計の前提
  「`--test` は合成データで work/data に非依存」は**誤り**だった——`prepare_root`→`load_schemas` が `work/**/data/*.yaml`
  から e0001 のテーブル定義を読む。sonnet は「data/ は移動しない（再現記録）」制約下で `_E0001_SCHEMA_DIR` を work/ の
  E-0001 data へ後方参照する最小回避を採った（verify 緑）。結果、**雛形 train.py が「残す領域」から「消す領域」
  （work/EP-06/E-0001/data）を内部参照**する＝T-0140 の「複製で壊れない自己完結」は**テストの入口パスは安定化したが
  内部スキーマ依存は未解消**の部分達成。template-copy.md の「壊れやすい点1 解消」は厳密には過剰主張気味
  （複製先が work/EP-06 を消すと `--test` の schema コピーが空振りしうる。ただし複製先は experiment スキルどおり
  自分の WORK_ID・テーブル定義に差し替える前提）。**フォロー候補（別タスク）**：雛形が必要とする「テーブル定義
  （schema）だけ」を `templates/experiment/` 側へ持たせて完全自己完結にする（run 出力＝folds/oof は work に残す）、
  または雛形スモークを完全 synthetic 化して schema 非依存にする。実験機構全体（`load_schemas` が work/**/data を
  glob する設計）に触れるため T-0140 の範囲外＝残課題として記録。
- `uv run verify` 全成功。**APPROVE**（上記残課題を別タスクでフォローする前提）。
