"""time-based routine 雛形（templates/schedule/）の構造 lint（参照整合を verify で守る）。

実行しない・ネットワークも使わない。GitHub Actions の scheduled workflow は「利用者がコピーする雛形」
なので実 schedule は動かせないが、trigger（schedule.cron）・stop 宣言（「止め方の無い routine を
作らない」の機械化）・叩いている CLI サブコマンドが `pyproject.toml` の `[project.scripts]` に実在するか、
は静的に検査できる（serve の deploy_lint と同じ思想の実行できない資産版・DEC-0009）。

`templates/schedule/` が無いプロジェクト（＝コピーして使う先の案件）では何も指摘しない（誤検知しない）。
依存は stdlib＋pyyaml のみ（agent extra 無しでも verify で走る）。yaml・tomllib は関数内で遅延取り込みする
（プロファイルのモジュールを軽く保つ規約＝DEC-0013）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from harness import pm

# 必須ファイル（templates/schedule/ からの相対）。1 つでも欠けると雛形として使えない。
_REQUIRED = ("monitor.yml", "README.md")

# monitor を定期実行しているとみなす CLI（agent/data の monitor サブコマンドを叩く想定）。
_MONITOR_SCRIPTS = ("agent", "data")


def run_checks(root: Path) -> list[pm.Problem]:
    """templates/schedule/ の構造整合を検査し、指摘（error/info）を返す。root は自リポ or コピー先。"""
    import yaml

    base = root / "templates" / "schedule"
    if not base.exists():
        return []  # コピーして使う先の案件（テンプレートを同梱しない）＝検査対象外

    problems: list[pm.Problem] = []

    present = {rel: (base / rel).is_file() for rel in _REQUIRED}
    for rel in _REQUIRED:
        if not present[rel]:
            problems.append(pm.Problem("error", f"templates/schedule/{rel}: 必須ファイルが無い"))

    monitor_text = (base / "monitor.yml").read_text(encoding="utf-8") if present["monitor.yml"] else None
    readme_text = (base / "README.md").read_text(encoding="utf-8") if present["README.md"] else None

    doc: Any = None
    if monitor_text is not None:
        try:
            doc = yaml.safe_load(monitor_text)
        except yaml.YAMLError:
            # YAML 妥当性・workflow 構造の型は actionlint/check-jsonschema へ委譲（自前では報告しない。
            # 読めない場合は doc=None のまま＝doc に依存する検査（trigger/permissions/concurrency）だけ
            # 静かに skip する。stop コメント・scripts 実在は raw text 相手なので影響を受けない）。
            doc = None

    if isinstance(doc, dict):
        # 落とし穴：pyyaml は YAML 1.1 の implicit resolver で `on:` を bool True に読む。
        # 文字列 "on" とキー True の両方を受ける（外すと全 workflow が trigger 無し誤検知になる）。
        on_block = doc.get("on", doc.get(True))
        _check_trigger(problems, on_block)
        _check_permissions(problems, doc)
        _check_concurrency(problems, doc)

    if monitor_text is not None:
        _check_stop_comment(problems, monitor_text)
        _check_scripts(problems, root, monitor_text)

    if readme_text is not None:
        _check_stop_heading(problems, readme_text)

    return problems


# --- trigger（schedule.cron ＋ workflow_dispatch） ---


def _cron_entries(on_block: Any) -> list[str]:
    schedule = on_block.get("schedule") if isinstance(on_block, dict) else None
    if not isinstance(schedule, list):
        return []
    return [entry["cron"] for entry in schedule if isinstance(entry, dict) and isinstance(entry.get("cron"), str)]


def _check_trigger(problems: list[pm.Problem], on_block: Any) -> None:
    if not isinstance(on_block, dict):
        problems.append(pm.Problem("error", "templates/schedule/monitor.yml: on（トリガ）が無い"))
        return

    crons = [c for c in _cron_entries(on_block) if c.strip()]
    if not crons:
        problems.append(
            pm.Problem(
                "error", "templates/schedule/monitor.yml: on.schedule に cron が無い（time-based trigger が無い）"
            )
        )
    # cron の構文（フィールド数等）は actionlint へ委譲（自前では存在だけを見る）。

    if "workflow_dispatch" not in on_block:
        problems.append(
            pm.Problem("error", "templates/schedule/monitor.yml: on.workflow_dispatch が無い（手動起動の口が無い）")
        )


# --- permissions / concurrency ---


def _check_permissions(problems: list[pm.Problem], doc: dict[str, Any]) -> None:
    if "permissions" not in doc:
        problems.append(pm.Problem("error", "templates/schedule/monitor.yml: permissions が無い"))


def _check_concurrency(problems: list[pm.Problem], doc: dict[str, Any]) -> None:
    if "concurrency" not in doc:
        problems.append(pm.Problem("info", "templates/schedule/monitor.yml: concurrency が無い（多重起動の抑止なし）"))


# --- stop 宣言（「止め方の無い routine を作らない」の機械化） ---


def _check_stop_comment(problems: list[pm.Problem], monitor_text: str) -> None:
    # 言語非依存の構造マーカー（`# stop: ...`）で検出する（英語 README の複製先で日本語「停止」grep が
    # 即壊れる言語過剰適合を避ける。意味論＝「止め方の無い routine を作らない」は不変）。
    if re.search(r"^\s*#\s*stop:", monitor_text, re.MULTILINE | re.IGNORECASE) is None:
        problems.append(
            pm.Problem(
                "error",
                "templates/schedule/monitor.yml: `# stop:` マーカーを含むコメント行が無い（停止手順の宣言が無い）",
            )
        )
        return
    comment_lines = re.findall(r"^\s*#.*$", monitor_text, re.MULTILINE)
    if not any(("README" in ln) or ("docs/agent.md" in ln) for ln in comment_lines):
        problems.append(
            pm.Problem(
                "error",
                "templates/schedule/monitor.yml: `# stop:` コメントが README/docs/agent.md を参照していない",
            )
        )


def _check_stop_heading(problems: list[pm.Problem], readme_text: str) -> None:
    # 英語見出し（`## Stop` 等）も日本語見出し（`## 停止`）も受ける（言語非依存化。既存の日本語見出しの
    # 複製先を壊さないための両対応）。
    if re.search(r"^#{1,6}\s.*(停止|stop)", readme_text, re.MULTILINE | re.IGNORECASE) is None:
        problems.append(pm.Problem("error", "templates/schedule/README.md: 「stop（停止）」の見出しが無い"))


# --- 叩いている CLI サブコマンドが pyproject.toml の [project.scripts] に実在するか ---


def _check_scripts(problems: list[pm.Problem], root: Path, monitor_text: str) -> None:
    run_lines = re.findall(r"run:\s*(.+)$", monitor_text, re.MULTILINE)
    uv_run_calls = [m.group(1) for line in run_lines for m in re.finditer(r"uv run (\S+)", line)]

    if not any(script in _MONITOR_SCRIPTS for script in uv_run_calls):
        problems.append(
            pm.Problem(
                "error",
                "templates/schedule/monitor.yml: uv run agent/data 系の run 行が無い（monitor を叩いていない）",
            )
        )

    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return
    import tomllib

    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return  # 壊れた pyproject.toml は別の検査（中核 lint）の領分
    scripts = (data.get("project") or {}).get("scripts") or {}
    for script in uv_run_calls:
        if script not in scripts:
            problems.append(
                pm.Problem(
                    "error",
                    f"templates/schedule/monitor.yml: uv run {script} の '{script}' が pyproject.toml の "
                    "[project.scripts] に無い",
                )
            )
