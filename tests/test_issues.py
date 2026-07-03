"""課題の登録簿のテスト：整合検査と未対処の集約。"""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from harness import issues

pytestmark = pytest.mark.unit


def _work(root: Path, unit_id: str, kind: str, status: str) -> None:
    ep = root / "work" / "EP-01"
    ep.mkdir(parents=True, exist_ok=True)
    if not (ep / "item.md").exists():
        (ep / "item.md").write_text("---\nid: EP-01\nkind: epic\nstatus: in-progress\n---\n", encoding="utf-8")
    post = frontmatter.Post("")
    post.metadata.update({"id": unit_id, "kind": kind, "status": status})
    (ep / f"{unit_id}-x.md").write_text(frontmatter.dumps(post), encoding="utf-8")


def _issue(root: Path, iid: str, kind: str, state: str, body: str = "", **extra: object) -> None:
    d = root / "issues"
    d.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body)
    post.metadata.update({"id": iid, "kind": kind, "state": state, **extra})
    (d / f"{iid}.md").write_text(frontmatter.dumps(post), encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in issues.run_checks(root) if p.level == "error"]


def test_open_issue_is_ok_and_appears_in_pending(tmp_path: Path) -> None:
    _issue(tmp_path, "ISS-0001", "question", "open", title="q")
    assert not _errors(tmp_path)
    assert any("ISS-0001" in line for line in issues.open_pending(tmp_path))


def test_resolved_requires_promoted_target_done(tmp_path: Path) -> None:
    _work(tmp_path, "T-0001", "task", "todo")
    _issue(tmp_path, "ISS-0002", "bug", "resolved", promoted_to="T-0001")
    assert any("done でない" in m for m in _errors(tmp_path))


def test_resolved_with_done_target_is_ok(tmp_path: Path) -> None:
    _work(tmp_path, "T-0002", "task", "done")
    _issue(tmp_path, "ISS-0003", "bug", "resolved", promoted_to="T-0002")
    assert not [m for m in _errors(tmp_path) if "ISS-0003" in m]


def test_promoted_to_missing_target_is_error(tmp_path: Path) -> None:
    _issue(tmp_path, "ISS-0004", "bug", "in-progress", promoted_to="T-9999")
    assert any("見つからない" in m for m in _errors(tmp_path))


def test_done_target_but_issue_still_open_is_error(tmp_path: Path) -> None:
    _work(tmp_path, "T-0003", "task", "done")
    _issue(tmp_path, "ISS-0005", "bug", "open", promoted_to="T-0003")
    assert any("done なのに課題が未解決" in m for m in _errors(tmp_path))


def test_wontfix_requires_reason(tmp_path: Path) -> None:
    _issue(tmp_path, "ISS-0006", "risk", "wontfix", body="やらない")
    assert any("理由" in m for m in _errors(tmp_path))
    _issue(tmp_path, "ISS-0007", "risk", "wontfix", body="## 理由\nこうだから")
    assert not [m for m in _errors(tmp_path) if "ISS-0007" in m]


def test_github_backend_has_no_local_entities(tmp_path: Path) -> None:
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "config.toml").write_text('[issues]\nbackend = "github:me/repo"\n', encoding="utf-8")
    _issue(tmp_path, "ISS-0008", "bug", "open")  # ローカルに置いても github backend では読まない
    assert issues.load_issues(tmp_path) == []
