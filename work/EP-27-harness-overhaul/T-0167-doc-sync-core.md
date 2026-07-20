---
id: T-0167
kind: task
status: done
title: docs/core.md を新設し、verify の内訳をコードから生成する（doc_sync）
created: 2026-07-10
depends_on: [EP-27]
verified_by:
  - tests/test_doc_sync.py::test_real_repo_core_doc_is_fresh
  - tests/test_doc_sync.py::test_check_table_has_exactly_one_row_per_invariant_check
  - tests/test_doc_sync.py::test_check_table_uses_docstring_first_line_as_summary
  - tests/test_doc_sync.py::test_render_ignores_config_so_every_copy_generates_the_same_table
  - tests/test_doc_sync.py::test_stale_block_is_error
  - tests/test_doc_sync.py::test_missing_marker_is_error
  - tests/test_doc_sync.py::test_duplicate_marker_is_error
  - tests/test_doc_sync.py::test_absent_core_doc_is_not_a_problem
  - tests/test_doc_sync.py::test_check_without_docstring_raises
  - tests/test_doc_sync.py::test_sync_is_idempotent
  - tests/test_doc_sync.py::test_crlf_document_is_not_reported_as_stale
  - tests/test_doc_sync.py::test_doc_sync_is_registered_in_invariant_checks
---
# T-0167 中核の正本ドキュメント＋内訳の自動生成

## 背景（実測）
`uv run verify` が回す検査は `PM_CHECKS` の 8 件（pm.lint・pm.spec_lint・issues・doclint・coverage_lint・
doc_source_lint・code_doc_lint・conventions）と `checks.toml` の言語ツール（ruff/mypy/pytest を段階ごとに）。
ところが「verify が何を回すか」の内訳を手書きで列挙している箇所が 6 つあり、**全部が違い、全部が古い**：

| 場所 | 書かれている内訳 | 誤り |
| --- | --- | --- |
| `README.md` | 作業単位＋課題＋テーブル定義の検査＋ruff＋mypy＋pytest | 6/8 欠落。テーブル定義は DS プロファイル限定なのに中核と並記 |
| `AGENTS.md` | 作業単位の検査＋完了↔検証の結びつけ＋ruff＋mypy＋pytest | 7/8 欠落（前 2 つは pm.lint の言い換え重複） |
| `docs/DoD.md` | 同上 | 同上 |
| `docs/README.md` | テスト・型検査・決まりごとの検査 | 分類のみ（これは腐らないので可） |
| `.claude/skills/verify/SKILL.md` | 作業単位＋完了↔検証＋課題＋テーブル定義＋ruff＋mypy＋pytest | 6/8 欠落。テーブル定義の誤記も同じ |
| `src/harness/checks.py` の print | 参照チェック・完了↔検証・課題の整合＋プロファイルの検査 | coverage_lint・conventions が分類名から読み取れない |

中核（`src/harness/*.py`）には正本ドキュメントが無い。`code_doc_lint` も「core 直下は対象外」と明記しており、
中核モジュールの触れ忘れは検出されない（この穴は T-0168 で塞ぐ。本タスクはその置き場を作る）。

## やること
- `docs/core.md` を新設（中核の正本ドキュメント）。散文＋自動生成の節。
- `src/harness/doc_sync.py`：`PM_CHECKS` の各関数から名前（`<モジュール>.<関数>`）と docstring 1 行目を取り、
  `checks.toml` の段階→コマンドと併せて Markdown 表を生成する。`docs/core.md` のマーカーで囲んだ節だけを差し替える。
- `doc_sync.run_checks` を `PM_CHECKS` に追加。生成し直した内容と食い違えば error（生成物をコミットし、
  verify が鮮度を検査する＝`go generate` ＋ `git diff --exit-code` と同型）。doc_sync 自身も表に載る。
- `uv run doc-sync` を `[project.scripts]` に追加（導線は `docs/core.md` と `AGENTS.md` に書く）。
- `doclint._FIXED_FILES` に `docs/core.md` を追加（散文中のパス参照を検査対象に載せ、かつ AGENTS からの
  リンクによって `docs/core.md` の削除が死にリンクとして検出されるようにする）。
- 上記 6 か所の手書き列挙を、分類レベルの要約（「プロジェクト管理の検査＋ruff・mypy・pytest」）＋
  `docs/core.md` へのリンクに置き換える。`checks.py` の print は実測件数を出す（プロファイル由来の検査も
  数に入る唯一の場所）。
- `docs/README.md` の文書地図・`docs/template-copy.md` の「残す」一覧に `docs/core.md` を追加。

## 設計上の決定
- **生成は `.harness/config.toml` を読まない**。プロファイルの `pm_checks` は実行時に config から加わるので、
  生成表は中核の `PM_CHECKS` だけを対象にする。これで生成結果が全複製先で同一になる（非 DS の複製でも
  `docs/core.md` は変わらない）。config 依存の実数は実行時の print だけが持つ。
- **docstring 1 行目が空・無い検査関数は ValueError**（黙って空欄を生成しない）。`coverage_lint._validated_exempt`・
  `code_doc_lint._validated_exempt` と同じ作法。
- **`docs/core.md` 自体が無いときは指摘なし**。削除の検出は doclint（AGENTS.md からのリンク）に委ねる。
- 名前は一律 `<モジュール>.<関数>`（`pm.lint`・`doclint.run_checks`）。`run_checks` だけ短縮する特例は作らない。
- 比較は改行を正規化し、書き出しは LF 固定（Windows の CRLF で鮮度検査が偽陽性を出さない）。

## 実測（検査が噛むことの確認）
- 生成節の 1 セルを手で書き換える → `doc_sync.run_checks` が error（`uv run doc-sync` で作り直せと言う）。
- `docs/core.md` を消す → `doc_sync` は黙る（設計どおり）が、doclint が AGENTS.md・docs/template-copy.md・
  `.claude/skills/verify/SKILL.md` の 3 件を死にリンクとして error にする。両者が相互に留め合う。
- `uv run doc-sync` を 2 回続けて走らせても内容不変（冪等）。

## 独立レビューの指摘と対応（判定：可・重大な指摘なし）
- **`_normalize` は死にコードだった**。恒等関数に置き換えてもテスト 22 件が全部通った（レビュアのミューテーション
  実測）。`Path.read_text` は universal newlines で開くので、CRLF は読んだ時点で LF になっている。削除し、
  その事実を `_read` の docstring に書いた。CRLF のテストは性質としては正しいので残す。
- `sync` が `read_text` を 2 回呼んでいたのを 1 回に。
- **段階の累積**（「full は fast・standard も走らせる」）は `checks._load_commands` の振る舞いの言い換えで、
  表からは導出されない＝散文が嘘になりうる。振る舞いを固定するテストを足した。
- `checks.py` の実行時表示も `shlex.join` に（生成表だけ引用して画面表示が非引用なのは筋が通らない）。
- **用語**：「回帰の番人」は比喩。`tests/` の 18 箇所を「回帰テスト」に一括置換。`doc_sync.py` の
  「機械の持ち物」「同型」「鮮度」も標準語に直した。
- **検出できない腐り方**（レビュアの実測）：正しい表をマーカーの外に複製すると素通りする。設計の限界として
  `docs/core.md` と `doc_sync.py` の docstring に明記し、恒久ドキュメントに項目を手書き列挙しないことを
  レビュー観点として残した。

## 範囲を広げて直したもの
`docs/method.md` にも同じ種類の古い列挙が 2 か所（層の表の「`harness/`（pm.lint・spec_lint・checks.toml）」と、
気づきの落とし先の表の「機械検査（pm.lint / spec_lint / checks.toml / pytest）」）。どちらも 9 件中 3 件しか
挙げていない。本タスクが消そうとしている腐り方そのものなので、同じコミットで `docs/core.md` への参照に置き換えた。

## 副次的に見つけて直した誤り
- `doclint.run_checks` の docstring が「未知コマンド＝warn」と書いていたが、実際の水準は `info`
  （`pm.Problem` に warn は無い）。docstring 1 行目がそのまま `docs/core.md` に載るので訂正した。
- 生成表のコマンドは `shlex.join` で引用する。`' '.join` だと `pytest -q -m unit and not slow` となり、
  表からコピーして貼ると別の意味になる（正しくは `-m 'unit and not slow'`）。

## 受け入れ基準
- 生成節を書き換えると `doc_sync.run_checks` が error を返し、`uv run doc-sync` 後は指摘ゼロ。
- マーカーの欠落・重複＝error。`docs/core.md` 不在＝指摘なし。
- docstring 1 行目が空の検査関数を含む一覧＝ValueError（fail closed）。
- 生成は冪等（連続 2 回で内容不変）。CRLF の `docs/core.md` でも偽陽性を出さない。
- 生成表の行数が `len(PM_CHECKS)` と一致し、各検査の名前と docstring 1 行目が本文に現れる。
- `uv run verify` 全成功（coverage_lint が `doc-sync` を到達可能と判定し、doclint が `docs/core.md` を通す）。
