"""リリース戦略文書（templates/serve/README.md の Blue-Green・Canary 節）の構造検査（T-0112）。

期待値の導き方（金メッキ禁止）：受け入れ基準の構成から導く。
- Blue-Green＝「image tag 切替」・Canary＝「replicas 比率」という定義そのものから、各節が引用すべき
  最小の k8s キー（Blue-Green→`image:`・Canary→`replicas:`）が決まる。
- 節が引用する k8s キー・テンプレート内ファイルは README から抽出し、実在は `templates/serve/` の
  実体と突き合わせる（deploy_lint の参照整合の思想を文書側にも適用＝文書の腐りを検知）。
実装の出力をコピーした固定値は書かない：README 本文の引用（バッククォート表記）を動的に集めて検査する。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVE_DIR = REPO_ROOT / "templates" / "serve"
README = SERVE_DIR / "README.md"

# 節見出し（## レベル）に含まれるべき戦略名＝受け入れ基準の構成から導く。
_STRATEGIES = ("Blue-Green", "Canary")
# 各戦略の定義から導かれる、その節が必ず引用すべき k8s キー（引用が無い＝手順が抽象論になっている）。
_REQUIRED_KEY = {"Blue-Green": "image:", "Canary": "replicas:"}

# バッククォート内の YAML キー表記（例 `image:`・`spec.selector.matchLabels` は対象外＝末尾コロンのみ）。
_KEY_RE = re.compile(r"`([A-Za-z][\w.-]*:)`")
# バッククォート内の k8s ファイル参照（例 `k8s/deployment.yaml`）。
_K8S_PATH_RE = re.compile(r"`(k8s/[\w.-]+)`")


def _sections() -> dict[str, str]:
    """README を ## 見出しで区切り、戦略名を含む節の本文（見出し行含む）を返す。"""
    text = README.read_text(encoding="utf-8")
    parts = re.split(r"^(?=## )", text, flags=re.MULTILINE)
    out: dict[str, str] = {}
    for name in _STRATEGIES:
        matches = [p for p in parts if p.startswith("## ") and name in p.splitlines()[0]]
        if matches:
            out[name] = matches[0]
    return out


@pytest.mark.unit
def test_readme_has_bluegreen_and_canary_sections() -> None:
    # 受け入れ基準：Blue-Green・Canary の節見出し（##）が README に在る。
    sections = _sections()
    for name in _STRATEGIES:
        assert name in sections, f"templates/serve/README.md に {name} の節見出し（## …{name}…）が無い"
    # Canary 節は A/B（実トラフィック出し分け・外部指標収集）との境界を明記する（受け入れ基準の 1 行）。
    assert "A/B" in sections["Canary"], "Canary 節に A/B テストとの境界（やらないこと）の明記が無い"


@pytest.mark.unit
def test_readme_cites_existing_k8s_keys() -> None:
    # 各節が引用する k8s キーとファイルは templates/serve/ に実在する＝文書とテンプレの参照整合。
    sections = _sections()
    deployment = (SERVE_DIR / "k8s" / "deployment.yaml").read_text(encoding="utf-8")
    service = (SERVE_DIR / "k8s" / "service.yaml").read_text(encoding="utf-8")
    k8s_text = deployment + service

    for name in _STRATEGIES:  # 節そのものが無いときも空振りで通さない（単独でも成立する検査にする）
        assert name in sections, f"templates/serve/README.md に {name} の節が無い"
        body = sections[name]
        keys = set(_KEY_RE.findall(body))
        # 戦略の定義から導く最小の引用（無ければ手順が実在キーに紐づいていない）。
        assert _REQUIRED_KEY[name] in keys, f"{name} 節が `{_REQUIRED_KEY[name]}` を引用していない"
        for key in sorted(keys):
            assert re.search(rf"^\s*{re.escape(key)}", k8s_text, flags=re.MULTILINE), (
                f"{name} 節が引用するキー `{key}` が templates/serve/k8s/ の deployment.yaml / "
                f"service.yaml に実在しない（文書の腐り）"
            )
        for rel in sorted(set(_K8S_PATH_RE.findall(body))):
            assert (SERVE_DIR / rel).is_file(), f"{name} 節が引用する `{rel}` が templates/serve/ に実在しない"
