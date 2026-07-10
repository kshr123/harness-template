# テンプレート複製手順（この基盤を次の案件で使う）

この文書は、新しい案件（別の開発テーマ・プロジェクト。1 リポジトリ＝1 案件）を始めるときにこのリポジトリを複製して使うための How-to（手順書）。
このリポジトリは「1 リポジトリ＝1 案件」の雛形で、複製すればこの基盤で作った仕組み
（検証・決まりごと・部品・スキル）を再コーディングせずに引き継げる。

手順は 4 歩：
1. リポジトリを丸ごとコピーする。
2. 「消す・作り直す」の一覧に従って前案件の中身を消し、新案件の内容（charter・REQ）を書く（「残す」の一覧は触らない）。
3. 案件タイプ（DS / 非 DS）に合わせて設定する。
4. 「複製後の確認」を行い、`uv run verify` にすべて成功させる。

## 残す（基盤そのもの・触らない）
- `src/harness/` … 中核（pm・issues・checks・config・testing）と DS プロファイル（`src/harness/ds/`）。
- `tests/` … 上記の検査。
- `docs/method.md`（進め方の正本）・`docs/DoD.md`（完了の定義）・`docs/core.md`（中核の正本。自動生成節は
  複製先でも `uv run doc-sync` が同じ内容を作る＝config に依らない）。
- `.claude/skills/`（スキル）・`AGENTS.md`・`CLAUDE.md`・`pyproject.toml`・`checks.toml`・`.pre-commit-config.yaml`。
- `docs/data/` のテーブル定義の仕組み（中身は案件のデータに合わせて入れ替える）。
- `templates/experiment/`（実験の正本雛形＝`train.py`・`config*.yaml`・`data/*.yaml` のテーブル定義。以後の実験は
  これを丸ごとコピーして使う＝experiment スキル参照。雛形は自己完結＝work/ を消しても壊れない）。

## 消す・作り直す（前の案件の中身）
- `work/` 配下の前案件エピック（`EP-*`・`T-*`・`E-*`）… 前案件の作業単位。**消す**（新案件のエピックを作り直す。
  範囲は数えない＝エピックが増えても列挙し直さなくてよい）。
- `docs/requirements/REQ-*.md` … 前案件の要件。**消す**（新案件の REQ を書く）。
- `issues/ISS-*.md` … 前案件の課題。**消す**。ただし `promoted_to`（対応済みの作業単位）を持たない open の課題
  （基盤側の未実装約束）だけは残してよい。`promoted_to` が付いた resolved 済みの課題は、その作業単位が
  `work/` ごと消えると参照エラーになるので必ず消す（判定は各ファイルの frontmatter を見る。
  該当する ID をここに書き並べない＝課題が増減するたびに古くなるため）。
- `docs/charter.md` … 立ち上げ文書。**新案件の内容に書き直す**（外部設計文書があればここから参照する）。
- `docs/learnings.md` … 気づき。**空にする**（ルール化済みで正本が AGENTS/検査に移ったものは消してよい）。
- `docs/structure-review-*.md` … 基盤のレビュー記録。**消してよい**（履歴）。
- `data/` の実体・保存済みモデル（`data/**/models/`）… コミットしない生成物。**消す**。

## 案件タイプに合わせる（DS / 非 DS）
1. **非 DS の案件**：`.harness/config.toml` で `profiles = []` にする（または行ごと消す）。これだけで
   DS の検査（テーブル定義 data_lint）が verify から外れる（`checks.py` の手動編集は不要）。
   `pyproject.toml` の `[project.optional-dependencies].ds` は使わないなら残していてよい（入れなければ効かない）。
   AGENTS・DoD の「（DS プロファイル）」印の項目は非 DS では外す。
2. **DS の案件**：`uv sync --extra ds` を入れる。テーブル定義（`docs/data/*.yaml`）を新データに合わせて作り直す。
   最初の実験は experiment スキルの手順で作る（`templates/experiment/` をコピー元にする）。

## 複製後の確認
- `uv run verify` にすべて成功する。
- `uv run status` で新案件の作業単位ツリーが出る（前案件の残骸が無い）。
- `uv run issue list` に前案件の課題が残っていない。

## 将来
profile（領域別の部品と検査の束）の登録の仕組みは導入済み（`.harness/config.toml` の
`profiles`＋`src/harness/profiles.py`）。2 つ目のプロファイル（例：アプリ開発）は、`PROFILE` を公開する
モジュールを書いて profiles に足すだけでよい。「（DS プロファイル）」タグの文書側の手動増減が残る
（`docs/method.md` の進化の歯止め＝一度上げた基準を後戻りさせない仕組み）。
