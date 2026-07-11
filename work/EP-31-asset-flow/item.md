---
id: EP-31
kind: epic
status: done
plan: detailed
requirements: [REQ-001]
depends_on: []
created: 2026-07-10
---
# EP-31 資産を配れるようにする（複製と還流の経路）

## なぜ最優先か（目的の確定 2026-07-10）
この基盤の最上位の目的は **「案件を重ねるほど強くなること」**。成果物の正しさも、人の時間を使わないことも、
これに従属する手段である。

これまで正本（README・AGENTS）は目的を**手段の言葉**で書いていた（verify・gates・作る側と確かめる側の分離）。
手段から手段を導く循環になっていて、5 本の独立した設計レビューのうち誰も「資産が案件へどう渡り、どう戻るか」を
見なかった。見たら、前提が壊れていた。

## 実測で分かったこと（複製は成立していない）
1. **手順どおりに複製すると、緑になる状態が存在しない**（デッドロック）。
   `docs/template-copy.md` に従って `work/` と `issues/` を消すと doclint の死にリンク検査が 7 件で落ちる。
   **恒久資産が可変領域を参照している**：`docs/core.md`→ISS-0015、`src/harness/doclint.py`→ISS-0001/0003、
   `code_doc_lint.py`→ISS-0015、`coverage_lint.py`→ISS-0014、`ds/experiment.py`→ISS-0007、`tests/conftest.py`→ISS-0002。
   参照される 6 枚を残すと、今度は pm 検査が「`ISS-0002` の `promoted_to` が指す `T-0069` が無い」で 4 件落ちる。
   逃げ場が無い。緑にする唯一の道は「触らない」はずの `src/harness/` から ISS 参照を剥がすこと。
2. **テストがこのリポジトリの実状態を仮定している**。`tests/test_profiles.py` と `tests/test_ops_profile.py` は
   「この config の profiles は `[ds, serve, agent, ops]`」とテンプレート自身の設定値をハードコードしている。
   `profiles = []` にすると失敗する。
3. **非 DS 案件は素の `uv sync` で verify が起動すらしない**（pytest 収集で 45 errors。tests が optional 依存を
   トップレベルで import する）。使わない lightgbm・statsmodels・fastapi を永久に飼う羽目になる。
4. **複製後の更新経路が無い**。`docs/template-copy.md` は本体→案件の一方向で、機械化もゼロ（手作業 4 歩の文書）。
   複製先は複製時点の基盤で凍結される。
5. **還流（案件→本体）の経路が無い**。実在するのは harvest スキルの 1 文「2 つ以上の案件で役立ったものだけを
   開発基盤へ取り込む」だけ。どうやって・誰が判断・何を単位に、はどこにも無い。しかも複製手順は
   `docs/learnings.md` を空にすると指示していて、**観察の材料を複製時に捨てている**。
   さらに「2 つ以上の案件で」（回数基準）は AGENTS の「回数で待たない・一般性で判断」と矛盾する。

**配れないなら、蓄積は成立しない。** だからこのエピックが最優先。

## 設計：fork にすると機構が要らなくなる
案件 ＝ テンプレートの **git clone（fork）**。実体コピーは採らない。

- **downstream が git の標準操作になる**：`git fetch upstream && git merge upstream/main`。
- **派生元の版記録ファイルを作らない**：`git merge-base upstream/main HEAD` が発生源で真実を持つ。
  版記録は写し＝台帳であり、必ず古びる（却下）。
- **還流も差分単位**：本体領域だけに触る 1 コミットを cherry-pick / PR で戻す。

これを機械的にする前提が、**本体領域と案件領域をファイルレベルで排他にする**こと。

- **本体領域**（upstream が所有）：`src/harness/`・`tests/`・`.claude/skills/`・`templates/`・
  `docs/{method,DoD,core,ds,serve,agent,ops,*-code}.md`・`AGENTS.md`・`CLAUDE.md`・`checks.toml`・
  `.pre-commit-config.yaml`・`.github/`
- **案件領域**（案件が所有。merge で競合しない）：`work/`・`issues/`・`docs/charter.md`・
  `docs/requirements/`・`docs/learnings.md`・`docs/data/*.yaml`・`.harness/config.toml`・`data/`
- **競合する 2 つだけを正直に規定**：`pyproject.toml`・`uv.lock`（案件が依存を足すので、merge 時に人が見る）

## 機構を増やさずに済ませた（L-017 の適用記録）
却下したもの：版記録ファイル（git が発生源）／複製先で前案件 ID の残骸を grep する lint（検出器。
参照方向の禁止で封鎖する）／還流候補の追跡台帳・「何案件で役立ったか」のカウント（検出器かつ計測機構）／
案件とテンプレートの差分監視（境界が排他なら merge が機械的で、差分という概念が消える）。

条件付きで採用したのは**複製シミュレーションの CI 1 本だけ**で、これは検出器だと正直に申告する。
「`profiles = []` の複製で verify が緑」は構成から導ける受け入れ基準であり、テストが実状態を仮定する型の結合は
参照の grep では原理的に見えないので、境界の実行可能な定義がこれしか無い。**増やさない。**

## タスク
| ID | 何を | なぜ |
| --- | --- | --- |
| T-0189 | 目的を正本（AGENTS・README）に書く | 手段の言葉で目的を書いていた。全部の判断がここから逆算される |
| T-0190 | 恒久資産から可変領域（ISS・work）への参照を断つ | 複製デッドロックの根。既存の doc_source_lint の適用範囲の穴埋め |
| T-0191 | テストがこのリポジトリの実状態を仮定しないようにする | `profiles = []` で落ちる 2 テスト |
| T-0192 | テストをプロファイルの持ち物にする | 非 DS 案件が使わない依存を飼わずに済む。`--all-extras` 条文を profile 従属に |
| T-0193 | 複製を fork と規定し、本体領域と案件領域を排他に定義する | merge を機械化する前提。`template-copy.md` の書き直し |
| T-0194 | `uv run init-project`（複製後の初期化を 1 コマンドに） | 手作業 4 歩は「読み忘れ・やり忘れ」という発生源を持つ |
| T-0195 | 複製シミュレーションの CI 1 本 | 上の 4 つが本当に効いていることの実行可能な定義（検出器と明記） |
| T-0196 | 還流の手順を決める（単位・判断者・基準） | harvest の 1 文を具体化。回数基準を廃し、判定はテンプレート側の独立レビュー |
| T-0181 | `doc_source_lint` の対象を templates/・src/・tests/ へ拡張 | T-0190 の機械化（既存タスク・ここへ移管） |
| T-0183 | 非 DS 案件で ds を外せるようにする | T-0192 と同じ根（既存タスク・ここへ移管） |
