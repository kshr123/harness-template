# テンプレート複製手順（この基盤を次の案件で使う）

この文書は、新しい[案件](glossary.md#案件)を始めるときにこのリポジトリを複製して使うための How-to（手順書）。
このリポジトリは「1 リポジトリ＝1 案件」の雛形で、複製すればこの基盤で作った仕組み
（検証・決まりごと・部品・スキル）を再コーディングせずに引き継げる。

手順は 4 歩：
1. リポジトリを丸ごとコピーする。
2. 「消す・作り直す」の一覧に従って前案件の中身を消し、新案件の内容（charter・REQ）を書く（「残す」の一覧は触らない）。
3. 「複製で壊れやすい点」を直す（e2e のパス・プロファイルの選択）。
4. 「複製後の確認」を行い、`uv run verify` にすべて成功させる。

## 残す（基盤そのもの・触らない）
- `src/harness/` … 中核（pm・issues・checks・config・testing）と DS プロファイル（`src/harness/ds/`）。
- `tests/` … 上記の検査（ただし後述の e2e パス直書きだけ直す）。
- `docs/decisions/`（DEC・不変の決定）・`docs/method.md`（進め方の正本）・`docs/DoD.md`（完了の定義）。
- `.claude/skills/`（スキル）・`AGENTS.md`・`CLAUDE.md`・`pyproject.toml`・`checks.toml`・`.pre-commit-config.yaml`。
- `docs/data/` のテーブル定義の仕組み（中身は案件のデータに合わせて入れ替える）。

## 消す・作り直す（前の案件の中身）
- `work/EP-01-foundation` 〜 `work/EP-08-agent-first-entry` … 前案件の作業単位。**消す**（新案件のエピックを作り直す）。
- `docs/requirements/REQ-*.md` … 前案件の要件。**消す**（新案件の REQ を書く）。
- `issues/ISS-*.md` … 前案件の課題。**消す**（`ISS-0002`〜`0005` のように基盤側の未実装約束を引き継ぐ場合だけ残す）。
- `docs/charter.md` … 立ち上げ文書。**新案件の内容に書き直す**（外部設計文書があればここから参照する）。
- `docs/learnings.md` … 気づき。**空にする**（昇格済みで正本が DEC に移ったものは消してよい）。
- `docs/structure-review-*.md` … 基盤のレビュー記録。**消してよい**（履歴）。
- `data/` の実体・保存済みモデル（`data/**/models/`）… コミットしない生成物。**消す**。

## 複製で壊れやすい点（必ず直す）
1. **e2e のパス直書き**：`tests/test_e2e_experiment.py` は `work/EP-06-ds-experiment-loop/E-0001-.../code/train.py` を
   直接叩く。新案件で E-0001 のフォルダ名が変わると verify（e2e）が落ちる。**最初の実験フォルダに合わせてこのパスを直す**
   （experiment スキルの手順で最初の実験を作ってから、e2e のパスを差し替える）。
2. **非 DS の案件**：`.harness/config.toml` で `profiles = []` にする（または行ごと消す）。これだけで
   DS の検査（テーブル定義 data_lint）が verify から外れる（`checks.py` の手動編集は不要）。
   `pyproject.toml` の `[project.optional-dependencies].ds` は使わないなら残していてよい（入れなければ効かない）。
   AGENTS・DoD の「（DS プロファイル）」印の項目は非 DS では外す。
3. **DS の案件**：`uv sync --extra ds` を入れる。テーブル定義（`docs/data/*.yaml`）を新データに合わせて作り直す。
   最初の実験は experiment スキルの手順で `E-0001` を作る（既存の E-0001 をコピー元にする）。

## 複製後の確認
- `uv run verify` にすべて成功する（e2e のパスを直した後）。
- `uv run status` で新案件の作業単位ツリーが出る（前案件の残骸が無い）。
- `uv run issue list` に前案件の課題が残っていない。

## 将来
[profile](glossary.md#profile)（領域別の部品と検査の束）の登録の仕組みは導入済み（`.harness/config.toml` の
`profiles`＋`src/harness/profiles.py`）。2 つ目のプロファイル（例：アプリ開発）は、`PROFILE` を公開する
モジュールを書いて profiles に足すだけでよい。「（DS プロファイル）」タグの文書側の手動増減が残る
（`docs/method.md` の進化の[ratchet](glossary.md#ratchet)）。
