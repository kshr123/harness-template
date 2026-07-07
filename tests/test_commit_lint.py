"""commit_lint（コミットメッセージの作業単位 ID 検査）のテスト。

期待値は一時ディレクトリに**テスト内で構成した** work/ の木（EP-90＋T-9001/T-9002）から導出する
（test_agent_lint.py と同型・実装出力のコピー禁止）：
- 構成した木に実在する ID を含むメッセージ → 問題 0 件（ID の正本＝pm.load_tree の木だけ）。
- ID を含まないメッセージ → error 1 件（木に何も一致しないため）。
- 木に無い ID（T-9999）→ error（架空 ID は known_ids に入りようがない）。
- 免除接頭辞（Merge/Revert/fixup!/squash!）→ 検査対象外なので木と無関係に 0 件。
配線（.pre-commit-config.yaml の commit-msg フック）は test_guardrails.py の型（ポリシー定数＋
データ駆動）で常在検査する。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from harness import commit_lint

_ROOT = Path(__file__).resolve().parents[1]

# --- テスト用の work/ の木（期待値の導出元。実リポの ID と衝突しない番号帯を使う） ---

_EPIC_ID = "EP-90"
_TASK_IDS = ("T-9001", "T-9002")
_ABSENT_ID = "T-9999"  # 木に置かない＝実在しない ID の代表


def _make_tree(root: Path) -> None:
    """EP 1 つ＋T 2 つの最小の木を構成する（known_ids ＝ {EP-90, T-9001, T-9002} が導出できる）。"""
    epic = root / "work" / "EP-90-demo"
    epic.mkdir(parents=True)
    (epic / "item.md").write_text(f"---\nid: {_EPIC_ID}\nkind: epic\nstatus: in-progress\n---\n", encoding="utf-8")
    for task_id in _TASK_IDS:
        (epic / f"{task_id}-demo.md").write_text(
            f"---\nid: {task_id}\nkind: task\nstatus: todo\n---\n", encoding="utf-8"
        )


# --- 純関数（check_message）＋入口（lint_message） ---


@pytest.mark.unit
def test_message_with_existing_id_passes(tmp_path: Path) -> None:
    """構成した木に実在する ID（EP-90・T-9001）を冒頭行に含む → 問題 0 件。"""
    _make_tree(tmp_path)
    assert commit_lint.lint_message(tmp_path, f"{_EPIC_ID} {_TASK_IDS[0]}：やることの要約\n\n本文") == []


@pytest.mark.unit
def test_message_without_id_fails(tmp_path: Path) -> None:
    """ID を含まないメッセージ → error 1 件。趣旨（実在 ID を含めよ）と書式の例が案内に入る。"""
    _make_tree(tmp_path)
    problems = commit_lint.lint_message(tmp_path, "リファクタリング")
    assert len(problems) == 1
    assert problems[0].level == "error"
    assert "作業単位 ID" in problems[0].message  # 何が欠けているか
    assert "EP-20 T-0101" in problems[0].message  # 正しい書式の例
    assert "Merge" in problems[0].message  # 免除接頭辞の案内（人・エージェントが次の一手を選べる）


@pytest.mark.unit
def test_unknown_id_fails(tmp_path: Path) -> None:
    """木に無い T-9999 を含むメッセージ → error（打ち間違い・架空 ID を通さない）。"""
    _make_tree(tmp_path)
    problems = commit_lint.lint_message(tmp_path, f"{_ABSENT_ID}：架空のタスク")
    assert [p.level for p in problems] == ["error"]
    assert _ABSENT_ID in problems[0].message  # どの ID が架空かを名指しする


@pytest.mark.unit
def test_unknown_id_fails_even_next_to_existing_id(tmp_path: Path) -> None:
    """実在 ID が並んでいても、架空 ID が混ざれば error（打ち間違いが実在 ID に隠れない）。"""
    _make_tree(tmp_path)
    problems = commit_lint.lint_message(tmp_path, f"{_EPIC_ID} {_ABSENT_ID}：番号の打ち間違い")
    assert [p.level for p in problems] == ["error"]
    assert _ABSENT_ID in problems[0].message


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "Merge branch 'feature' into main",
        'Revert "EP-99 何かの取り消し"',
        "fixup! 直前コミットの修正",
        "squash! まとめる",
    ],
)
def test_exempt_prefixes_pass(tmp_path: Path, message: str) -> None:
    """ツール生成コミット（免除接頭辞）は木と無関係に 0 件（接頭辞の明示リストだけ＝fail closed）。"""
    _make_tree(tmp_path)
    assert commit_lint.lint_message(tmp_path, message) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "Merged the fix without any id",  # 手書き（git 生成でない）＝免除しない
        "Reverting things manually",  # 同上（スペース無し＝git の `Revert \"…\"` と別物）
        "Mergeイ直したので直す",  # 接頭辞に続く非スペースで単語途中に化けた手書き
    ],
)
def test_humanwritten_lookalikes_are_not_exempt(tmp_path: Path, message: str) -> None:
    """`Merged …`・`Reverting …` のような手書き文は免除に該当させない（ID 検査を素通りさせない＝迂回穴を塞ぐ）。"""
    _make_tree(tmp_path)
    problems = commit_lint.lint_message(tmp_path, message)
    assert [p.level for p in problems] == ["error"]


@pytest.mark.unit
def test_empty_message_passes(tmp_path: Path) -> None:
    """空メッセージ（コメント行だけを含む場合も）は 0 件（git 側が別途拒否する領分）。"""
    _make_tree(tmp_path)
    assert commit_lint.lint_message(tmp_path, "") == []
    assert commit_lint.lint_message(tmp_path, "\n# Please enter the commit message\n") == []


@pytest.mark.unit
def test_id_is_checked_on_first_line_only(tmp_path: Path) -> None:
    """本文（2 行目以降）だけに ID があっても error（冒頭行＝来歴の見出しに ID を置く約束）。"""
    _make_tree(tmp_path)
    problems = commit_lint.lint_message(tmp_path, f"見出しに ID が無い\n\n{_TASK_IDS[0]} は本文にだけある")
    assert [p.level for p in problems] == ["error"]


# --- 免除ポリシーの固定（coverage_lint の _EXEMPT と同型：明示リスト＋理由必須） ---

# 免除してよいのはツール生成コミットの定型接頭辞だけ。ここに 1 つ足す＝ポリシー変更なので、
# このタプルと実装の両方を同時に更新すること（黙って免除を広げる変異を赤くする）。
EXEMPT_PREFIX_POLICY: tuple[str, ...] = ("Merge ", 'Revert "', "fixup! ", "squash! ")


@pytest.mark.unit
def test_exempt_prefixes_are_the_fixed_policy() -> None:
    assert set(commit_lint._EXEMPT_PREFIXES) == set(EXEMPT_PREFIX_POLICY), (
        "免除接頭辞がポリシー（ツール生成コミットの定型だけ）とずれている。広げる場合は"
        "ポリシー変更としてこのテストの EXEMPT_PREFIX_POLICY と同時に更新すること"
    )
    for prefix, reason in commit_lint._EXEMPT_PREFIXES.items():
        assert reason.strip(), f"_EXEMPT_PREFIXES[{prefix!r}] の理由が空（免除には人が読める理由が必須）"


# --- 配線の常在検査（T-0100 の型：設定が黙って外れたら verify が落ちる） ---


@pytest.mark.unit
def test_commit_msg_hook_wired() -> None:
    """.pre-commit-config.yaml に commit-msg ステージのフックがあり、entry がこの検査を指す。"""
    config = yaml.safe_load((_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [hook for repo in config["repos"] for hook in repo["hooks"]]
    hook = next((h for h in hooks if h.get("stages") == ["commit-msg"]), None)
    assert hook is not None, (
        "commit-msg ステージのフックが .pre-commit-config.yaml に無い。コミットメッセージの"
        "作業単位 ID 検査（T-0101 の執行点）が外れている。フックを戻すこと"
    )
    assert hook["entry"].startswith("uv run commit-msg-lint"), (
        f"commit-msg フックの entry が 'uv run commit-msg-lint' でない（実際: {hook['entry']!r}）。"
        "検査の実体（harness.cli:commit_msg_lint_main）に配線すること"
    )
    # 既定では全フックが全ステージで走る（default_stages 既定＝全ステージ）。commit-msg を install すると
    # check（standard）や gitleaks がコミットごとに二重実行されるため、既存フックは pre-commit ステージに固定する。
    assert config.get("default_stages") == ["pre-commit"], (
        "default_stages が [pre-commit] でない。commit-msg install 時に既存フックが二重実行される"
    )


@pytest.mark.integration
def test_cli_entry_exit_codes(tmp_path: Path) -> None:
    """CLI 入口（git が渡すメッセージファイルのパス）：実在 ID → exit 0／ID 無し → exit 1＋案内。"""
    _make_tree(tmp_path)
    msg_file = tmp_path / "COMMIT_EDITMSG"
    code = (
        "import sys; sys.argv = ['commit-msg-lint', sys.argv[1]]; "
        "from harness.cli import commit_msg_lint_main; commit_msg_lint_main()"
    )

    msg_file.write_text(f"{_EPIC_ID} {_TASK_IDS[1]}：正しい書式", encoding="utf-8")
    ok = subprocess.run(
        [sys.executable, "-c", code, str(msg_file)], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert ok.returncode == 0, f"実在 ID のメッセージが弾かれた: {ok.stdout}{ok.stderr}"

    msg_file.write_text("IDの無いメッセージ", encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, "-c", code, str(msg_file)], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert bad.returncode == 1, "ID 無しのメッセージが通った（fail closed になっていない）"
    assert "作業単位 ID" in bad.stdout  # なぜ落ちたかを人・エージェントに案内する
