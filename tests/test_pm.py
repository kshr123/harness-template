"""PM層の中核ロジックのテスト。

生成と評価の分離：実装（pm）とは別に、期待する不変条件をテストで固定する。
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from harness import pm


def _write(path: Path, meta: dict[str, object], body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(body)
    post.metadata.update(meta)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _scaffold(root: Path) -> None:
    _write(
        root / "projects" / "demo" / "wbs.md",
        {
            "project": "demo",
            "epics": [
                {"id": "EP-01", "name": "骨格", "plan": "detailed", "status": "todo"},
                {"id": "EP-02", "name": "残り", "plan": "outline", "status": "todo"},
            ],
        },
    )
    _write(root / "tasks" / "T-0001-a.md", {"id": "T-0001", "status": "done", "epic": "EP-01"})
    _write(root / "tasks" / "T-0002-b.md", {"id": "T-0002", "status": "todo", "epic": "EP-01"})


def test_lint_accepts_outline_and_backlog(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # outline エピック（EP-02）はタスク 0 でも余白として許容。バックログも許容。
    _write(tmp_path / "tasks" / "T-0003-c.md", {"id": "T-0003", "status": "todo", "epic": "none"})
    problems = pm.lint(tmp_path)
    assert not [p for p in problems if p.level == "error"]


def test_lint_flags_true_orphan(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # 存在しないエピックを指す＝真の孤児＝赤。
    _write(tmp_path / "tasks" / "T-0009-x.md", {"id": "T-0009", "status": "todo", "epic": "EP-99"})
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert len(errors) == 1
    assert "EP-99" in errors[0].message


def test_render_status_counts_done(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    status = pm.render_status(tmp_path)
    assert "EP-01" in status
    assert "1/2" in status  # done 1 / 総数 2
    assert "余白" in status  # EP-02 は outline で未分解


def test_broken_frontmatter_is_error(tmp_path: Path) -> None:
    _scaffold(tmp_path)
    # status が不正値＝型検証で赤。
    bad: dict[str, object] = {"id": "T-0010", "status": "unknown", "epic": "EP-01"}
    _write(tmp_path / "tasks" / "T-0010-bad.md", bad)
    errors = [p for p in pm.lint(tmp_path) if p.level == "error"]
    assert errors
