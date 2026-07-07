"""CI テンプレート（templates/ci/）の構造 lint（verify ゲートの参照整合を verify で守る）。

GitHub Actions は実行しない・ネットワークも使わない。テンプレートは「利用者がコピーする雛形」なので
実行はできないが、構造（必須ファイルの存在・verify step の有無・Python 版・extras の規約）は静的に
検査できる。deploy_lint（templates/serve/ の構造 lint）と同型の「実行できない資産を verify で腐らせない」
検査（DEC-0009）。使い方の正本は docs/ops.md の「CI（verify ゲート）テンプレートと ci_lint」。

検査対象は**データ駆動**（_WORKFLOWS の表）：ワークフロー雛形を足すときは表に 1 行足すだけで
欠落検査・必須 step 検査・トリガ検査・版/extras 検査が増える（retrain.yml＝T-0114 がその 1 行）。
存在検査と内容検査は分かれる：required=False の雛形（例 retrain.yml＝CT は任意）は**不在を error に
しない**・在るときだけ内容を検査する（verify ゲートは必須・CT は opt-in という違いを表の 1 列で表す）。

検査の内訳（1 ワークフローあたり）：
- 必須ファイル（required=True）の欠落＝error（複製先がゲート無しで始まってしまう）。
- 表の required_runs（例 `uv run verify`）を run に含む step が無い＝error（ゲートの本体が抜けた雛形）。
- ordered=True の雛形では required_runs の並びが step の登場順でもあること＝error（CT の監視→昇格の
  順序が意味を持つ。並べ替えは順序違反）。ordered=False（既定・例 verify.yml）は有無だけ見る。
- 表の required_triggers（例 schedule）が on: に無い＝error（定期実行の起点が抜けた CT 雛形）。
- `python-version` がリポの正（pyproject の requires-python）と食い違う・指定が無い＝error。
  リポの正を導出できない root（pyproject が無いコピー先）では版検査を行わない（誤検知しない）。
- `uv sync` の step に `--all-extras` が無い＝error（開発・verify 環境は全部入り＝AGENTS の規約）。

`templates/ci/` が無いプロジェクト（＝テンプレートを同梱しないコピー先の案件）では何も指摘しない
（誤検知しない）。依存は stdlib＋pyyaml のみ・yaml は関数内で遅延取り込み（deploy_lint と同じ規約。
プロファイルのモジュールを軽く保つ＝DEC-0013）。
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness import pm


@dataclass(frozen=True)
class _WorkflowSpec:
    """検査するワークフロー雛形 1 つ分の要求（データ駆動の拡張点）。"""

    rel: str  # templates/ci/ からの相対パス
    required_runs: tuple[str, ...]  # いずれかの step の run に含まれるべきコマンド断片
    purpose: str  # 欠落・step 抜けの error 文で「なぜ要るか」を伝える一言
    required: bool = True  # False＝任意の雛形（不在は error にしない。在るときだけ内容を検査する）
    required_triggers: tuple[str, ...] = ()  # on: に要るトリガ名（例 "schedule"。空＝トリガ検査なし）
    ordered: bool = False  # True＝required_runs の並びが step の登場順でもあること（CT の監視→昇格の順序）


# 検査対象の表（テンプレを足すときはここに 1 行追加）。
_WORKFLOWS: tuple[_WorkflowSpec, ...] = (
    _WorkflowSpec(
        rel=".github/workflows/verify.yml",
        required_runs=("uv sync", "uv run verify"),
        purpose="PR→verify ゲート",
    ),
    _WorkflowSpec(
        rel=".github/workflows/retrain.yml",
        required_runs=("uv sync", "train.py", "uv run data monitor", "promote_model"),
        purpose="継続学習（schedule→experiment→monitor→promote）",
        required=False,  # CT は任意の雛形＝verify ゲートと違い、同梱をやめた複製先を error にしない
        required_triggers=("schedule",),  # 定期実行が CT の起点（無いと手動でしか回らない雛形になる）
        ordered=True,  # experiment→monitor→promote の順序が意味を持つ（監視してから昇格・並べ替えは error）
    ),
)

# requires-python（例 ">=3.14"）・python-version から minor までの版を取り出す。
_VERSION_RE = re.compile(r"(\d+\.\d+)")


def run_checks(root: Path) -> list[pm.Problem]:
    """templates/ci/ の構造を検査し、指摘（error/info）を返す。root は自リポ or コピー先。"""
    import yaml

    base = root / "templates" / "ci"
    if not base.exists():
        return []  # テンプレートを同梱しないコピー先の案件＝検査対象外（誤検知しない）

    problems: list[pm.Problem] = []
    repo_python = _repo_python_version(root)

    for spec in _WORKFLOWS:
        path = base / spec.rel
        if not path.is_file():
            if spec.required:
                problems.append(
                    pm.Problem(
                        "error",
                        f"templates/ci/{spec.rel}: 必須ファイルが無い（複製先が {spec.purpose} 無しで始まって"
                        "しまう。雛形を復元するか、同梱をやめるなら templates/ci/ ごと消す）",
                    )
                )
            continue  # 任意の雛形（required=False）は不在を指摘しない（在るときだけ内容を検査する）
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            # YAML 妥当性・workflow 構造の型は actionlint/check-jsonschema へ委譲（自前では報告しない）。
            # 読めない雛形はここで内容検査を諦めるだけ（他 spec の error にも波及させない）。
            continue
        _check_required_triggers(problems, spec, doc)
        _check_required_runs(problems, spec, doc)
        _check_run_order(problems, spec, doc)
        _check_uv_sync_extras(problems, spec, doc)
        _check_python_version(problems, spec, doc, repo_python)
    return problems


# --- 必須トリガ（required_triggers のトリガ名が on: に在ること） ---


def _check_required_triggers(problems: list[pm.Problem], spec: _WorkflowSpec, doc: Any) -> None:
    if not spec.required_triggers:
        return
    triggers = _trigger_names(doc)
    for name in spec.required_triggers:
        if name not in triggers:
            problems.append(
                pm.Problem(
                    "error",
                    f"templates/ci/{spec.rel}: `{name}` トリガ（on:）が無い（{spec.purpose} の起点が抜けた"
                    f"雛形。on: に {name} を戻す）",
                )
            )


# --- 必須 step（required_runs のコマンド断片を run に含む step が在ること） ---


def _check_required_runs(problems: list[pm.Problem], spec: _WorkflowSpec, doc: Any) -> None:
    runs = _run_commands(doc)
    for fragment in spec.required_runs:
        if not any(fragment in run for run in runs):
            problems.append(
                pm.Problem(
                    "error",
                    f"templates/ci/{spec.rel}: `{fragment}` を実行する step が無い（{spec.purpose} の本体が"
                    f"抜けた雛形。run に `{fragment}` を持つ step を戻す）",
                )
            )


# --- step の順序（ordered=True のとき required_runs の並び＝step の登場順であること） ---


def _check_run_order(problems: list[pm.Problem], spec: _WorkflowSpec, doc: Any) -> None:
    if not spec.ordered:
        return  # 有無だけ見る雛形（既定・例 verify.yml）は順序を問わない
    runs = _run_commands(doc)
    # 各 fragment が最初に現れる step の index（不在は None＝required_runs 検査が別途 error にする）。
    first: list[tuple[str, int]] = []
    for fragment in spec.required_runs:
        idx = next((i for i, run in enumerate(runs) if fragment in run), None)
        if idx is not None:
            first.append((fragment, idx))
    # 隣り合う fragment の登場順が逆転していたら順序違反（監視→昇格の順序が意味を持つ）。
    for (prev_frag, prev_idx), (frag, idx) in zip(first, first[1:], strict=False):
        if idx < prev_idx:
            problems.append(
                pm.Problem(
                    "error",
                    f"templates/ci/{spec.rel}: step の順序が違う（`{prev_frag}` より前に `{frag}` が来ている。"
                    f"{spec.purpose} は表の並び順で実行する必要がある＝run を並べ直す）",
                )
            )
            return  # 最初の逆転 1 件だけ報告（壊れた並びを名指しできれば十分・多重報告しない）


# --- uv sync の extras（開発・verify 環境は全部入り＝AGENTS の規約） ---


def _check_uv_sync_extras(problems: list[pm.Problem], spec: _WorkflowSpec, doc: Any) -> None:
    for run in _run_commands(doc):
        for line in run.splitlines():
            if "uv sync" in line and "--all-extras" not in line:
                problems.append(
                    pm.Problem(
                        "error",
                        f"templates/ci/{spec.rel}: uv sync に --all-extras が無い（optional 依存のテストが "
                        f"skip され verify 環境の規約＝全部入りに反する）: {line.strip()}",
                    )
                )


# --- Python 版の整合（雛形の python-version ＝ リポの正＝pyproject の requires-python） ---


def _check_python_version(problems: list[pm.Problem], spec: _WorkflowSpec, doc: Any, repo_python: str | None) -> None:
    if repo_python is None:
        return  # リポの正を導出できない（pyproject が無い等）＝版検査を行わない（誤検知しない）
    versions = _python_versions(doc)
    if not versions:
        problems.append(
            pm.Problem(
                "error",
                f"templates/ci/{spec.rel}: python-version の指定が無い（CI の版がリポの正＝{repo_python} と"
                "ずれても気づけない。uv セットアップ step の with に python-version を書く）",
            )
        )
        return
    for version in versions:
        if version != repo_python and not version.startswith(f"{repo_python}."):
            problems.append(
                pm.Problem(
                    "error",
                    f"templates/ci/{spec.rel}: python-version {version} がリポの正（pyproject の "
                    f"requires-python＝{repo_python}）と食い違う（CI とローカルで別の版を検証してしまう。"
                    "どちらかへ揃える）",
                )
            )


def _repo_python_version(root: Path) -> str | None:
    """リポの正の Python 版（pyproject の requires-python から minor まで）。導出できなければ None。"""
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return None  # pyproject の健全性は本 lint の関心外（ここでは版検査を諦めるだけ）
    spec = data.get("project", {}).get("requires-python", "")
    m = _VERSION_RE.search(str(spec))
    return m.group(1) if m else None


# --- ワークフロー YAML 構造の取り出し（欠けても落ちない：常に空を返す＝deploy_lint と同じ流儀） ---


def _steps(doc: Any) -> list[dict[str, Any]]:
    """全 job の全 step。構造が想定と違っても落ちない（欠けは他の検査が指摘する）。"""
    jobs = doc.get("jobs") if isinstance(doc, dict) else None
    if not isinstance(jobs, dict):
        return []
    out: list[dict[str, Any]] = []
    for job in jobs.values():
        steps = job.get("steps") if isinstance(job, dict) else None
        if isinstance(steps, list):
            out.extend(step for step in steps if isinstance(step, dict))
    return out


def _run_commands(doc: Any) -> list[str]:
    """全 step の run 文字列（コメントは YAML パースで落ちる＝run の実体だけを見る）。"""
    return [step["run"] for step in _steps(doc) if isinstance(step.get("run"), str)]


def _trigger_names(doc: Any) -> set[str]:
    """on: のトリガ名の集合。pyyaml は `on` キーを YAML 1.1 の真偽値 True に読むので両方の鍵を見る。"""
    if not isinstance(doc, dict):
        return set()
    on = doc.get("on", doc.get(True))
    if isinstance(on, dict):
        return {str(k) for k in on}
    if isinstance(on, list):
        return {str(v) for v in on}
    if isinstance(on, str):
        return {on}
    return set()


def _python_versions(doc: Any) -> list[str]:
    """全 step の with.python-version（文字列化。unquoted 3.10→"3.1" の YAML 事故もそのまま照合に出す）。"""
    out: list[str] = []
    for step in _steps(doc):
        with_ = step.get("with")
        if isinstance(with_, dict) and "python-version" in with_:
            out.append(str(with_["python-version"]))
    return out
