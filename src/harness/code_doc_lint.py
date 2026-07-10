"""公開モジュールが、対応する正本ドキュメントに載っているかの検査（code_doc_lint）。

これは体裁でなく**ドキュメントの陳腐化防止（保守）**の検査：新しいモジュールを足したのに正本ドキュメントで
一切触れられていない状態を verify で止める。「どのコードがどんな役割か」を人が（元コードを読まずに）辿れる
状態を強制する＝AGENTS の「部品は元コードを読まずに使える状態にして完了」「使い方にたどり着けるリンク・
記載が必須」をコード側にも効かせる。

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

**この検査が見るのは「言及の有無」だけ**で、説明が正しいか・空でないかは見ない（説明の質はレビュー観点）。
モジュールを削除したあとに docs の行が残っていても検出しない（逆向きの腐り＝正本ドキュメントに
実在しないモジュール名の行が残る、は現状どの検査も落とさない。未解決の既知の穴）。
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


def _problem(location: str, module: str, doc_name: str) -> pm.Problem:
    """触れ忘れの指摘。どのファイルが・どの正本ドキュメントに載っていないかを名指しする。"""
    return pm.Problem(
        "error",
        f"{location}: モジュールが正本ドキュメント（docs/{doc_name}.md／docs/{doc_name}-code.md）で一度も"
        f"触れられていない。どのコードが何を担うかを人が辿れるよう、`{module}` の役割を 1 行足すこと"
        f"（一覧・拡張ポイントの表でも可）。意図的に載せないなら理由つきで _EXEMPT に登録（code_doc_lint）",
    )


def run_checks(root: Path) -> list[pm.Problem]:
    """公開モジュールが正本ドキュメント（中核＝docs/core.md・プロファイル＝docs/<名>.md）に載っているか検査する。"""
    problems: list[pm.Problem] = []
    exempt = _validated_exempt()

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
    return problems
