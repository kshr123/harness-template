---
id: T-0155
kind: task
status: done
title: プロファイルのコード役割ドキュメント（serve/agent-code）＋触れ忘れを止める code_doc_lint
created: 2026-07-08
depends_on: [T-0150]
verified_by: [tests/test_code_doc_lint.py::test_undocumented_module_is_error, tests/test_code_doc_lint.py::test_real_repo_profile_modules_are_documented]
---
# T-0155 コードの役割ドキュメントを serve/agent へ広げ、保守を機械化する

## 背景
オーナー要望：ドキュメントは「エージェントには分かるが人には分かりにくい」。とくに**どのコードがどんな役割か・
今後どう広がるか**が読めない。ds は先に `docs/ds-code.md`（設計の説明＝Explanation）へ分割済み（323f2fe）。
残る serve・agent・ops も同じ型にし、かつ**今後もドキュメントが保守される仕組み**（新モジュールを足したのに
docs で触れないと verify で止まる）を作る。

## やったこと（理想の最小構成）
- **`docs/serve-code.md`・`docs/agent-code.md`（新規 Explanation）**：`docs/<名>.md`（Reference＝地図）の姉妹。
  各ファイルが何を担い・どこに何がどう書かれ・拡張の継ぎ目はどこかを、コードを読む前に掴めるようにする。
  ds-code.md と同じ構成。**事実だけを書く**（「今後どうなりそうか」の推測節は 3 つの -code.md すべてから削除。
  最新維持は下の code_doc_lint に任せる）。冒頭に**大粒度のグループ・順番・ファイルの関係を示す図**（ASCII）を
  置き、ぱっと見で流れ（入力→組み立て→評価→保存→配信）が分かるようにした。
- **地図側からの導線**：`docs/serve.md`・`docs/agent.md` の実装参照行を `-code.md` へのリンクに更新。agent.md は
  部分的なモジュール手書き一覧（cassette 等が抜け・二重管理になる）を削り、より完全な `agent-code.md` へ 1 本化。
- **`docs/README.md` の文書地図**に serve-code.md・agent-code.md（Explanation）を追加（ds-code.md 行と対称）。
- **ops は据え置き**：モジュール 2 つ（ci_lint.py・profile.py）は `docs/ops.md` 本文が既に名指ししている＝
  別 `-code.md` は作らず地図 1 枚に同居（分割は中身の量が要るときだけ＝過剰分割を避ける）。
- **`src/harness/code_doc_lint.py`（新 core 検査＝保守の仕組み）**：`src/harness/*/`（profile.py を持つ
  ディレクトリ＝プロファイル）の公開モジュール（`__init__.py`・`profile.py`・`_` 始まりを除く *.py）が、その
  プロファイルの正本ドキュメント（`docs/<名>.md`＋`docs/<名>-code.md` を連結）で**ファイル名として一度は
  触れられている**ことを検査。欠落＝error（触れ忘れを verify で止める）。理由必須 allowlist（他 lint と同型）。
  stdlib のみ・無ネットワーク・軽量。`PM_CHECKS`（verify）へ配線。

## 「言及の有無」だけを見る理由（一般化しすぎない）
説明の質（分かりやすさ・過不足）は機械で測れない＝review 観点に残す。機械で安全に止められるのは「新モジュール
を足したのに正本 docs で一度も触れていない」＝発見可能性の穴だけ。ここに絞る（正直な線引き）。profile.py は
どのプロファイルにも 1 つある同型の結線なので対象外（説明を要さない）。

## 受け入れ基準
- `uv run verify` 全成功（code_doc_lint 込み・現リポの全プロファイルのモジュールは docs で言及済み）。
- 人が `docs/README.md` から serve-code.md・agent-code.md へ辿れ、各プロファイルの「どのコードが何を担うか」を
  コードを読まずに掴める。
- プロファイルに未記載モジュールを足すと verify が落ち、メッセージが直し方（docs に 1 行足す）を示すことを
  回帰テストで固定（maker≠checker：本タスクは Opus が実装＋独立レビューで確認）。

## 触ってよい範囲
`docs/serve-code.md`・`docs/agent-code.md`（新規）・`docs/serve.md`・`docs/agent.md`・`docs/README.md`・
`src/harness/code_doc_lint.py`（新規）・`src/harness/checks.py`（PM_CHECKS へ 1 行）・
`tests/test_code_doc_lint.py`（新規）・この item.md。他は変えない。
