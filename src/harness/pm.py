"""PM層の中核ロジック：タスク／WBS の読み込み、STATUS 導出、孤児検出。

- タスク（葉）が存在と状態の唯一の情報源。
- WBS/エピックは意図と計画の成熟度だけを持ち、配下と進捗は導出する。
- lint は余白（outline エピック・epic: none）を許容し、真の孤児だけ赤にする。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import frontmatter
from pydantic import ValidationError

from harness.models import NONE_EPIC, Epic, Task, TaskStatus


@dataclass(frozen=True)
class LoadedTask:
    path: Path
    task: Task


@dataclass(frozen=True)
class Problem:
    """検証の指摘。level="error" だけが赤（合否を落とす）。"""

    level: str  # "error" | "info"
    message: str


def load_tasks(root: Path) -> tuple[list[LoadedTask], list[Problem]]:
    """tasks/*.md を読み、型検証する。壊れた frontmatter は error。"""

    tasks: list[LoadedTask] = []
    problems: list[Problem] = []
    tasks_dir = root / "tasks"
    if not tasks_dir.is_dir():
        return tasks, problems
    for path in sorted(tasks_dir.glob("*.md")):
        if path.name in {"STATUS.md", "_template.md"}:
            continue
        post = frontmatter.load(path)
        try:
            task = Task.model_validate(dict(post.metadata))
        except ValidationError as exc:
            problems.append(
                Problem("error", f"{path.name}: frontmatter が不正: {exc.error_count()} 件")
            )
            continue
        tasks.append(LoadedTask(path, task))
    return tasks, problems


def load_epics(root: Path) -> tuple[dict[str, Epic], list[Problem]]:
    """projects/<案件>/wbs.md の frontmatter `epics` を読み、型検証する。"""

    epics: dict[str, Epic] = {}
    problems: list[Problem] = []
    for wbs in sorted((root / "projects").glob("*/wbs.md")):
        post = frontmatter.load(wbs)
        raw_epics = post.metadata.get("epics") or []
        if not isinstance(raw_epics, list):
            problems.append(Problem("error", f"{wbs.parent.name}/wbs.md: epics はリストが必要"))
            continue
        for raw in raw_epics:
            try:
                epic = Epic.model_validate(raw)
            except ValidationError as exc:
                problems.append(
                    Problem(
                        "error", f"{wbs.parent.name}/wbs.md: エピックが不正: {exc.error_count()} 件"
                    )
                )
                continue
            epics[epic.id] = epic
    return epics, problems


def lint(root: Path) -> list[Problem]:
    """孤児検出（余白を許容する lint）。真の孤児だけ error（赤）。"""

    tasks, problems = load_tasks(root)
    epics, epic_problems = load_epics(root)
    problems.extend(epic_problems)
    known = set(epics)

    for lt in tasks:
        epic = lt.task.epic
        if epic == NONE_EPIC:
            problems.append(Problem("info", f"{lt.path.name}: epic: none（バックログ＝割当待ち）"))
        elif epic not in known:
            # 真の孤児＝存在しないエピックを指す（付け替え忘れ・typo）。ここだけ赤。
            problems.append(
                Problem("error", f"{lt.path.name}: 存在しないエピック '{epic}'（真の孤児）")
            )

    # detailed なのにタスク 0 件＝分解漏れの合図（赤にしない）。
    used = {lt.task.epic for lt in tasks}
    for ep in epics.values():
        if ep.plan.value == "detailed" and ep.id not in used:
            problems.append(
                Problem("info", f"{ep.id}: plan=detailed だがタスク 0 件（分解漏れの可能性）")
            )
        # outline でタスク 0 件＝正常な余白。何も言わない。

    return problems


def render_status(root: Path) -> str:
    """タスクと WBS から STATUS.md（生成物）を導出する。手書き禁止。"""

    tasks, _ = load_tasks(root)
    epics, _ = load_epics(root)

    by_epic: dict[str, list[Task]] = {}
    for lt in tasks:
        by_epic.setdefault(lt.task.epic, []).append(lt.task)

    lines: list[str] = [
        "<!-- 生成物：uv run status が自動生成する。手編集禁止。 -->",
        "# STATUS（エピック別の進捗＋計画の成熟度）",
        "",
        "| エピック | plan | 目的 | done/総数 | blocked | 関連要件 |",
        "|---|---|---|---|---|---|",
    ]

    for epic in epics.values():
        ts = by_epic.get(epic.id, [])
        total = len(ts)
        done = sum(1 for t in ts if t.status is TaskStatus.done)
        blocked = sum(1 for t in ts if t.status is TaskStatus.blocked)
        if epic.plan.value == "outline" and total == 0:
            progress = "—（未分解＝余白）"
        else:
            progress = f"{done}/{total}" + (" ✅" if total and done == total else "")
        reqs = ", ".join(epic.requirements) if epic.requirements else "—"
        lines.append(
            f"| {epic.id} {epic.name} | {epic.plan.value} | {epic.name} | "
            f"{progress} | {blocked} | {reqs} |"
        )

    backlog = by_epic.get(NONE_EPIC, [])
    if backlog:
        done = sum(1 for t in backlog if t.status is TaskStatus.done)
        total = len(backlog)
        lines.append(f"| （バックログ：epic: none） | — | 割当待ち | {done}/{total} | — | — |")

    lines.append("")
    return "\n".join(lines)
