# テンプレートの fork と、資産の渡り方・戻り方（正本）

この文書は、この開発基盤を次の案件で使うときの**複製の仕方**と、複製後の**両方向の資産の流れ**の正本
（唯一の正とする置き場）。案件を重ねるほど強くなるための最上位の条件（AGENTS.md 目的 4）を、機構を増やさず
git の標準操作で成り立たせる。

**案件 ＝ テンプレートの git clone（fork）。** 実体コピー（zip を展開して別リポにする等）は採らない。fork に
すると、本体→案件の取り込みも、案件→本体の還流も、専用の仕組みを持たずに `git fetch`／`git merge`／
`git cherry-pick`／PR だけで回る。

## 1. fork する（案件を始める）

```
git clone <template-url> <案件名>
cd <案件名>
git remote rename origin upstream        # 派生元（本体）を upstream にする
git remote add origin <案件リモート-url>  # 案件の置き場を origin にする
uv run init-project                       # 案件領域を白紙化する（下記 3 節）
```

- **派生元の版記録ファイルは作らない**。どの版から分かれたかは `git merge-base upstream/main HEAD` が発生源
  として持つ。版記録ファイルは写し＝台帳であり、必ず古びる（作らない）。
- `upstream` リモートの有無が「fork 済みか」の判定になる。`uv run init-project` はこれを見て、まだ fork して
  いない状態（テンプレート本体そのもの・`upstream` 未設定）では**拒否**する（本体を誤って初期化しない）。
- CI 雛形（`templates/ci/.github/workflows/verify.yml`）をコピーしたら、`verify` を **required status check** に
  し、PR レビュー必須（承認者 ≠ 作成者）を設定する。この 1 手順だけは作業ツリーの外＝唯一の不動点で、人が
  行う（手順・gh CLI 例は `docs/ops.md` の「verify を required check にする」）。

## 2. 本体領域と案件領域（ファイルレベルで排他）

merge を機械的にする前提が、**どのファイルを誰が所有するか**をファイルレベルで分けること。所有が重ならない
限り、`git merge upstream/main` は案件のファイルに一切触れずに本体の改良だけを取り込める（競合が出ない）。

**本体領域（upstream が所有。案件は編集しない）**

- `src/harness/`・`tests/`・`.claude/skills/`・`templates/`
- `docs/` 直下の説明文書（`docs/*.md`）＝下の「案件領域」に挙げる `docs/charter.md`・`docs/learnings.md` を**除く**すべて
  （`method.md`・`core.md`・`template-copy.md`・各プロファイルの `<名>.md`／`<名>-code.md` など）。**規則で決めるので
  一覧を持たない**：新しいプロファイルの正本 docs（例 `stats.md`）を足しても、この規則で自動的に本体領域になる。
- `AGENTS.md`・`CLAUDE.md`・`checks.toml`・`.pre-commit-config.yaml`・`.github/`

**案件領域（案件が所有。案件だけが中身を決める）**

- `work/`・`issues/`・`docs/charter.md`・`docs/requirements/`・`docs/demands/`・`docs/learnings.md`・`docs/data/*.yaml`・
  `.harness/config.toml`・`data/`
- 注意：この領域は「案件が編集しない本体領域」とは違い、**本体（upstream）も自分の開発履歴として
  `work/EP-*`・`issues/ISS-*` 等を持つ**。テンプレートは自分自身を最初の案件として `work/` にコミットし続けるからだ。
  したがって `git merge upstream/main` は、本体側で増えた作業単位を案件の `work/` に**黙って持ち込む**
  （新規追加は競合すら出ずに流入し、案件が白紙化で消した単位を本体が変更していれば modify/delete で復活する）。
  この経路の塞ぎ方は 4 節。

**両者が所有を分け合う 2 ファイル（正直に規定）**

- `pyproject.toml`・`uv.lock`。案件は依存を足す（`uv add …`）ので、本体が依存を更新すると merge 時に競合し
  うる。ここだけは `git merge upstream/main` の際に人が解決する（案件が足した extra を残しつつ本体の更新を取り込む）。

## 3. 案件領域を白紙化する（`uv run init-project`）

fork 直後は本体（demo 案件）の `work/`・`issues/`・要件・憲章・learnings が入っている。これを 1 コマンドで
白紙化する。手作業の一覧（読み忘れ・やり忘れの発生源）を実行可能にしたもの。

```
uv run init-project                                   # 対話で確認してから初期化・profiles は空（非 DS）
uv run init-project --force --profiles ""             # 非対話（CI・スクリプト用）・非 DS
uv run init-project --force --profiles "harness.ds"   # DS 案件として初期化
```

`uv run init-project` がやること（案件領域だけ）:

- `work/` の前案件の作業単位（`EP-*`・`T-*`・`INV-*`・`E-*`）を消す。
- `issues/` の前案件の課題（`ISS-*`）を消す。
- `docs/requirements/` の前案件の要件（`REQ-*`）を消し、雛形 `REQ-001.md` を置く。
- `docs/demands/` の前案件の要求（`DEM-*`）を消す。
- `docs/charter.md`・`docs/learnings.md` を雛形に戻す。
- `docs/structure-review-*.md`（基盤のレビュー記録＝履歴）を消す。
- `data/` の生成物（実データ・保存済みモデル）を消す。
- `.harness/config.toml` の `profiles` を `--profiles` の値に設定する（非 DS 案件は空＝`[]`）。
- 最後に `uv run verify` を走らせて緑を確認する（`--no-verify` で省ける）。

安全装置：破壊的操作なので `--force` か確認プロンプトが必須。`upstream` リモートが無い（未 fork）状態では拒否する。

### 案件タイプ（DS / 非 DS）

- **非 DS 案件**：`--profiles ""`（空）。DS の検査（テーブル定義 data_lint）・optional 依存が verify から外れ、
  素の `uv sync` で緑になる。AGENTS.md・DoD.md の**「（DS プロファイル）」印は残したまま読み飛ばす**
  （`profiles = []` の案件には効かない項目、という意味）。案件が本体ファイル `AGENTS.md` を手で編集して印を
  外す運用はしない（本体ファイルを編集すると merge 競合の発生源になる）。
- **DS 案件**：`--profiles "harness.ds"`（配信・LLMOps を足すなら `"harness.ds,harness.serve,harness.agent,harness.ops"`）。
  `uv sync --extra ds` を入れ、テーブル定義（`docs/data/*.yaml`）を新データに合わせて作り直す。最初の実験は
  experiment スキルの手順で作る（`templates/experiment/` をコピー元にする）。

## 4. 本体の改良を取り込む（本体 → 案件）

本体領域（`src/harness/` 等）だけを取り込みたいが、素の `git merge upstream/main` は本体側の**案件領域**
（`work/`・`issues/` 等＝本体の開発履歴）も一緒に持ち込む（2 節の注意）。そこで merge のあと、案件領域を
**案件（fork）側の版へ統一して**から確定する。下の `AREAS` が覆うべき案件領域の根の正本は
`src/harness/init_project.py` の `CASE_AREA_ROOTS`（1 か所）。**新しい案件領域の根を足すときはその定数に足す**と、
`AREAS` がそれを覆うこと（`tests/test_template_copy.py`）と scrub がその根の外を触らないこと
（`tests/test_init_project.py`）の両方が検査で強制される＝対象集合が実装の申告に依存しない。

```
git fetch upstream
# 前提：作業ツリーがクリーン（未コミットの案件変更が無い）。下の掃除が未追跡の案件ファイルも消すため。
[ -z "$(git status --porcelain)" ] || { echo "作業ツリーが汚れている。先にコミット/退避してから merge する"; exit 1; }

git merge --no-commit --no-ff upstream/main            # 本体領域も案件領域もいったん取り込む

# 案件領域を fork（HEAD=自分）の版へ統一する（本体由来の作業単位の流入・削除済み単位の復活を捨てる）。
AREAS="work issues docs/requirements docs/demands docs/charter.md docs/learnings.md docs/structure-review-*.md docs/data .harness/config.toml data"
for p in $AREAS; do
  git rm -r --cached --ignore-unmatch -- $p >/dev/null 2>&1 || true   # index から外す（衝突・追加を解消）
  git checkout HEAD -- $p 2>/dev/null || true                        # 自分の版に戻す（無ければ何もしない）
done
git ls-files --others --exclude-standard -- $AREAS | while IFS= read -r f; do rm -f -- "$f"; done  # 本体由来の未追跡を消す
find work issues docs/requirements -type d -empty -delete 2>/dev/null || true

# 案件領域の衝突・混入はこれで解消済み。残る競合は pyproject.toml・uv.lock だけ（2 節。案件の extra を
# 残しつつ本体の更新を取り込む）。競合が残っていれば自動でコミットせず、人が解決してから add/commit する。
if git ls-files -u | grep -q . ; then
  echo "手で解決する競合が残っています："; git diff --name-only --diff-filter=U
  echo "解決したら: git add -A && git commit"
else
  git add -A
  git commit -m "merge upstream (案件領域は fork 側に統一)"
fi
```

取り込んだら `uv run verify` で緑を確認する。この「merge しても案件領域が本体側に汚染されない」性質は
`tests/test_template_copy.py` が、**この文書のレシピをそのまま抜き出して** fork→本体前進→merge を実際に
再生して検査する（保証 (b)＝ここの手順が退行すれば赤くなる）。

## 5. 案件の改良を本体へ戻す（案件 → 本体＝還流）

案件で作った再利用できる改善（検査・抽象・スキル・規約・レジストリの住人）は、本体へ戻して初めて次の案件に
効く。戻し方も差分単位で、専用の台帳・カウンタ・bot は作らない。

- **還流の単位＝「本体領域だけに触る 1 コミット」**。案件内で部品・スキル・検査を作るときは、案件領域の変更
  （`work/`・`docs/charter.md` など）と**同じコミットに混ぜない**。コミット境界＝資産境界にしておくと、その
  コミットをそのまま `git cherry-pick` で本体へ運べる／PR にできる。
- **還流するのは learnings そのものではなく、ルール化の結果**。気づき（`docs/learnings.md`＝案件領域）は
  白紙化で消える一時的な観察の材料であって、本体に運ぶものではない。運ぶのは、その気づきから作った
  **検査・抽象・スキル・規約・レジストリの住人**（＝正本が本体側へ移ったもの）。この「正本が移る」の流れは
  `docs/method.md` C 節が正本。ルール化の手順（learnings に記録 → 落とし先を選ぶ → 検査を先に足す）は harvest スキル。
- **一般性の判断者＝テンプレート側の独立レビュー**（既定はオーナー）。案件のエージェントは還流候補の PR を
  **起こすところまで**（harness-template への PR、または本体領域だけのコミットの cherry-pick を提案する）。
  採否は**テンプレート側の verify 緑＋別文脈のレビュー**が決める（作る側と確かめる側の分離を、案件とテンプレート
  の間にも効かせる）。案件のエージェントが自分の改善を自分で本体に取り込んで完了、とはしない。
- **回数で待たない**。「2 つ以上の案件で役立ったら還流する」という回数基準は使わない（AGENTS.md・method.md の
  「回数で待たず、一般性で判断」に統一）。1 案件目で一般的だと見えたものは、その時点で還流候補にする。
- **還流し忘れを可視化する**。まだ本体へ戻していない本体領域の変更は、fork 分岐点からの git 履歴で洗える
  （台帳・bot は作らない＝対象集合は git から導く）。pathspec は 2 節の本体領域＝案件領域の docs を除いたもの：

  ```
  git log --oneline upstream/main..HEAD -- \
    src tests .claude/skills templates AGENTS.md CLAUDE.md checks.toml .pre-commit-config.yaml .github docs \
    ':(exclude)docs/charter.md' ':(exclude)docs/learnings.md' ':(exclude)docs/requirements' ':(exclude)docs/data'
  ```

  ここに出るコミットが還流候補（本体領域に触れたコミット）。中身が一般的なら PR/cherry-pick を起こす。
