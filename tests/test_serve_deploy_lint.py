"""deploy_lint（配信テンプレート templates/serve/ の構造 lint）のテスト。

期待値の導き方：自リポの実テンプレートを「生きた fixture」として tmp_path にコピーし、
既知の値（port 8000・image・namespace・selector・--extra serve・env 名）を 1 箇所だけ壊す。
壊した値と壊した先のファイル名が名指しで error になることを確かめる（変異ガード）。
数値・名前はテンプレートの構成から導く（実装の出力をコピーした固定値ではない）。
Docker build・kubectl・ネットワークは使わない（構造検査のみ）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harness.serve import deploy_lint

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates" / "serve"


def _copy_templates(tmp_path: Path) -> Path:
    """実テンプレート一式を一時プロジェクトへコピーし、その root を返す。"""
    shutil.copytree(TEMPLATES, tmp_path / "templates" / "serve")
    return tmp_path


def _mutate(root: Path, rel: str, old: str, new: str) -> None:
    """テンプレートの 1 箇所を置換して壊す。old が無い＝fixture の前提が崩れているので失敗にする。"""
    path = root / "templates" / "serve" / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture の前提が崩れている: {rel} に {old!r} が無い"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _errors(root: Path) -> list[str]:
    return [p.message for p in deploy_lint.run_checks(root) if p.level == "error"]


# --- 入口の分岐（テンプレートの有無） ---


@pytest.mark.unit
def test_no_templates_dir_yields_no_problems(tmp_path: Path) -> None:
    # templates/serve/ が無い＝コピーして使う先の案件。何も指摘しない（誤検知しない）。
    assert deploy_lint.run_checks(tmp_path) == []


@pytest.mark.integration
def test_real_repo_templates_pass_clean() -> None:
    # 自リポの出荷テンプレートは 0 件で通る＝「生きた fixture」（verify のたびに陳腐化を検知する回帰の番人）。
    assert deploy_lint.run_checks(REPO_ROOT) == []


# --- 必須ファイル ---


@pytest.mark.unit
def test_missing_required_file_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    (root / "templates" / "serve" / "k8s" / "service.yaml").unlink()
    assert any("k8s/service.yaml" in m and "必須" in m for m in _errors(root))


# --- port 一貫（EXPOSE＝ENTRYPOINT --port＝compose ports＝containerPort＝targetPort） ---


@pytest.mark.unit
def test_missing_expose_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "Dockerfile.serve", "EXPOSE 8000", "# EXPOSE を消した")
    assert any("Dockerfile.serve" in m and "EXPOSE" in m for m in _errors(root))


@pytest.mark.unit
def test_entrypoint_port_mismatch_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "Dockerfile.serve", "--port 8000", "--port 8001")
    errors = _errors(root)
    assert any("Dockerfile.serve" in m and "8001" in m and "8000" in m for m in errors)


@pytest.mark.unit
def test_compose_container_port_mismatch_is_error(tmp_path: Path) -> None:
    # ports "H:C" のコンテナ側（C）を壊す。ホスト側は自由（比べるのはコンテナ側だけ）。
    root = _copy_templates(tmp_path)
    _mutate(root, "docker-compose.serve.yml", '"8000:8000"', '"8000:8080"')
    errors = _errors(root)
    assert any("docker-compose.serve.yml" in m and "8080" in m and "8000" in m for m in errors)


@pytest.mark.unit
def test_deployment_container_port_mismatch_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "k8s/deployment.yaml", "containerPort: 8000", "containerPort: 8080")
    errors = _errors(root)
    assert any("deployment.yaml" in m and "8080" in m and "8000" in m for m in errors)


@pytest.mark.unit
def test_service_target_port_mismatch_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "k8s/service.yaml", "targetPort: 8000", "targetPort: 8080")
    errors = _errors(root)
    assert any("service.yaml" in m and "8080" in m and "8000" in m for m in errors)


# --- image 名一貫（compose の model-in-image ＝ deployment） ---


@pytest.mark.unit
def test_image_mismatch_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "k8s/deployment.yaml", "image: harness-serve:model-in-image", "image: other-image:latest")
    errors = _errors(root)
    assert any(
        "deployment.yaml" in m and "other-image:latest" in m and "harness-serve:model-in-image" in m for m in errors
    )


@pytest.mark.unit
def test_compose_without_model_in_image_target_is_error(tmp_path: Path) -> None:
    # deployment と突き合わせる基準（model-in-image のサービス）が無い＝error。
    root = _copy_templates(tmp_path)
    _mutate(root, "docker-compose.serve.yml", "target: model-in-image", "target: something-else")
    assert any("model-in-image" in m for m in _errors(root))


# --- namespace 一貫（namespace.yaml ＝ deployment ＝ service） ---


@pytest.mark.unit
def test_namespace_mismatch_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "k8s/service.yaml", "namespace: harness-serve", "namespace: other-ns")
    errors = _errors(root)
    assert any("service.yaml" in m and "other-ns" in m and "harness-serve" in m for m in errors)


# --- selector 整合（deployment matchLabels⊆template labels・service selector⊆template labels） ---


@pytest.mark.unit
def test_service_selector_mismatch_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "k8s/service.yaml", "app: harness-serve", "app: other-app")
    errors = _errors(root)
    assert any("service.yaml" in m and "other-app" in m for m in errors)


@pytest.mark.unit
def test_deployment_match_labels_mismatch_is_error(tmp_path: Path) -> None:
    # matchLabels だけを壊す（template labels は据え置き）＝selector が Pod を選べない構成。
    root = _copy_templates(tmp_path)
    _mutate(
        root,
        "k8s/deployment.yaml",
        "matchLabels:\n      app: harness-serve",
        "matchLabels:\n      app: other-app",
    )
    errors = _errors(root)
    assert any("deployment.yaml" in m and "other-app" in m for m in errors)


# --- uv sync に --extra serve ---


@pytest.mark.unit
def test_uv_sync_without_extra_serve_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "Dockerfile.serve", " --extra serve", "")
    assert any("Dockerfile.serve" in m and "--extra serve" in m for m in _errors(root))


# --- env SERVE_WORK / SERVE_NAME の三者一致（Dockerfile ENTRYPOINT・compose・deployment） ---


@pytest.mark.unit
def test_entrypoint_missing_env_reference_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "Dockerfile.serve", "$SERVE_NAME", "$OTHER_NAME")
    errors = _errors(root)
    assert any("Dockerfile.serve" in m and "SERVE_NAME" in m for m in errors)


@pytest.mark.unit
def test_compose_missing_env_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "docker-compose.serve.yml", "SERVE_WORK:", "OTHER_WORK:")
    errors = _errors(root)
    assert any("docker-compose.serve.yml" in m and "SERVE_WORK" in m for m in errors)


@pytest.mark.unit
def test_deployment_missing_env_is_error(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    _mutate(root, "k8s/deployment.yaml", "name: SERVE_WORK", "name: OTHER_WORK")
    errors = _errors(root)
    assert any("deployment.yaml" in m and "SERVE_WORK" in m for m in errors)


# --- 壊れた YAML ---


@pytest.mark.unit
def test_broken_yaml_is_error_not_crash(tmp_path: Path) -> None:
    root = _copy_templates(tmp_path)
    (root / "templates" / "serve" / "k8s" / "service.yaml").write_text("kind: [unclosed\n", encoding="utf-8")
    assert any("service.yaml" in m for m in _errors(root))
