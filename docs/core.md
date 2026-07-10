# core — 中核（プロファイルに依らない共通部分）の正本

このリポジトリは「中核」と「プロファイル」の 2 層でできている。

- **中核**（`src/harness/*.py`）… どの案件でも同じもの。作業単位の管理・課題・ドキュメントの検査・
  検証コマンドの入口。プロファイルのコードを import しない。
- **プロファイル**（`src/harness/ds/`・`src/harness/serve/`・`src/harness/agent/`・`src/harness/ops/`）…
  案件によって載せ替えるもの。`.harness/config.toml` の `profiles` に書いたものだけが実行時に加わる。
  非 DS の案件は `profiles` を空にすれば DS の検査が丸ごと外れる（`src/harness/checks.py` の手編集は不要）。
  それぞれの正本は [ds.md](ds.md)・[serve.md](serve.md)・[agent.md](agent.md)・[ops.md](ops.md)。

この文書は中核の正本。とくに **`uv run verify` が実際に何を回すか**をここだけで定義する。

## 検証コマンド

| コマンド | 何をするか |
| --- | --- |
| `uv run verify` | 完了判定。`check --level full` と同じ。すべて成功して初めて done にできる |
| `uv run check --level fast` | 編集中の速い検査（`standard`・`full` も指定できる。段階は累積） |
| `uv run doc-sync` | 下の自動生成節を作り直す（検査を足した・docstring を直したあとに走らせる） |

実体は `src/harness/checks.py` の `run_check`。次の 2 つを順に走らせる。

1. **プロジェクト管理の検査**（`PM_CHECKS`）… 段階によらず毎回すべて走り、指摘を全件集めてから合否を出す。
2. **言語ツール**（`checks.toml`）… ruff・mypy・pytest を段階ごとに走らせる。

下の 2 つの表は、その 2 つの出所（`PM_CHECKS` の各関数の docstring 1 行目と、`checks.toml`）から
`uv run doc-sync` が生成する。**手で編集しない**。生成し忘れ・書き換えは `doc_sync.run_checks` が
verify で失敗として教える（`src/harness/doc_sync.py`）。

<!-- doc-sync:begin ここから uv run doc-sync が生成する。手で編集しない。 -->
### プロジェクト管理の検査（`PM_CHECKS`）

段階（fast/standard/full）によらず毎回走る。プロファイル（ds・serve・agent・ops）の検査は
`.harness/config.toml` の `profiles` から実行時に加わるので、この表には載らない（各プロファイルの
正本ドキュメントを見る）。

| 検査 | 何を見るか |
| --- | --- |
| `pm.lint` | 作業単位の検査。ID の重複・depends_on の指す先が無い・計画の詳しさの不整合を見る。 |
| `pm.spec_lint` | 作業単位に SPEC.md があれば、必要な見出しがそろっているか確認する。 |
| `issues.run_checks` | 課題の整合検査。作業単位との紐付けが崩れていないかを見る（backend によらず同じ）。 |
| `doclint.run_checks` | 正本ドキュメントの参照（ID・パス・`uv run` コマンド）の実在検査。死にリンク＝error、未知コマンド＝info。 |
| `coverage_lint.run_checks` | CLI コマンドの導線カバレッジ検査。スキル/正本 docs から到達できないコマンド＝error。 |
| `doc_source_lint.run_checks` | 恒久ドキュメントが `work/` の作業単位を設計の根拠に参照していないか検査する。参照＝error。 |
| `code_doc_lint.run_checks` | 各プロファイルの公開モジュールが、そのプロファイルの正本ドキュメントに載っているか検査する。欠落＝error。 |
| `conventions.run_checks` | テスト規約の静的検査。グローバル種・--test 欠落・ISS 無し命令形 skip・encoding 欠落＝error。 |
| `doc_sync.run_checks` | 中核の正本ドキュメントの自動生成節が最新か検査する。古い・マーカー異常＝error。 |

### 言語ツール（`checks.toml`）

段階は累積する（full は fast・standard のコマンドも走らせる）。

| 段階 | コマンド |
| --- | --- |
| `fast` | `ruff format --check .` |
| `fast` | `ruff check .` |
| `fast` | `pytest -q -m 'unit and not slow'` |
| `standard` | `mypy` |
| `standard` | `pytest -q -m 'integration and not slow'` |
| `full` | `pytest -q -m 'e2e and not slow'` |
<!-- doc-sync:end -->

## 検査を足すとき

1. `src/harness/<名前>.py` に `run_checks(root: Path) -> list[pm.Problem]` を書く。**docstring の 1 行目が
   上の表の要約になる**ので、何を見て何を error にするかを 1 文で書く。
2. `src/harness/checks.py` の `PM_CHECKS` に加える。
3. `uv run doc-sync` で上の表を作り直し、生成結果ごとコミットする。

`pm.Problem` の水準は `error`（合否に効く）と `info`（知らせるだけ）の 2 つ。環境の違いで揺れる指摘
（実行ファイルの有無など）は `info` にして、合否を環境に依存させない。

検査を足す前に、`docs/method.md` の「ルールを機械検査に落とす」手順を読むこと。**先に「違反すると失敗する
検査」を書き、既存の違反を直し、verify を全成功に戻す**（テスト先行と同じ順）。

## 生成物の扱い

このリポジトリには生成物が 2 種類ある。扱いが違うので混ぜない。

| 生成物 | コミットするか | 最新をどう保つか |
| --- | --- | --- |
| `STATUS.md`（`uv run status`） | しない | 見たいときに作り直す。古い生成物で検証を落とさない |
| この文書の自動生成節（`uv run doc-sync`） | **する** | verify が生成し直して突き合わせる。食い違えば失敗 |

違いは「他の正本から参照される読み物かどうか」。`docs/core.md` は AGENTS.md から参照され、GitHub 上でも
そのまま読まれるのでコミットが要る。コミットする以上、最新かどうかは機械が保証する。

この検査で止められないことが 1 つある。**上の表をマーカーの外に複製すれば、複製の側は古くなっても
検出されない**。恒久ドキュメント（README・AGENTS・DoD など）には検査やコマンドの項目を手書きで列挙せず、
「プロジェクト管理の検査＋ruff・mypy・pytest」のような分類だけを書いてこの文書へリンクすること。
