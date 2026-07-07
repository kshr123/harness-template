---
id: T-0134
kind: task
status: done
title: 検査委譲の関門 DEC-0021＋actionlint/check-jsonschema を pre-commit 配線（歩く骨組み）
requirements: [REQ-001]
depends_on: [T-0133]
verified_by:
  - tests/test_guardrails.py::test_workflow_lint_wired
  - tests/test_doclint.py::test_real_repo_docs_have_no_dead_links
---
# T-0134 検査委譲の関門＋既製バリデータの配線（歩く骨組み）

## 狙い（なぜ *より理想* になるか）
自前 lint 群の下層3〜5割は汎用形式の再実装（YAML 妥当性・cron フィールド数・workflow の on:/permissions 型・
「停止」の日本語 grep）。`schedule_lint.py` の `on:`→bool True 回避（pyyaml の YAML-1.1 罠）は actionlint が
10 年前に解決済みの問題を自前で踏み直した記録。**「新しい機械検査を書く前に、既製スキーマ/バリデータで
表明できるかを問う」関門**を DEC 化し、実際に actionlint（GitHub Actions 専用 lint・cron 構文検査を含む）と
check-jsonschema（schemastore の github-workflow スキーマ）を pre-commit に配線する＝DEC-0006/0008 の思想を
lint 群自身へ適用する進化。この骨組みでは自前 lint は**まだ削らない**（二重でも緑＝骨組み先行。純化は T-0135）。

## 設計（fable 詳細設計・確定）
- **DEC-0021（新規・accepted）**：`docs/decisions/DEC-0021-prefer-off-the-shelf-validators.md`。「機械検査の第一候補は
  既製バリデータ／自前 lint はスキーマで表明できないプロジェクト固有意味論に限定」。判定表：汎用形式（YAML 妥当・
  workflow 構造の型・cron 構文・schema 準拠）→既製へ委譲／固有意味論（scripts 実在・experiment→monitor→promote 順序・
  導線カバレッジ・参照実在・三者整合・停止手順の README 節との結線）→自前。関連 [[DEC-0006]][[DEC-0008]][[DEC-0016]]。
- **pre-commit 配線**：`.pre-commit-config.yaml` に 2 フックを remote repo で追加（gitleaks と同じ流儀＝network at
  hook time は既に許容・verify は no-network なので実行しない）。
  - **actionlint**（`rhysd/actionlint`）：GitHub Actions workflow の構文・式・cron を検査。
  - **check-jsonschema**（`python-jsonschema/check-jsonschema`・`--builtin-schema vendor.github-workflows`）：
    workflow の schema 準拠を検査。
- **`files:` 上書きが必須（vacuous pass を潰す）**：両フックの公式既定 `files` は `^\.github/workflows/` だが、
  本リポの workflow 雛形は `templates/ci/.github/workflows/*.yml` と `templates/schedule/monitor.yml`。`files:` を
  この 2 か所を覆う正規表現に上書きする（上書きしないと「緑だが何も走査していない」＝L-015 の教訓そのもの）。
  **k8s（`templates/serve/k8s/*.yaml`）・compose（`docker-compose.serve.yml`）は workflow ではないので `files:` の
  対象に含めない**（github-workflow スキーマを非 workflow に当てない）。
- **L-015 の作法で実測**：配線後に「壊れた workflow で本当に落ちる・クリーンで本当に通る」を両方実測してから確定する
  （network が使えず hook を実走できない環境なら、その旨を報告し wiring テスト＋手動実測手順の記録で代替＝gitleaks も
  DL を伴う remote フックである先例に合流）。
- **wiring テスト（`test_guardrails.py::test_workflow_lint_wired`・既存ファイルへ追記）**：`.pre-commit-config.yaml`
  を parse し、(a) actionlint・check-jsonschema の 2 フックが存在、(b) それぞれの `files` パターンが
  `templates/ci/.github/workflows/` と `templates/schedule/monitor.yml` の両方に**マッチする**（実際のパス文字列を
  `re.search` で当てて確認＝設定が黙って templates/ を外したら RED）、(c) check-jsonschema が github-workflows の
  builtin schema を使う、を検査。`test_secrets_scan_wired`（gitleaks）と同型・fail closed。
- **CI 追従**：CI（`.github/workflows/ci.yaml`）が pre-commit を回すなら 2 フックも同じ入口に含まれることを確認
  （gitleaks の CI 配線と同型。CI で pre-commit を明示フック指定している場合のみ追記）。

## 受け入れ基準（detailed）
- `docs/decisions/DEC-0021-*.md` が存在（判定表＋関連リンク）。
- `.pre-commit-config.yaml` に actionlint・check-jsonschema が追加され、`files:` が templates/ の workflow 2 か所を覆う。
- `test_guardrails.py::test_workflow_lint_wired` が存在し、`files:` が templates/ を外すと RED。
- 自前 lint（schedule_lint/ci_lint）は**無変更**（骨組みでは二重・純化は T-0135）。
- `uv run verify` 全成功（フック実行は verify の対象外＝no-network を保つ）。

## 効かせる guard（maker≠checker・このミューテーションで RED）
1. actionlint フックの `files:` を既定（`^\.github/workflows/`）に戻す／フックを削除 → `test_workflow_lint_wired` が
   RED（templates/ を覆わない vacuous 配線を検知）。
2. check-jsonschema の builtin schema 指定を外す → `test_workflow_lint_wired` が RED。
3. DEC-0021 を消す／指すパスを壊す → doclint の参照整合が RED。

## 触ってはいけない核
verify の fail-closed 構造・`checks.py` の PM_CHECKS 配線・gitleaks フック（`test_secrets_scan_wired`）・
自前 lint の中身（純化は T-0135）。

## verified_by
- `tests/test_guardrails.py::test_workflow_lint_wired`（新規＝配線が templates/ を覆う・fail closed）
- `tests/test_doclint.py::test_real_repo_docs_have_no_dead_links`（DEC-0021 のパス参照整合）

## やらないこと
自前 lint（schedule_lint/ci_lint）の汎用層剥離（T-0135 の領分・骨組みでは二重で緑）／verify に network を持ち込む
（フックは pre-commit 実行時のみ）／k8s・compose へ github-workflow スキーマを当てる／新 CLI・スキル（既存 pre-commit
基盤を使うだけ）。

## T-0135 への申し送り（重要・被覆の連続性）
本タスクでは actionlint/check-jsonschema を **pre-commit ローカルフックのみ**に配線し、CI（`.github/workflows/ci.yaml`）
には追加していない（設計の「CI 追従」は条件付き・骨組みでは自前 lint が二重で残るので CI 被覆は維持）。
**T-0135 で自前 lint（schedule_lint/ci_lint）の汎用層を削る前に、必ず CI で actionlint・check-jsonschema を回す配線を
入れること**（gitleaks が CI で `uvx pre-commit run gitleaks --all-files` を回すのと同型）。さもないと汎用層の被覆が
「verify/CI で走らないローカルフック」に痩せる＝「緑を保ったまま差し替え」（method.md A 節）に反する。

## 独立レビュー（Opus・ミューテーション／作る側と確かめる側を分ける・APPROVE）
設計＝fable・実装＝sonnet・レビュー＝Opus（別モデル）。別ターミナルの EP-24（doc_standards＝造語 denylist・lede 検査）
が着地した後の統合ツリー（origin/main=01efac7＋本タスク）で実測。
- **統合の健全性**：作業ツリーが EP-24 マージ済み（doc_standards.py・docs/README.md・glossary.md 実在）＋本タスクを
  正しく反映し、`uv run verify` 全緑。新規 DEC-0021・T-0134 md は EP-24 の新 doc_standards 検査（造語 denylist・lede）も
  通過＝衝突なし。✓
- **G-files**（actionlint の `files:` 上書きを公式既定 `^\.github/workflows/` に戻す＝templates/ を1件も走査しない
  vacuous 配線）→ `test_workflow_lint_wired` が RED。L-015 の「緑だが何も走査しない」再発を機械で止める。✓
- **G-schema**（check-jsonschema の `--builtin-schema vendor.github-workflows` を外す）→ 同テスト RED。✓
- **guard の非空振り確認**：wiring テストが照合する `WORKFLOW_LINT_TARGET_PATHS` は実在する雛形
  （`templates/ci/.github/workflows/verify.yml`・`templates/schedule/monitor.yml`）＝架空パスに対する空検査でない。✓
- **実装者の実測（network 有・参考）**：クリーン雛形で actionlint/check-jsonschema とも Passed、cron を `99 6 * * 1`
  に壊すと actionlint が「invalid CRON」で Failed、`branches:` を整数に壊すと check-jsonschema が schema 違反で Failed
  を確認済み（L-015 の作法）。Opus 側は network 非依存の wiring guard を独立実測。
- **自前 lint 無変更の確認**：`git diff` は `.pre-commit-config.yaml`＋`test_guardrails.py`＋新規 DEC/md のみ。
  schedule_lint/ci_lint は無変更（純化は T-0135）。gitleaks フック・PM_CHECKS・verify の fail-closed 不変。✓
- `uv run verify` 全成功。**APPROVE**（T-0135 への CI 配線申し送りを前提に）。
