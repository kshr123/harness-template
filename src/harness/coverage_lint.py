"""CLI コマンドの導線カバレッジ検査（coverage_lint）。

doclint（参照実在＝dead link）の逆向きを止める：**新しい能力（CLI コマンド）が増えたのに、
スキル/正本 docs に導線が書かれない（missing link）**を機械で検出する。「部品は入口まで
作って完了」の第 3 要件（スキル/雛形からの導線）の機械化。core の検査（プロファイル非依存）。

方針（doclint と同じテキスト/AST 作法＝プロファイル境界を壊さない）:
- 走査対象は **2 経路**：typer 装飾子（下記 ast 走査）＋ ルート `pyproject.toml` の `[project.scripts]` の
  キー（plain main。stdlib の tomllib で読む・無ければ読み飛ばす）。到達可能性の判定は両経路とも同一で、
  同じトークンを両経路が拾っても error は 1 回だけ（typer 装飾子を持たない plain main〔typer.run を呼ぶ
  関数〕が導線検査の死角だった穴を、この 2 経路目で塞ぐ）。
- `src/harness/**/cli.py` を **ast で解析**する（import しない＝ds/serve/agent の重い依存を引き込まない）。
  各関数の装飾子 `@<app>.command("name")` を全抽出し、app 変数名から `_app` を剥がして接頭辞を導出する
  （`data_app`→`data`・`issue_app`→`issue`・`serve_app`→`serve`）。`_app` で終わらない変数の `.command` は
  対象外（他オブジェクトのメソッド呼び出しと区別できないため保守的に拾わない）。
- 到達可能の判定はトークン＝`f"{prefix} {name}"`（`name == prefix` のときは `prefix` 単体＝
  `serve_app.command("serve")` → `"serve"`）が、探索コーパスの連結テキストに **`uv run <トークン>` の形
  （語境界つき正規表現）**で 1 回以上現れること。現れない＝error（どの cli.py のどのコマンドが未到達かを
  名指しする）。単なる部分文字列一致（`serve` が `deserve` に当たる／`data blocks` という語が否定文中に
  出るだけで合格になる、等）は誤検出のため使わない。「実際に `uv run` の後ろに置かれて案内されている」
  ことだけを到達とみなす（意味を読む＝否定文の判定はしない。機械には無理なので語境界の照合に留める）。
- 探索コーパス＝`.claude/skills/**/*.md`（再帰）＋ `AGENTS.md` ＋ `README.md` ＋ `docs/*.md`（非再帰＝
  正本の置き場だけ。docs/archive/ 等の下層は導線でなく記録なので数えない）。無いファイルは読み飛ばす。
- 免除は `_EXEMPT`（トークン→理由）だけ。真に導線不要な内部コマンドを、**理由必須**で明示的に載せる
  （サイレントな見逃しを防ぐ。理由が空は設定ミスとして ValueError で即失敗＝fail closed）。
  免除を増やす前に「導線を足す」を先に検討すること。
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

from harness import pm

# 免除リスト：真に導線不要な内部コマンドだけ（トークン → なぜ導線が不要かの理由。空は不可）。
_EXEMPT: dict[str, str] = {
    "data lint": (
        "テーブル定義（スキーマ YAML）の静的検査の内部入口。verify（ds プロファイルの invariant_checks）が"
        "毎回自動で呼ぶため、人・エージェントがスキル経由で直接叩く導線を必要としない。"
    ),
    "changelog": (
        "Phase 0 の未実装骨格（cli.py の changelog_main は「未実装」を echo するだけで機能が無い）。"
        "実装時にスキル/正本 docs へ導線を張り、この免除を外すこと（silent 免除にしない）。"
    ),
}

# コーパスの固定ファイル（存在するものだけ読む）。glob の対象は _corpus を参照。
_CORPUS_FIXED = ("AGENTS.md", "README.md")


def _validated_exempt() -> dict[str, str]:
    """免除リストの理由が空でないことを確かめて返す。空の理由は設定ミス＝即失敗（黙って免除しない）。"""
    for token, reason in _EXEMPT.items():
        if not reason.strip():
            raise ValueError(f"_EXEMPT[{token!r}] の理由が空。免除には人が読める理由が必須（coverage_lint）")
    return _EXEMPT


def _cli_files(root: Path) -> list[Path]:
    """検査対象＝src/harness/ 以下のすべての cli.py（プロファイル問わず・無ければ空）。"""
    src = root / "src" / "harness"
    return sorted(src.rglob("cli.py")) if src.is_dir() else []


def _command_tokens(path: Path) -> list[str]:
    """cli.py を ast で解析し、`@<app>.command("name")` から到達可能性トークンを全抽出する。

    トークン＝`{接頭辞} {name}`（接頭辞は app 変数名から `_app` を剥がしたもの）。`name == 接頭辞` の
    ときは接頭辞単体（`serve_app.command("serve")` → `"serve"`＝`uv run serve` で呼ぶ形と一致させる）。
    名前を文字列リテラルで明示しない `command()` は対象外（保守的に拾わない）。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tokens: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "command"):
                continue
            app = dec.func.value
            if not (isinstance(app, ast.Name) and app.id.endswith("_app")):
                continue
            if not (dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str)):
                continue
            prefix = app.id.removesuffix("_app")
            name = dec.args[0].value
            token = prefix if name == prefix else f"{prefix} {name}"
            if token not in tokens:  # 同名の重複定義でも指摘は 1 回
                tokens.append(token)
    return tokens


def _script_tokens(root: Path) -> list[str]:
    """ルート `pyproject.toml` の `[project.scripts]` のキー（コマンド名）を到達可能性トークンとして返す。

    plain main（typer.run 型・装飾子を持たない）も導線検査に載せる（この経路が無いと死角になる）。読み取りは stdlib の
    tomllib だけ（重い依存・ネットワークゼロ）。ファイルが無ければ静かに読み飛ばす（既存作法と同じ）。
    """
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return []
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        return []
    scripts = project.get("scripts")
    if not isinstance(scripts, dict):
        return []
    return [key for key in scripts if isinstance(key, str)]


def _reachable(token: str, corpus: str) -> bool:
    """トークンが `uv run <token>` の形（語境界つき）でコーパスに現れるかを判定する。

    `token in corpus` の部分文字列一致（`serve` が `deserve` に当たる／1 語のコマンドが本文にただ出現する
    だけで合格になる）をやめ、「実際に `uv run` の後ろに置かれて案内されている」ことだけを到達とみなす。
    前後は非単語文字（空白・バッククォート・句読点など）を要求する語境界（`\\w` でも `-` でもない）。
    トークンにハイフンを含むコマンド（`task-lint` 等）もこの境界で正しく区切れる。
    """
    pattern = re.compile(r"(?<![\w-])uv run " + re.escape(token) + r"(?![\w-])")
    return pattern.search(corpus) is not None


def _corpus(root: Path) -> str:
    """導線の探索コーパス（スキル＋AGENTS＋README＋docs 直下）を連結して返す。無いファイルは読み飛ばす。"""
    parts: list[str] = []
    skills = root / ".claude" / "skills"
    if skills.is_dir():
        parts.extend(p.read_text(encoding="utf-8") for p in sorted(skills.rglob("*.md")))
    parts.extend(p.read_text(encoding="utf-8") for rel in _CORPUS_FIXED if (p := root / rel).is_file())
    docs = root / "docs"
    if docs.is_dir():
        parts.extend(p.read_text(encoding="utf-8") for p in sorted(docs.glob("*.md")))
    return "\n".join(parts)


def run_checks(root: Path) -> list[pm.Problem]:
    """CLI コマンドの導線カバレッジ検査。スキル/正本 docs から到達できないコマンド＝error。"""
    problems: list[pm.Problem] = []
    exempt = _validated_exempt()
    corpus = _corpus(root)
    reported: set[str] = set()  # 報告済み token（typer 走査と scripts 走査の重複報告を防ぐ）
    for cli in _cli_files(root):
        rel = cli.relative_to(root).as_posix()
        for token in _command_tokens(cli):
            if token in exempt or _reachable(token, corpus):
                continue
            reported.add(token)
            problems.append(
                pm.Problem(
                    "error",
                    f"{rel}: コマンド '{token}' への導線が無い（.claude/skills/**・AGENTS.md・README.md・"
                    f"docs/*.md のどこにも現れない）。スキルか正本 docs に使い方を 1 行足すこと"
                    f"（真に内部専用なら coverage_lint の _EXEMPT に理由つきで。第 3 要件）",
                )
            )
    for token in _script_tokens(root):
        if token in exempt or _reachable(token, corpus) or token in reported:
            continue
        problems.append(
            pm.Problem(
                "error",
                f"pyproject.toml: [project.scripts] のコマンド '{token}' への導線が無い（.claude/skills/**・"
                f"AGENTS.md・README.md・docs/*.md のどこにも現れない）。スキルか正本 docs に使い方を 1 行"
                f"足すこと（真に内部専用なら coverage_lint の _EXEMPT に理由つきで）",
            )
        )
    return problems
