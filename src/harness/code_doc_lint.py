"""プロファイルの公開モジュールが、そのプロファイルの正本ドキュメントに載っているかの検査（code_doc_lint）。

これは体裁でなく**ドキュメントの陳腐化防止（保守）**の検査：新しいモジュールを足したのに正本ドキュメント
（`docs/<プロファイル>.md`＋あれば `docs/<プロファイル>-code.md`）で一切触れられていない状態を verify で止める。
「どのコードがどんな役割か」を人が（元コードを読まずに）辿れる状態を強制する＝AGENTS の「部品は元コードを
読まずに使える状態にして完了」「使い方にたどり着けるリンク・記載が必須」をコード側にも効かせる。

対象と判定:
- **プロファイル**＝`src/harness/*/` のうち `profile.py` を持つディレクトリ（ds・serve・agent・ops…）。config で
  差し替わる部品群の置き場で、ここに足したモジュールは正本ドキュメントで説明されるべき。core 直下
  （プロファイルでない共通部品）は対象外＝ここは「プロファイルの拡張ポイント」を守る検査に絞る。
- **公開モジュール**＝そのディレクトリ直下の `*.py` から `__init__.py`・`profile.py`（どのプロファイルにも 1 つ
  ある同型の結線＝説明を要さない）・`_` 始まり（私的モジュール）を除いたもの。
- **載っている**＝そのプロファイルの正本ドキュメント（`docs/<名>.md` と `docs/<名>-code.md` を連結した本文）に
  ファイル名（例 `runtime.py`）が現れること。役割の説明はドキュメントの散文に委ね、ここは**言及の有無**だけを見る
  （説明の質はレビュー観点。機械化するのは「触れ忘れ」の検出だけ＝過剰検査を避ける正直な線引き）。

免除は `_EXEMPT`（`<プロファイル>/<モジュール>.py` → 理由）だけ。理由必須（空は ValueError＝黙って免除しない。
doc_source_lint / coverage_lint と同型）。免除を増やす前に「docs に 1 行足す」を先に検討。core の検査
（プロファイル非依存）。stdlib のみに依存。
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import pm


def _mentioned(module: str, docs_text: str) -> bool:
    """モジュール名が docs 本文に**独立した語**として現れるか。

    素朴な部分文字列一致だと `lint.py` が `schedule_lint.py`（同じプロファイルの別モジュール）に埋もれて
    常に真になり、`lint.py` 自身の検査が無効化される。語頭に境界（直前が `_` や英数でない）を要求して、
    `_lint.py` 族（`schedule_lint.py`・`deploy_lint.py`・`ci_lint.py`）の内部一致を弾く。
    """
    return re.search(r"(?<![0-9A-Za-z_])" + re.escape(module), docs_text) is not None


# 免除（`<プロファイル>/<モジュール>.py` → なぜドキュメントで触れなくてよいかの理由。空は不可）。
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


def _public_modules(profile_dir: Path) -> list[str]:
    """プロファイル直下の公開モジュール名（`__init__.py`・`profile.py`・`_` 始まりを除く *.py）を名前順で返す。"""
    return sorted(
        p.name
        for p in profile_dir.glob("*.py")
        if p.name not in {"__init__.py", "profile.py"} and not p.name.startswith("_")
    )


def _profile_docs_text(root: Path, profile: str) -> str:
    """そのプロファイルの正本ドキュメント（`docs/<名>.md`＋`docs/<名>-code.md`）を連結した本文。無いものは飛ばす。"""
    parts: list[str] = []
    for rel in (f"docs/{profile}.md", f"docs/{profile}-code.md"):
        p = root / rel
        if p.is_file():
            parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def run_checks(root: Path) -> list[pm.Problem]:
    """各プロファイルの公開モジュールが、そのプロファイルの正本ドキュメントに載っているか検査する。欠落＝error。"""
    problems: list[pm.Problem] = []
    exempt = _validated_exempt()
    for profile_dir in _profile_dirs(root):
        profile = profile_dir.name
        docs_text = _profile_docs_text(root, profile)
        for module in _public_modules(profile_dir):
            if f"{profile}/{module}" in exempt:
                continue
            if not _mentioned(module, docs_text):
                problems.append(
                    pm.Problem(
                        "error",
                        f"src/harness/{profile}/{module}: プロファイル '{profile}' のモジュールが正本ドキュメント"
                        f"（docs/{profile}.md／docs/{profile}-code.md）で一度も触れられていない。どのコードが何を"
                        f"担うかを人が辿れるよう、`{module}` の役割を 1 行足すこと（一覧・拡張ポイントの表でも可）。"
                        f"意図的に載せないなら理由つきで _EXEMPT に登録（code_doc_lint）",
                    )
                )
    return problems
