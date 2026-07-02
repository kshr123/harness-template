"""課題（発見された問題・リスク・疑問）の登録簿。

作業単位の木とは別に、open→対応中→解決／見送り という生涯を持つ課題を扱う。
置き場は設定（config の issues.backend）で切り替える。この段階では file:（ローカルのファイル）だけ実装し、
github:（GitHub Issues）はインターフェースを固定して後続で足す。
対処すると決めた課題は promoted_to で作業単位（タスク・調査）に結びつける（紐付けの正本は課題側）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path

import frontmatter
from pydantic import BaseModel, ConfigDict, ValidationError

from harness import pm
from harness.config import load_config
from harness.models import Status

ISSUE_FILE = re.compile(r"^ISS-\d+.*\.md$")


class IssueKind(StrEnum):
    """課題の種別。不具合・リスク・疑問。"""

    bug = "bug"  # 不具合（起きた問題）
    risk = "risk"  # リスク（起きるかもしれない問題）
    question = "question"  # 疑問（確認が要ること）


class IssueState(StrEnum):
    """課題の状態。見送り（wontfix）も正しい終わり方。"""

    open = "open"
    in_progress = "in-progress"
    resolved = "resolved"
    wontfix = "wontfix"


class Issue(BaseModel):
    """1 件の課題の frontmatter。"""

    model_config = ConfigDict(extra="forbid")

    id: str  # ISS-0001。一意・再利用しない。
    kind: IssueKind
    state: IssueState
    title: str | None = None
    found_in: str | None = None  # 発見元（作業単位 ID・場面）
    promoted_to: str | None = None  # 昇格先の作業単位 ID（T-xxxx / INV-xxxx）
    created: date | None = None
    closed: date | None = None

    @property
    def display(self) -> str:
        return f"{self.id} {self.title}" if self.title else self.id


@dataclass
class LoadedIssue:
    issue: Issue
    path: Path
    body: str


def local_dir(root: Path) -> Path | None:
    """課題の置き場（ローカル）。github: backend のときは None を返す。"""
    backend = load_config(root).issues.backend
    if backend.startswith("file:"):
        return root / backend[len("file:") :]
    if backend.startswith("github:"):
        return None
    raise ValueError(f"課題の置き場 '{backend}' が不正（file: か github: を使う）")


def load_issues(root: Path, problems: list[pm.Problem] | None = None) -> list[LoadedIssue]:
    """課題を読む。github: backend のときは空を返す（実アダプタは後続）。"""
    d = local_dir(root)
    if d is None or not d.is_dir():
        return []
    out: list[LoadedIssue] = []
    for entry in sorted(d.iterdir()):
        if entry.is_file() and ISSUE_FILE.match(entry.name):
            post = frontmatter.load(entry)
            try:
                issue = Issue.model_validate(dict(post.metadata))
            except ValidationError as exc:
                if problems is not None:
                    problems.append(pm.Problem("error", f"{entry.name}: frontmatter が不正: {exc.error_count()} 件"))
                continue
            out.append(LoadedIssue(issue, entry, post.content))
    return out


def run_checks(root: Path) -> list[pm.Problem]:
    """課題の整合検査。作業単位との紐付けが崩れていないかを見る（backend によらず同じ）。"""
    problems: list[pm.Problem] = []
    loaded = load_issues(root, problems)
    top, _ = pm.load_tree(root)
    status_by_id = {n.item.id: n.item.status for n in pm._all_nodes(top)}

    for li in loaded:
        iss = li.issue
        pt = iss.promoted_to
        if pt is not None and pt not in status_by_id:
            problems.append(pm.Problem("error", f"{iss.id}: promoted_to の '{pt}' が見つからない"))
        if iss.state is IssueState.resolved:
            if pt is None:
                problems.append(pm.Problem("error", f"{iss.id}: resolved だが promoted_to が空"))
            elif pt in status_by_id and status_by_id[pt] is not Status.done:
                problems.append(pm.Problem("error", f"{iss.id}: resolved だが対応先 {pt} が done でない"))
        if (
            pt in status_by_id
            and status_by_id[pt] is Status.done
            and iss.state
            in (
                IssueState.open,
                IssueState.in_progress,
            )
        ):
            problems.append(pm.Problem("error", f"{iss.id}: 対応先 {pt} が done なのに課題が未解決のまま"))
        if iss.state is IssueState.wontfix and "## 理由" not in li.body:
            problems.append(pm.Problem("error", f"{iss.id}: 見送り（wontfix）に「## 理由」の節が無い"))
    return problems


def open_pending(root: Path) -> list[str]:
    """未対処（open）の課題を「人の判断待ち」に載せる行にする。"""
    return [
        f"- 課題 {li.issue.display}：未対処（open）" for li in load_issues(root) if li.issue.state is IssueState.open
    ]


def next_id(root: Path) -> str:
    """次の課題 ID（ISS- のゼロ埋め連番）。"""
    nums = [int(m.group(1)) for li in load_issues(root) if (m := re.match(r"ISS-(\d+)", li.issue.id))]
    return f"ISS-{max(nums, default=0) + 1:04d}"
