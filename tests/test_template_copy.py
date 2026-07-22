"""fork（複製）と還流の正本が壊れていないことを守る回帰テスト。

対象は本体領域の実ファイル（`docs/template-copy.md`・`.github/workflows/ci.yaml`）で、複製後も残る
（可変領域ではない）。ここが黙って消える／退行すると「案件を重ねるほど強くなる」の前提（配れる・戻せる）が
崩れるので、要点の存在を機械的に固定する。test_purpose.py と同じ作法（正本テキスト・構造の存在確認）。

期待値は「この設計が要求する不変量」から書く（実装の出力の写経ではない）：境界がファイルレベルで排他で
あること・複製シミュレーションの検出器が CI に居ること・還流の判断者と単位が決まっていること。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_COPY = REPO_ROOT / "docs" / "template-copy.md"
CI_YAML = REPO_ROOT / ".github" / "workflows" / "ci.yaml"


@pytest.mark.unit
def test_template_copy_defines_ownership_boundary() -> None:
    # T-0193：本体領域と案件領域をファイルレベルで排他に定義していること（merge を機械化する前提）。
    text = TEMPLATE_COPY.read_text(encoding="utf-8")
    assert "本体領域" in text and "案件領域" in text
    # 排他の芯：本体領域の代表（src/harness/）と案件領域の代表（work/）が両方名指しされている。
    assert "src/harness/" in text and "work/" in text
    # fork＝git clone であること・upstream で派生元を指すこと（版記録ファイルを作らない設計）。
    assert "fork" in text and "upstream" in text


@pytest.mark.unit
def test_template_copy_defines_reflux_procedure() -> None:
    # T-0196：還流（案件→本体）の単位・判断者・基準が決まっていること。
    text = TEMPLATE_COPY.read_text(encoding="utf-8")
    assert "還流" in text
    # 単位＝本体領域だけに触る 1 コミット（cherry-pick / PR）。
    assert "cherry-pick" in text
    # 判断者＝テンプレート側の独立レビュー、かつ回数基準を使わない（一般性で判断）。
    assert "独立レビュー" in text
    assert "回数" in text  # 「回数で待たない／回数基準は使わない」を明記していること


@pytest.mark.unit
def test_ci_has_clone_simulation_detector() -> None:
    # T-0195：複製シミュレーションの検出器が CI に 1 本あること。init-project → uv sync → verify が緑、を回す。
    text = CI_YAML.read_text(encoding="utf-8")
    assert "clone-simulation" in text
    assert "uv run init-project" in text
    assert "uv sync" in text
    assert "uv run verify" in text


# --- fork 後の upstream merge が案件領域を汚染しないこと（EP-42・保証 (b)。実際に git を回して再生する） ---


def _extract_merge_recipe() -> str:
    """template-copy.md 4 節の merge 復旧レシピ（``` ブロック）を抜き出す。

    テストは自前のコピーでなく **doc の手順そのもの** を実行する＝正本は 1 つ（doc を直せばテストが従う）。
    """
    blocks = TEMPLATE_COPY.read_text(encoding="utf-8").split("```")
    recipes = [b for i, b in enumerate(blocks) if i % 2 == 1 and "git merge --no-commit" in b]
    assert len(recipes) == 1, f"merge レシピの ``` ブロックが 1 つでない（{len(recipes)} 個）"
    return recipes[0]


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return proc.stdout


def _run_recipe(fork: Path) -> subprocess.CompletedProcess[str]:
    # レシピは素の git を叩くので、fork に identity をローカル設定してから走らせる（CI runner は未設定）。
    _git(fork, "config", "user.email", "t@t")
    _git(fork, "config", "user.name", "t")
    return subprocess.run(
        ["sh", "-c", _extract_merge_recipe()], cwd=fork, capture_output=True, text=True, encoding="utf-8", check=True
    )


def _make_upstream(up: Path) -> None:
    """本体（テンプレート）v1：自分の開発履歴として案件領域（work・issues・requirements）も持つ＋本体コード＋共有ファイル。"""
    up.mkdir()
    _git(up, "init", "-q", "-b", "main")
    for rel, body in {
        "work/EP-01/item.md": "id: EP-01\n",
        "issues/ISS-0001-x.md": "ISS-0001\n",
        "docs/requirements/REQ-001.md": "REQ-001\n",
        "src/harness/core.py": "core v1\n",
        "pyproject.toml": "[project]\nname='h'\ndependencies=[]\n",
    }.items():
        p = up / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "template v1")


def _fork_and_scrub(tmp_path: Path, up: Path) -> Path:
    """案件（fork）：clone → upstream 化 → 案件領域を白紙化（init-project 相当）→ 案件自身の EP-50。"""
    fork = tmp_path / "fork"
    _git(tmp_path, "clone", "-q", str(up), str(fork))
    _git(fork, "remote", "rename", "origin", "upstream")
    _git(fork, "rm", "-qr", "work", "issues", "docs/requirements")
    (fork / "work" / "EP-50").mkdir(parents=True)
    (fork / "work" / "EP-50" / "item.md").write_text("id: EP-50\n", encoding="utf-8")
    _git(fork, "add", "-A")
    _git(fork, "commit", "-qm", "init-project + EP-50")
    return fork


@pytest.mark.integration
def test_upstream_merge_keeps_case_area_ours(tmp_path: Path) -> None:
    """本体（upstream）が前進したあと案件（fork）が merge しても、案件領域は fork 側のまま・本体改良だけ入る。

    素の `git merge upstream/main` は本体側の作業単位（work 配下・issues 配下）を案件へ黙って持ち込み、
    案件が白紙化で消した単位を本体が変更していれば modify/delete で復活する。template-copy.md 4 節の復旧レシピ
    （案件領域を fork=HEAD の版へ統一）が、この汚染を消しつつ本体領域の改良は取り込むことを実測で固定する。
    """
    _make_upstream(up := tmp_path / "up")
    fork = _fork_and_scrub(tmp_path, up)

    # 本体 v2：新単位 EP-99 追加・EP-01 修正・issues 追加・本体コード改良（案件が欲しいのはこれだけ）。
    (up / "work" / "EP-99").mkdir(parents=True)
    (up / "work" / "EP-99" / "item.md").write_text("id: EP-99\n", encoding="utf-8")
    (up / "work" / "EP-01" / "item.md").write_text("id: EP-01 updated\n", encoding="utf-8")
    (up / "issues" / "ISS-0002-y.md").write_text("ISS-0002\n", encoding="utf-8")
    (up / "src" / "harness" / "core.py").write_text("core v2\n", encoding="utf-8")
    _git(up, "add", "-A")
    _git(up, "commit", "-qm", "template v2")

    _git(fork, "fetch", "-q", "upstream")
    _run_recipe(fork)

    # 案件領域は fork 側のまま（本体の作業単位は入らない・消した単位は復活しない）。
    assert [p.name for p in (fork / "work").iterdir()] == ["EP-50"]
    assert not (fork / "work" / "EP-99").exists()
    assert not (fork / "work" / "EP-01").exists()
    assert not (fork / "issues").exists() or list((fork / "issues").glob("ISS-*")) == []
    # 本体領域の改良は取り込めている。
    assert (fork / "src" / "harness" / "core.py").read_text(encoding="utf-8") == "core v2\n"
    # 作業ツリーはクリーン（レシピが未追跡の混入も残さない）。
    assert _git(fork, "status", "--porcelain").strip() == ""


@pytest.mark.integration
def test_merge_recipe_does_not_commit_shared_file_conflict(tmp_path: Path) -> None:
    """共有ファイル（pyproject.toml）の競合は自動コミットせず人へ残す（競合マーカーを黙って commit しない）。"""
    _make_upstream(up := tmp_path / "up")
    fork = _fork_and_scrub(tmp_path, up)
    # 案件と本体が同じ行を別々に変更＝2 節が「起きうる」と明言する唯一の競合。
    (fork / "pyproject.toml").write_text("[project]\nname='h'\ndependencies=['fork-extra']\n", encoding="utf-8")
    _git(fork, "commit", "-qam", "案件が extra を足す")
    (up / "pyproject.toml").write_text("[project]\nname='h'\ndependencies=['upstream-dep']\n", encoding="utf-8")
    _git(up, "commit", "-qam", "本体が依存を更新")

    _git(fork, "fetch", "-q", "upstream")
    _run_recipe(fork)

    # レシピは competing な pyproject を「解決済み」として commit しない：未解決のまま人へ残す。
    assert _git(fork, "ls-files", "-u", "--", "pyproject.toml").strip() != ""
    assert "<<<<<<<" not in _git(fork, "show", "HEAD:pyproject.toml")  # HEAD にマーカー入りが入っていない


@pytest.mark.unit
def test_merge_recipe_areas_cover_case_area_roots() -> None:
    """doc の AREAS が案件領域の根の正本（init_project.CASE_AREA_ROOTS）を漏れなく覆うこと。

    required は手書きコピーでなく `init_project.py` の定数から導く＝正本 1 つ。ズレると、本体が fork 後に積んだ
    案件領域ファイルを merge レシピが掃除し損ねる（今回訂正したのと同型の穴）。scrub 側が定数を覆うことは
    tests/test_init_project.py が別途検査する（doc AREAS ⊇ 定数 ⊇ scrub の 2 段で drift を捕まえる）。
    """
    from harness import init_project

    recipe = _extract_merge_recipe()
    areas_line = next(ln for ln in recipe.splitlines() if ln.strip().startswith("AREAS="))
    areas = set(areas_line.split("=", 1)[1].strip().strip('"').split())
    required = set(init_project.CASE_AREA_ROOTS)
    assert required <= areas, f"AREAS が案件領域の根を覆っていない: 欠け={required - areas}"
