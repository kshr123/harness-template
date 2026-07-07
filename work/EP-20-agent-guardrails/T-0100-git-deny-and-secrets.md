---
id: T-0100
kind: task
status: done
title: 破壊的 git deny と秘密情報検出（settings＋pre-commit＋CI を同じ入口で・ガードレールの骨組み）
created: 2026-07-07
depends_on: [T-0088]
verified_by: [tests/test_guardrails.py::test_destructive_git_denied, tests/test_guardrails.py::test_secrets_scan_wired]
---
# T-0100 破壊的 git deny と秘密情報検出

## 狙い（端まで通る最小＝エピックの骨組み）
現状のガードは Read 拒否（`.env`/`secrets/`）のみで、**破壊的 git 操作と「コミットに鍵を書く」経路が無防備**。
このタスクで EP-20 の骨組みを 1 本通す：**ガードレール 1 件＝(a) 執行点（settings / pre-commit / CI）＋
(b) 配線の常在検査（pytest＝`uv run verify` に接続）** という型を確立する。以降のタスク（T-0101〜T-0103）は
この型（緑）を保ったまま執行点を増やしていく。新規 src 資産は作らない（設定＋テストのみ・item.md の見立て通り）。

## 受け入れ基準
- **`.claude/settings.json`**：`permissions.deny` に破壊的 git 操作の deny を追加する。対象（最低限）：
  `git push --force` / `git push -f`／`git reset --hard`／`git clean -f`／`git branch -D`。
  ルール記法は Claude Code の Bash ルール（接頭辞一致＝`Bash(git push --force:*)` 形式）を実装時に公式ドキュメントで
  確認して用いる（item.md の `git push --force*` は意図表記であり、そのままの文字列にしない）。
  既存の Read 拒否 3 件は変更しない。
- **`.pre-commit-config.yaml`**：秘密情報検出フックを追加する（第一候補＝gitleaks の公式 pre-commit フック。
  環境上の理由で回らない場合は detect-secrets。どちらを選んだかと理由をフックのコメントに 1 行残す）。
  既存の `harness-check-standard` フックは変更しない。
- **`.github/workflows/ci.yaml`**：**ローカルと同じ入口**で秘密情報スキャンを回すステップ（またはジョブ）を追加する
  （`uvx pre-commit run <hook-id> --all-files` 等＝「ローカルと CI が同じ入口」の既存思想を守る。CI だけ別ツールに
  しない）。verify ジョブの既存ステップは変更しない。
- **`tests/test_guardrails.py`（新規）**：配線の常在検査（下記「検査」）。ガードが黙って外れたら verify が
  落ちる＝fail closed。
- **導線（DEC-0016）**：新しい CLI コマンドは増やさない（coverage_lint の対象外）。ただしガードレールの所在
  （どこで何を止めるか）を `AGENTS.md` の「してはいけないこと」節近傍または `docs/` 直下の正本に 1〜2 行で明記する。
- `uv run verify` 全体緑。

## 触ってよいファイル
`.claude/settings.json`・`.pre-commit-config.yaml`・`.github/workflows/ci.yaml`・
`tests/test_guardrails.py`（新規）・`AGENTS.md`（1〜2 行）・`docs/learnings.md`（気づきがあれば追記）。
`src/` は触らない（このタスクは設定＋テストのみ）。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_guardrails.py::test_destructive_git_denied`（**unit**）：`.claude/settings.json` を JSON として読み、
  `permissions.deny` に破壊的 git 5 種（force push・reset --hard・clean -f・branch -D）を覆うルールが含まれることを
  検査する。期待値はこのタスクで定めるポリシー（受け入れ基準の一覧）から導出＝実装出力のコピーではない。
  既存の Read 拒否 3 件が残っていることも同時に検査（退行防止）。
- `test_guardrails.py::test_secrets_scan_wired`（**unit**）：`.pre-commit-config.yaml` を yaml として読み、
  秘密情報検出フックの id が存在すること、および `.github/workflows/ci.yaml` に同じ入口（同フック id への言及）が
  あることを検査する。
- 実際の検出力（仕込んだ偽の鍵を検出できるか）はツール実体が要るため pytest では回さず、pre-commit / CI の実行系で
  担保する。実装時に**手元で 1 回だけ偽の鍵を仕込んだ検出デモを行い、その出力を PR に証拠として貼る**（コミットは
  しない）。
- マーカーは `unit`（`--strict-markers` 前提・未登録マーカー禁止）。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
（レビュー後に記入。観点：deny ルールの記法が Claude Code の実仕様に合っているか＝実測で拒否されるか／
秘密情報フックがローカルと CI で本当に同じ入口か／偽陽性（テストフィクスチャ内のダミー値等）で開発が止まらないか／
テストがポリシー由来の期待値になっているか＝金メッキでないか）
