"""ci_lint（CI テンプレート templates/ci/ の構造 lint）のテスト。

期待値の導き方：自リポの実テンプレート（templates/ci/）を「生きた fixture」として tmp_path にコピーし、
既知の 1 箇所（verify step・python-version・--all-extras）を意図的に壊す→壊した箇所が名指しで error に
なることを確かめる（変異ガード。deploy_lint のテストと同型）。error の件数・文言は「何を壊したか」の
構成から導く（実装の出力をコピーした固定値ではない＝ハードコード期待値禁止）。
GitHub Actions もネットワークも使わない（実行しない・構造検査のみ）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harness.ops import ci_lint

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates" / "ci"
WORKFLOW = ".github/workflows/verify.yml"
RETRAIN = ".github/workflows/retrain.yml"

# リポの正（pyproject の requires-python ">=3.14"）と同じ版を持つ最小 pyproject。
# 版の期待値はこの構成（3.14 と書いたこと）から導く。
_PYPROJECT = '[project]\nname = "copy-dest"\nversion = "0.1.0"\nrequires-python = ">=3.14"\n'


def _copy_templates(tmp_path: Path, *, with_pyproject: bool = True) -> Path:
    """実テンプレート一式＋最小 pyproject を一時プロジェクトへ置き、その root を返す。

    templates/experiment/ も一緒に置く：retrain.yml は train.py をそこから参照する（スクリプト参照の
    実在検査の対象）ので、置かないと他の観点のテストまで参照エラーで落ちてしまう。
    """
    shutil.copytree(TEMPLATES, tmp_path / "templates" / "ci")
    shutil.copytree(REPO_ROOT / "templates" / "experiment", tmp_path / "templates" / "experiment")
    if with_pyproject:
        (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    return tmp_path


def _mutate(root: Path, old: str, new: str, rel: str = WORKFLOW) -> None:
    """ワークフロー雛形の 1 箇所を置換して壊す。old が無い＝fixture の前提が崩れているので失敗にする。"""
    path = root / "templates" / "ci" / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture の前提が崩れている: {rel} に {old!r} が無い"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in ci_lint.run_checks(root) if p.level == "error"]


# --- 入口の分岐（テンプレートの有無） ---


@pytest.mark.unit
def test_no_templates_ci_no_problems(tmp_path: Path) -> None:
    # templates/ci/ が無い＝テンプレートを同梱しないコピー先の案件。誤検知しない（指摘 0 件）。
    assert ci_lint.run_checks(tmp_path) == []


@pytest.mark.integration
def test_repo_template_passes() -> None:
    # 自リポの出荷テンプレートは 0 件で通る＝「生きた fixture」（verify のたびに陳腐化を検知する回帰テスト）。
    assert ci_lint.run_checks(REPO_ROOT) == []


# --- 必須ファイル ---


@pytest.mark.unit
def test_missing_workflow_file_flagged(tmp_path: Path) -> None:
    # templates/ci/ は在るが verify.yml が無い＝複製先がゲート無しで始まる構成→名指しの error。
    (tmp_path / "templates" / "ci").mkdir(parents=True)
    errors = _errors(tmp_path)
    assert any(WORKFLOW in m for m in errors)


# --- verify step（ゲートの本体） ---


@pytest.mark.unit
def test_missing_verify_step_flagged(tmp_path: Path) -> None:
    # verify step を意図的に抜く（run を無関係なコマンドへ置換）→壊したのは 1 箇所なので error は 1 件。
    root = _copy_templates(tmp_path)
    _mutate(root, "uv run verify", "echo done")
    errors = _errors(root)
    assert len(errors) == 1
    assert "uv run verify" in errors[0]


# --- Python 版の整合（雛形＝リポの正） ---


@pytest.mark.unit
def test_python_version_mismatch_flagged(tmp_path: Path) -> None:
    # 雛形の版だけを 3.13 へずらす（pyproject は 3.14 のまま）→両方の版を名指しで error 1 件。
    root = _copy_templates(tmp_path)
    _mutate(root, 'python-version: "3.14"', 'python-version: "3.13"')
    errors = _errors(root)
    assert len(errors) == 1
    assert "3.13" in errors[0] and "3.14" in errors[0]


@pytest.mark.unit
def test_unpinned_python_version_flagged(tmp_path: Path) -> None:
    # python-version の指定そのものを消す（別の with キーへ置換）→版の乖離を検査できない構成＝error。
    root = _copy_templates(tmp_path)
    _mutate(root, 'python-version: "3.14"', "enable-cache: true")
    errors = _errors(root)
    assert any("python-version" in m for m in errors)


@pytest.mark.unit
def test_without_pyproject_version_check_skipped(tmp_path: Path) -> None:
    # コピー先に pyproject が無い＝リポの正を導出できない→版検査は行わない（誤検知しない）。他は満たすので 0 件。
    _copy_templates(tmp_path, with_pyproject=False)
    assert ci_lint.run_checks(tmp_path) == []


# --- uv sync の extras（verify 環境は全部入り＝AGENTS の規約） ---


@pytest.mark.unit
def test_missing_all_extras_flagged(tmp_path: Path) -> None:
    # uv sync から --all-extras だけを外す（step 自体は残す）→規約違反の 1 箇所＝error 1 件。
    root = _copy_templates(tmp_path)
    _mutate(root, "uv sync --all-extras", "uv sync")
    errors = _errors(root)
    assert len(errors) == 1
    assert "--all-extras" in errors[0]


# --- 継続学習（CT）雛形 retrain.yml（任意テンプレ＝在れば内容を検査・無くても error にしない） ---


@pytest.mark.unit
def test_retrain_template_missing_promote_step_flagged(tmp_path: Path) -> None:
    # promote step（既存 promote_model の呼び出し）だけを意図的に潰す→壊したのは 1 箇所なので error は 1 件。
    root = _copy_templates(tmp_path)
    _mutate(root, "promote_model", "echo_no_gate", rel=RETRAIN)
    errors = _errors(root)
    assert len(errors) == 1
    assert "promote_model" in errors[0] and "retrain.yml" in errors[0]


@pytest.mark.unit
def test_retrain_template_missing_schedule_flagged(tmp_path: Path) -> None:
    # schedule トリガだけを別名へ潰す（step は全部残す）→定期実行の起点が抜けた構成＝error 1 件。
    root = _copy_templates(tmp_path)
    _mutate(root, "schedule:", "not-a-trigger:", rel=RETRAIN)
    errors = _errors(root)
    assert len(errors) == 1
    assert "schedule" in errors[0] and "retrain.yml" in errors[0]


@pytest.mark.unit
def test_no_retrain_template_is_ok(tmp_path: Path) -> None:
    # retrain.yml を置かない構成（CT は任意の雛形＝verify.yml と違い必須にしない）→誤検知しない（指摘 0 件）。
    root = _copy_templates(tmp_path)
    (root / "templates" / "ci" / RETRAIN).unlink()
    assert ci_lint.run_checks(root) == []


@pytest.mark.unit
def test_retrain_template_out_of_order_steps_flagged(tmp_path: Path) -> None:
    # monitor↔promote を入れ替える（両 step は残す＝有無だけ見る検査は通る）→CT の順序（監視してから昇格）
    # が崩れた構成＝順序検査だけが error 1 件。壊したのは並びの 1 箇所なので error はちょうど 1 件。
    root = _copy_templates(tmp_path)
    path = root / "templates" / "ci" / RETRAIN
    lines = path.read_text(encoding="utf-8").split("\n")
    # monitor step の 2 行（`- name:` ＋ その run 行）を切り出し、末尾（promote step の後ろ）へ移す
    # ＝両 step は残るが登場順で monitor が promote より後になる（有無検査は通し、順序検査だけ落とす）。
    start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("- name: ドリフト確認"))
    assert lines[start + 1].strip().startswith("run: uv run data monitor"), "fixture の前提: monitor step は 2 行"
    block = lines[start : start + 2]
    rest = lines[:start] + lines[start + 2 :]
    path.write_text("\n".join(rest).rstrip("\n") + "\n" + "\n".join(block) + "\n", encoding="utf-8")
    errors = _errors(root)
    assert len(errors) == 1
    assert "promote_model" in errors[0] and "uv run data monitor" in errors[0] and "順" in errors[0]


@pytest.mark.integration
def test_repo_retrain_template_passes() -> None:
    # 自リポ同梱の retrain.yml が表（_WORKFLOWS）に載っていて（検査対象で空振りでない）、0 件で通る（陳腐化番人）。
    assert RETRAIN in {spec.rel for spec in ci_lint._WORKFLOWS}
    assert (TEMPLATES / RETRAIN).is_file()
    assert ci_lint.run_checks(REPO_ROOT) == []


# --- スクリプト参照の実在（run が参照する .py がリポジトリ内に実在すること） ---


@pytest.mark.unit
def test_missing_script_reference_flagged(tmp_path: Path) -> None:
    # 実在しない .py への参照を run に追記する→参照エラーが名指しで error 1 件。
    root = _copy_templates(tmp_path)
    _mutate(root, "uv run verify", "uv run verify && uv run python scripts/does_not_exist.py")
    errors = _errors(root)
    assert len(errors) == 1
    assert "scripts/does_not_exist.py" in errors[0] and WORKFLOW in errors[0]


@pytest.mark.unit
def test_yaml_extension_workflow_is_scanned(tmp_path: Path) -> None:
    # GitHub Actions は .yml と .yaml の両方を読む。.yaml の雛形も同じ検査を受ける（拡張子で抜けない）。
    root = _copy_templates(tmp_path)
    workflows = root / "templates" / "ci" / ".github" / "workflows"
    (workflows / "extra.yaml").write_text(
        "on: {push: {}}\njobs:\n  j:\n    steps:\n      - run: uv run python scripts/absent.py\n",
        encoding="utf-8",
    )
    errors = _errors(root)
    assert len(errors) == 1
    assert "scripts/absent.py" in errors[0] and "extra.yaml" in errors[0]


@pytest.mark.unit
def test_existing_script_reference_not_flagged(tmp_path: Path) -> None:
    # 実在するスクリプトへの参照は指摘しない（誤検知しない）。templates/experiment/train.py は fixture が置く。
    root = _copy_templates(tmp_path)
    _mutate(root, "uv run verify", "uv run verify && uv run python templates/experiment/train.py --test")
    assert _errors(root) == []


@pytest.mark.unit
def test_placeholder_script_reference_not_flagged(tmp_path: Path) -> None:
    # $VAR・<...> のようなプレースホルダは対象外（保守的な抽出。誤検知しない）。
    root = _copy_templates(tmp_path)
    _mutate(root, "uv run verify", "uv run verify && uv run python $SCRIPT_PATH.py <path/to/script>.py")
    assert _errors(root) == []


# --- 壊れた YAML（妥当性は actionlint/check-jsonschema へ委譲・自前では報告しない） ---


@pytest.mark.unit
def test_broken_yaml_does_not_crash_and_is_not_self_reported(tmp_path: Path) -> None:
    # YAML 妥当性の自前検査は削った（：actionlint/check-jsonschema が同じ壊し方を RED にする）。
    # 壊れた YAML でもクラッシュしない（run_checks が例外を投げたらこのテスト自体が失敗する）ことと、
    # 「YAML として読めない」という自己申告 error がもう出ないことを確かめる。
    root = _copy_templates(tmp_path)
    (root / "templates" / "ci" / WORKFLOW).write_text("jobs: [unclosed\n", encoding="utf-8")
    errors = _errors(root)
    assert not any("YAML" in m for m in errors)
