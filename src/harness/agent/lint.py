"""エージェント宣言（docs/agents/**/*.yaml）の構造 lint（参照整合を verify で守る）。

実行しない・ネットワークも使わない。宣言の `provider` が PROVIDERS に・`tools[]` が TOOLS に実在するかを
静的に検査する（serve の deploy_lint と同じ思想＝実行できない資産の参照整合）。
`docs/agents/` が無いプロジェクトでは何も指摘しない（誤検知しない）。
依存は stdlib＋pyyaml＋agent.{providers,tools}（軽い）のみ。yaml は関数内で遅延取り込みする
（プロファイルのモジュールを軽く保つ規約）。
"""

from __future__ import annotations

from pathlib import Path

from harness import pm


def run_checks(root: Path) -> list[pm.Problem]:
    """docs/agents/**/*.yaml の宣言を検査し、指摘（error/info）を返す。root は自リポ or コピー先。"""
    import yaml

    from harness.agent.providers import PROVIDERS
    from harness.agent.tools import TOOLS

    base = root / "docs" / "agents"
    if not base.exists():
        return []  # エージェント宣言を持たないプロジェクト＝検査対象外

    problems: list[pm.Problem] = []
    for path in sorted(base.rglob("*.yaml")):
        rel = path.relative_to(root)
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(pm.Problem("error", f"{rel}: YAML として読めない（{type(exc).__name__}）"))
            continue
        if not isinstance(doc, dict):
            problems.append(pm.Problem("error", f"{rel}: AgentSpec の YAML はキー→値の辞書であること"))
            continue
        provider = doc.get("provider")
        if not isinstance(provider, str) or provider not in PROVIDERS:
            problems.append(
                pm.Problem(
                    "error",
                    f"{rel}: provider '{provider}' が PROVIDERS に無い（一覧は `uv run agent providers`）",
                )
            )
        tools = doc.get("tools")
        if tools is None:
            continue  # tools 無し（既定＝空）は無指摘
        if not isinstance(tools, list):
            problems.append(pm.Problem("error", f"{rel}: tools はツール名（str）の並びであること"))
            continue
        for tool in tools:
            if not isinstance(tool, str) or tool not in TOOLS:
                problems.append(
                    pm.Problem(
                        "error",
                        f"{rel}: tool '{tool}' が TOOLS に無い（一覧は `uv run agent tools`）",
                    )
                )
    return problems
