"""公開モジュールと、対応する正本ドキュメントの役割一覧が食い違っていないかの**双方向**の検査（code_doc_lint）。

これは体裁でなく**ドキュメントの陳腐化防止（保守）**の検査：「どのコードがどんな役割か」を人が（元コードを
読まずに）辿れる状態を強制する＝AGENTS の「部品は元コードを読まずに使える状態にして完了」「使い方に
たどり着けるリンク・記載が必須」をコード側にも効かせる。両向きを見る：

- **順（コード→ドキュメント）**：新しい公開モジュールを足したのに正本ドキュメントで一切触れられていない
  状態を verify で止める。
- **逆（ドキュメント→コード）**：役割一覧が挙げるモジュールが実在しなくなった（コードを消したのに説明の行が
  残った）状態を止める。読者が存在しないコードを探すのを防ぐ。

対象と、対応する正本ドキュメント:
- **プロファイル**＝`src/harness/*/` のうち `profile.py` を持つディレクトリ（ds・serve・agent・ops…）。
  正本は `docs/<プロファイル>.md`（＋あれば `docs/<プロファイル>-code.md`）。
- **中核**＝`src/harness/*.py`（直下・非再帰）。正本は `docs/core.md`（＋あれば `docs/core-code.md`）。
  `profile.py` を持たない下位ディレクトリ（`src/harness/util/` のような入れ子）は対象外。
- **公開モジュール**＝`__init__.py`・`profile.py`（どのプロファイルにも 1 つある同じ形の結線＝説明を要さない）・
  `_` 始まり（私的モジュール）を除いた `*.py`。`cli.py` は中核・プロファイルとも対象（除外しない）。
- **載っている**＝対応する正本ドキュメント（`<名>.md` と `<名>-code.md` を連結した本文）にファイル名
  （例 `runtime.py`）が現れること。役割の説明はドキュメントの散文に委ね、ここは**言及の有無**だけを見る
  （説明の質はレビュー観点。機械化するのは「触れ忘れ」の検出だけ＝過剰検査を避ける正直な線引き）。

免除は `_EXEMPT`（リポジトリ相対のパス `src/harness/…/<モジュール>.py` → 理由）だけ。理由必須
（空は ValueError＝黙って免除しない。doc_source_lint / coverage_lint と同じ作法）。免除を増やす前に
「docs に 1 行足す」を先に検討。core の検査（プロファイル非依存）。stdlib のみに依存。

**この検査が見るのは「言及の有無」と「役割一覧が挙げる名前の実在」だけ**で、説明が正しいか・空でないかは
見ない（説明の質はレビュー観点）。逆向きの対象は「役割一覧の行」に絞る：表の行（`| ` + 名前 + ` |`）か
箇条書き（`- ` + 名前）の**先頭**に来る `<名>.py` だけを拾い、散文の途中の言及は数えない（架空のファイル名を
例示する散文で誤検出しないため）。フルパスのバッククォート（`` `src/harness/x.py` ``）は名前に `/` を含むので
先頭パターンに一致せず、別ディレクトリのモジュールを箇条書きで触れたいときの逃げ道になる。
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import pm

# 素の名前の直前に来てはいけない文字。英数・`_` に加えて、パスの構成文字（`/`・`.`・`-`）も禁じる。
# `_` だけを禁じた版は `schedule_lint.py` に埋もれる `lint.py` は弾けたが、`src/harness/ds/models.py`
# （**別モジュール**へのパス）に含まれる `models.py` は直前が `/` なので通ってしまい、同名の中核モジュールの
# 検査が黙って無効化されていた。パスでの言及は「自分自身の置き場」に一致するときだけ数える（_location_forms）。
_NAME_BOUNDARY = r"(?<![0-9A-Za-z_./-])"
_NAME_END = r"(?![0-9A-Za-z])"  # `pipeline.py` が `pipeline.pyi` に一致しない


def _location_forms(location: str) -> list[str]:
    """そのモジュール自身の置き場を指すパス表記の一覧（親ディレクトリを 1 つ以上含む接尾辞）。

    `src/harness/ds/models.py` → `src/harness/ds/models.py`・`harness/ds/models.py`・`ds/models.py`。
    ファイル名だけ（`models.py`）は含めない＝素の名前として別に判定する。
    """
    parts = location.split("/")
    return ["/".join(parts[i:]) for i in range(len(parts) - 1)]


def _mentioned(module: str, location: str, docs_text: str) -> bool:
    """モジュールが docs 本文で**そのモジュールとして**触れられているか。

    数えるのは 2 つの形だけ：(1) 素の名前（`models.py`）が独立した語として現れる、(2) 自分自身の置き場を
    指すパス（`src/harness/models.py`・`harness/models.py`）が現れる。他モジュールへのパスに名前が
    含まれているだけの一致は数えない。
    """
    if re.search(_NAME_BOUNDARY + re.escape(module) + _NAME_END, docs_text):
        return True
    return any(re.search(_NAME_BOUNDARY + re.escape(form) + _NAME_END, docs_text) for form in _location_forms(location))


# 免除（リポジトリ相対のパス `src/harness/[<プロファイル>/]<モジュール>.py` → なぜドキュメントで触れなくて
# よいかの理由。空は不可）。鍵にパスを使うのは、中核とプロファイルで名前空間が衝突しないようにするため
# （`core/x.py` のような短縮鍵は、将来 `src/harness/core/` というプロファイルを作った瞬間に曖昧になる）。
_EXEMPT: dict[str, str] = {}


def _validated_exempt() -> dict[str, str]:
    """免除リストの理由が空でないことを確かめて返す。空の理由は設定ミス＝即失敗（黙って免除しない）。"""
    for key, reason in _EXEMPT.items():
        if not reason.strip():
            raise ValueError(f"_EXEMPT[{key!r}] の理由が空。免除には人が読める理由が必須（code_doc_lint）")
    return _EXEMPT


def _profile_dirs(root: Path) -> list[Path]:
    """`src/harness/*/` のうち profile.py を持つディレクトリ（＝プロファイル）を名前順で返す。"""
    base = root / "src" / "harness"
    if not base.is_dir():
        return []
    return sorted(d for d in base.iterdir() if d.is_dir() and (d / "profile.py").is_file())


def _public_modules(directory: Path) -> list[str]:
    """直下の公開モジュール名（`profile.py`・`_` 始まりを除く *.py）を名前順で返す。

    `__init__.py` は `_` 始まりなので明示的に除く必要はない（条件を二重に書くと、片方を消しても挙動が
    変わらない＝テストで守れない死んだ条件になる）。`profile.py` はどのプロファイルにも 1 つある同じ形の
    結線なので説明を要さない。
    """
    return sorted(p.name for p in directory.glob("*.py") if p.name != "profile.py" and not p.name.startswith("_"))


def _core_modules(root: Path) -> list[str]:
    """中核（`src/harness/*.py`・非再帰）の公開モジュール名。プロファイルの入れ子は含まない。"""
    base = root / "src" / "harness"
    return _public_modules(base) if base.is_dir() else []


def _docs_text(root: Path, name: str) -> str:
    """正本ドキュメント（`docs/<名>.md`＋`docs/<名>-code.md`）を連結した本文。無いものは飛ばす。"""
    parts: list[str] = []
    for rel in (f"docs/{name}.md", f"docs/{name}-code.md"):
        p = root / rel
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


# 役割一覧の行が先頭で名指しする `<名>.py`。行頭の表区切り（`|`）か箇条書き（`-`/`*`）の直後の
# バッククォート名だけを拾う＝散文の途中の言及（`（`cv.py` の run_cv）` 等）は数えない（逆向きの誤検出回避）。
# 名前は語文字＋`.py` のみ＝フルパス（`src/harness/x.py`）は `/` を含むので一致しない（別ディレクトリを指す逃げ道）。
_ROLE_ROW_RE = re.compile(r"^[ \t]*(?:\||[-*])[ \t]*`([0-9A-Za-z_]+\.py)`")


def _declared_modules(docs_text: str) -> list[str]:
    """役割一覧（表の行・箇条書き）が先頭で名指しする `<名>.py` の一覧（出現順・重複はそのまま）。"""
    return [m.group(1) for line in docs_text.splitlines() if (m := _ROLE_ROW_RE.match(line))]


def _scope_dirs(root: Path) -> list[tuple[str, Path]]:
    """(正本ドキュメント名, モジュールの置き場) の一覧。中核（core→src/harness）＋各プロファイル。

    順向きの対象（core と `_profile_dirs`）と同じ集合を、正本ドキュメント名に対応づけて返す。
    既知の制約：`src/harness/core/profile.py` という名の「core」プロファイルを作ると docs/core.md が
    中核とそのプロファイルの両方に照合されて誤検出する（`_EXEMPT` の鍵と同じ名前空間の衝突）。
    """
    base = root / "src" / "harness"
    scopes: list[tuple[str, Path]] = []
    if base.is_dir():
        scopes.append(("core", base))
    scopes.extend((d.name, d) for d in _profile_dirs(root))
    return scopes


def _stale_role_problem(doc_rel: str, module: str, directory: Path, root: Path) -> pm.Problem:
    """役割一覧に、実在しないモジュールの行が残っている指摘（逆向き）。どの docs のどの名前が空振りかを名指す。"""
    location = (directory / module).relative_to(root).as_posix()  # リポ相対は常に `/`（Windows で `\` にしない）
    return pm.Problem(
        "error",
        f"{doc_rel}: 役割一覧が `{module}` を挙げているが {location} が実在しない。モジュールを消したら"
        f"役割の行も消すこと（読者が存在しないコードを探すのを防ぐ＝code_doc_lint の逆向き）",
    )


def _reverse_checks(root: Path) -> list[pm.Problem]:
    """役割一覧（表・箇条書きの先頭）が挙げるモジュールが、対応する置き場に実在するか（逆向き）。"""
    problems: list[pm.Problem] = []
    for name, directory in _scope_dirs(root):
        for rel in (f"docs/{name}.md", f"docs/{name}-code.md"):
            path = root / rel
            if not path.is_file():
                continue
            for module in _declared_modules(path.read_text(encoding="utf-8")):
                if not (directory / module).is_file():
                    problems.append(_stale_role_problem(rel, module, directory, root))
    return problems


def _problem(location: str, module: str, doc_name: str) -> pm.Problem:
    """触れ忘れの指摘。どのファイルが・どの正本ドキュメントに載っていないかを名指しする。"""
    return pm.Problem(
        "error",
        f"{location}: モジュールが正本ドキュメント（docs/{doc_name}.md／docs/{doc_name}-code.md）で一度も"
        f"触れられていない。どのコードが何を担うかを人が辿れるよう、`{module}` の役割を 1 行足すこと"
        f"（一覧・拡張ポイントの表でも可）。意図的に載せないなら理由つきで _EXEMPT に登録（code_doc_lint）",
    )


def run_checks(root: Path) -> list[pm.Problem]:
    """公開モジュールと正本ドキュメントの役割一覧が食い違っていないか双方向で検査する（順：触れ忘れ／逆：残骸）。"""
    problems: list[pm.Problem] = []
    exempt = _validated_exempt()

    # 順向き：公開モジュールが対応する正本ドキュメントで一度も触れられているか。
    core_docs = _docs_text(root, "core")
    for module in _core_modules(root):
        location = f"src/harness/{module}"
        if location in exempt or _mentioned(module, location, core_docs):
            continue
        problems.append(_problem(location, module, "core"))

    for profile_dir in _profile_dirs(root):
        profile = profile_dir.name
        docs_text = _docs_text(root, profile)
        for module in _public_modules(profile_dir):
            location = f"src/harness/{profile}/{module}"
            if location in exempt or _mentioned(module, location, docs_text):
                continue
            problems.append(_problem(location, module, profile))

    # 逆向き：役割一覧が挙げるモジュールが実在するか（消したのに説明の行が残っていないか）。
    problems.extend(_reverse_checks(root))
    return problems
