# core — 中核（プロファイルに依らない共通部分）の正本

このリポジトリは「中核」と「プロファイル」の 2 層でできている。

- **中核**（`src/harness/*.py`）… どの案件でも同じもの。作業単位の管理・課題・ドキュメントの検査・
  検証コマンドの入口。プロファイルのコードを import しない。
- **プロファイル**（`src/harness/ds/`・`src/harness/serve/`・`src/harness/agent/`・`src/harness/ops/`・`src/harness/stats/`）…
  案件によって載せ替えるもの。`.harness/config.toml` の `profiles` に書いたものだけが実行時に加わる。
  非 DS の案件は `profiles` を空にすれば DS の検査が丸ごと外れる（`src/harness/checks.py` の手編集は不要）。
  それぞれの正本は [ds.md](ds.md)・[serve.md](serve.md)・[agent.md](agent.md)・[ops.md](ops.md)・[stats.md](stats.md)。

この文書は中核の正本。とくに **`uv run verify` が実際に何を回すか**をここだけで定義する。

## 検証コマンド

| コマンド | 何をするか |
| --- | --- |
| `uv run verify` | 完了判定。`check --level full` と同じ。すべて成功して初めて done にできる |
| `uv run check --level fast` | 編集中の速い検査（`standard`・`full` も指定できる。段階は累積） |
| `uv run check --scope diff` | git 差分に応じて回すものを絞る**参考実行**（散文だけ→不変条件のみ・領域変更→その領域だけ）。**done の判定にはしない**（完了は `uv run verify` の全成功だけ） |
| `uv run doc-sync` | 下の自動生成節を作り直す（検査を足した・docstring を直したあとに走らせる） |
| `uv run gates` | 昇格の判定の一覧（config の `kind` に書ける名前と意味）。実体は `src/harness/gates.py` |

実体は `src/harness/checks.py` の `run_check`。次の 2 つを順に走らせる。

1. **不変条件の検査**（`INVARIANT_CHECKS`。不変条件＝invariant＝このリポジトリで常に成り立つべき性質。
   参照が実在する・完了は検証に結びつく・中核はプロファイルを import しない、等）… 段階によらず毎回すべて走り、
   指摘を全件集めてから合否を出す。言語ツールが知らない、この基盤固有の規則を機械で確かめる。
2. **言語ツール**（`checks.toml`）… ruff・mypy・pytest を段階ごとに走らせる（言語として普遍的な正しさ）。

下の 2 つの表は、その 2 つの出所（`INVARIANT_CHECKS` の各関数の docstring 1 行目と、`checks.toml`）から
`uv run doc-sync` が生成する。**手で編集しない**。生成し忘れ・書き換えは `doc_sync.run_checks` が
verify で失敗として教える（`src/harness/doc_sync.py`）。

<!-- doc-sync:begin ここから uv run doc-sync が生成する。手で編集しない。 -->
### 不変条件の検査（`INVARIANT_CHECKS`）

段階（fast/standard/full）によらず毎回走る。プロファイルの検査は
`.harness/config.toml` の `profiles` から実行時に加わるので、この表には載らない（各プロファイルの
正本ドキュメントを見る）。

| 検査 | 何を見るか |
| --- | --- |
| `pm.lint` | 作業単位の検査。ID の重複・depends_on の指す先が無い・計画の詳しさの不整合を見る。 |
| `issues.run_checks` | 課題の整合検査。作業単位との紐付けが崩れていないかを見る（backend によらず同じ）。 |
| `doclint.run_checks` | 正本ドキュメントの参照（ID・パス・`uv run` コマンド）の実在検査。死にリンク＝error、未知コマンド＝info。 |
| `coverage_lint.run_checks` | CLI コマンドの導線カバレッジ検査。スキル/正本 docs から到達できないコマンド＝error。 |
| `doc_source_lint.run_checks` | 複製後も残る資産が `work/` の作業単位・`issues/` の課題を設計の根拠に参照していないか検査する。参照＝error。 |
| `code_doc_lint.run_checks` | 公開モジュールと正本ドキュメントの役割一覧が食い違っていないか双方向で検査する（順：触れ忘れ／逆：残骸）。 |
| `profile_doc_lint.run_checks` | 各プロファイルに正本 docs/<名>.md があり、doc 索引 docs/README.md から辿れるか検査する。欠落＝error。 |
| `boundary_lint.run_checks` | 中核（src/harness/*.py）がプロファイル（ds・serve・agent…）を import していないか検査する。 |
| `conventions.run_checks` | テスト規約・ソース規約の静的検査（種・--test・skip 理由・encoding・相対パスの as_posix 忘れ＝error）。 |
| `doc_sync.run_checks` | 中核の正本ドキュメントの自動生成節が最新か検査する。古い・マーカー異常＝error。 |

### 言語ツール（`checks.toml`）

段階は累積する（full は fast・standard のコマンドも走らせる）。

| 段階 | コマンド |
| --- | --- |
| `fast` | `ruff format --check .` |
| `fast` | `ruff check .` |
| `fast` | `pytest -q -m 'unit and not slow'` |
| `standard` | `mypy` |
| `standard` | `pytest -q -m 'integration and not slow and not browser'` |
| `full` | `pytest -q -m 'e2e and not slow'` |
<!-- doc-sync:end -->

## モジュール一覧

`src/harness/` の直下にあるものが中核。ここに公開モジュールを足したら、この表に 1 行足すこと
（触れ忘れは `code_doc_lint` が verify で失敗させる）。逆に、モジュールを消したのに下の表の行が残ったら、
`code_doc_lint` の逆向きが verify で失敗させる（役割一覧の行の先頭が名指す `<名>.py` の実在を照合する）＝
消したときは説明の行も消すこと。

**中核のしくみ**

| モジュール | 役割 |
| --- | --- |
| `pm.py` | `work/` の木を読んで進捗を出し、ID の重複・依存の指す先・完了と検証の結びつけ（`verified_by` の `::テスト名` を必須化し ast で実在照合）・`work/` の不可視領域と正体不明の `.md` を検査する |
| `models.py` | 作業単位（エピック・タスク・実験）の frontmatter を表す型定義。`pm.py`・`issues.py` が使う |
| `issues.py` | 課題（不具合・リスク・疑問）の登録簿の読み込みと、作業単位との整合の検査 |
| `config.py` | `.harness/config.toml` を読む（有効なプロファイル・データや課題の置き場） |
| `profiles.py` | config が指すプロファイルの `PROFILE` 宣言を読み込み、検査に繋ぐ |
| `checks.py` | 検証の入口。`INVARIANT_CHECKS` と `checks.toml` の言語ツールを束ねて走らせ、合否を返す |
| `scope.py` | `check --scope diff` の振り分け。git 差分から回すもの（不変条件は毎回全部・言語ツールとテストは変更範囲だけ）を決める参考実行。分類できない・検査インフラ・中核の変更は全実行に落とす（fail-closed） |
| `cli.py` | 中核 CLI（typer）の入口。`uv run <コマンド>` はここから呼ばれる |
| `init_project.py` | 複製後の初期化（`uv run init-project`）。fork した案件の案件領域を白紙化し verify 緑の出発点に戻す（本体領域には触れない・未 fork では拒否） |
| `gates.py` | 昇格の判定（`value_threshold`・`change_threshold`）。champion を差し替えてよいかを決める |

**検査**（上の自動生成の表の各行に対応する）

| モジュール | 何を見るか |
| --- | --- |
| `doclint.py` | 正本ドキュメントの参照（ID・相対パス・`uv run` コマンド）が実在するか |
| `doc_source_lint.py` | 複製後も残る資産（docs・src・tests・templates・skills）が一時的な単位（`work/`・`issues/`）を設計の根拠に参照していないか |
| `code_doc_lint.py` | 公開モジュールと正本ドキュメントの役割一覧が食い違っていないか（順：新しいモジュールの触れ忘れ／逆：消したモジュールの説明の行が残っていないか） |
| `profile_doc_lint.py` | 各プロファイルの正本 `docs/<名>.md` があり、doc 索引 `docs/README.md` から辿れるか（プロファイル追加時の索引の陳腐化を止める） |
| `coverage_lint.py` | CLI コマンドの使い方が、スキルか正本ドキュメントから辿れるか |
| `boundary_lint.py` | 中核（`src/harness/*.py`）がプロファイル（ds・serve・agent・ops）を import していないか（ast・遅延 import も検出。`INVARIANT_CHECKS` に登録され verify に載る） |
| `doc_sync.py` | この文書の自動生成節が `INVARIANT_CHECKS`・`checks.toml` の現状と一致しているか |
| `conventions.py` | テスト規約・ソース規約（乱数の種・`--test` の有無・skip の理由・`subprocess` の `encoding`・リポ相対パスの `.as_posix()`）を静的に検査する |
| `commit_lint.py` | コミットメッセージの冒頭に、`work/` に実在する作業単位の ID があるか |

**プロファイルが共有する部品**

中核ディレクトリに置いてあるが、上の「中核のしくみ」からは使われない。複数のプロファイルが再利用するので
中核に置いている（プロファイル間で同じものを二度書かないため）。

| モジュール | 役割 | 使っているプロファイル |
| --- | --- | --- |
| `registry.py` | config の種別文字列から部品を引く登録簿と、その一覧表示 | ds・agent |
| `storage.py` | 保存先 URI の解決・不可分な書き込み・sha256・manifest の読み書き | ds・agent |
| `promotion.py` | 昇格記録の置き場・読み書き・champion の解決・判定の実行（仕組みだけ。向きや閾値の方針は呼び手） | ds・agent |
| `provenance.py` | 保存物の由来書き（git commit/branch/dirty・依存版・uv.lock 指紋・時刻）を集める（保存の by-product） | ds・agent |
| `fingerprint.py` | 入力 1 件を正準な JSON にして sha256 の指紋にする | ds・serve・agent |
| `testing.py` | pytest のマーカー（unit/integration/e2e）と skip 理由の検査（`tests/conftest.py` が使う） | 全体（テスト） |

`src/harness/models.py`（中核の作業単位の型）と `src/harness/ds/models.py`（学習済みモデルの保存と読み込み）は
名前が同じだけの別物なので混同しないこと。

## 検査を足すとき

1. `src/harness/<名前>.py` に `run_checks(root: Path) -> list[pm.Problem]` を書く。**docstring の 1 行目が
   上の表の要約になる**ので、何を見て何を error にするかを 1 文で書く。
2. `src/harness/checks.py` の `INVARIANT_CHECKS` に加える。
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
「不変条件の検査＋ruff・mypy・pytest」のような分類だけを書いてこの文書へリンクすること。
