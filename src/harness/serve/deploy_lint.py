"""配信テンプレート（templates/serve/）の構造 lint（参照整合を verify で守る）。

Docker build も kubectl も実行しない・ネットワークも使わない。テンプレートは「利用者がコピーする雛形」
なので実行はできないが、Dockerfile／compose／k8s の間の**参照整合**（同じポート・同じ image・同じ
namespace・selector が Pod を選べる・uv sync に配信 extra・env 名の三者一致）だけは静的に検査できる。
E-0001 を e2e が叩いて「腐らせない」のと同じ思想の、実行できない資産版（DEC-0009）。

`templates/serve/` が無いプロジェクト（＝コピーして使う先の案件）では何も指摘しない（誤検知しない）。
依存は stdlib＋pyyaml のみ（serve extra 無しでも verify で走る）。yaml は関数内で遅延取り込みする
（プロファイルのモジュールを軽く保つ規約）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from harness import pm

# 必須ファイル（templates/serve/ からの相対）。1 つでも欠けると参照の突き合わせが成り立たない。
_REQUIRED = (
    "README.md",
    "Dockerfile.serve",
    "docker-compose.serve.yml",
    "k8s/namespace.yaml",
    "k8s/deployment.yaml",
    "k8s/service.yaml",
)

# Dockerfile ENTRYPOINT・compose・deployment の三者が必ず参照する配信モデルの env。
_REQUIRED_ENV = ("SERVE_WORK", "SERVE_NAME")

# deployment のイメージと突き合わせる compose サービスの build ターゲット（配布形＝モデル同梱）。
_MODEL_IN_IMAGE = "model-in-image"


def run_checks(root: Path) -> list[pm.Problem]:
    """templates/serve/ の参照整合を検査し、指摘（error/info）を返す。root は自リポ or コピー先。"""
    import yaml

    base = root / "templates" / "serve"
    if not base.exists():
        return []  # コピーして使う先の案件（テンプレートを同梱しない）＝検査対象外

    problems: list[pm.Problem] = []

    # --- 必須ファイル存在 ---
    present = {rel: (base / rel).is_file() for rel in _REQUIRED}
    for rel in _REQUIRED:
        if not present[rel]:
            problems.append(pm.Problem("error", f"templates/serve/{rel}: 必須ファイルが無い"))

    def _text(rel: str) -> str | None:
        return (base / rel).read_text(encoding="utf-8") if present.get(rel) else None

    def _yaml(rel: str) -> Any:
        if not present.get(rel):
            return None
        try:
            return yaml.safe_load((base / rel).read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(pm.Problem("error", f"templates/serve/{rel}: YAML として読めない（{type(exc).__name__}）"))
            return None

    dockerfile = _text("Dockerfile.serve")
    compose = _yaml("docker-compose.serve.yml")
    namespace_doc = _yaml("k8s/namespace.yaml")
    deployment = _yaml("k8s/deployment.yaml")
    service = _yaml("k8s/service.yaml")

    _check_ports(problems, dockerfile, compose, deployment, service)
    _check_image(problems, compose, deployment)
    _check_namespace(problems, namespace_doc, deployment, service)
    _check_selectors(problems, deployment, service)
    _check_uv_sync(problems, dockerfile)
    _check_env(problems, dockerfile, compose, deployment)
    return problems


# --- port 一貫（EXPOSE＝ENTRYPOINT --port＝compose コンテナ側＝containerPort＝targetPort） ---


def _check_ports(
    problems: list[pm.Problem], dockerfile: str | None, compose: Any, deployment: Any, service: Any
) -> None:
    if dockerfile is None:
        return
    expose = re.search(r"^EXPOSE\s+(\d+)", dockerfile, re.MULTILINE)
    if expose is None:
        problems.append(pm.Problem("error", "templates/serve/Dockerfile.serve: EXPOSE 行が無い（配信ポートの基準）"))
        return
    ref = expose.group(1)

    port = re.search(r"--port\s+(\d+)", dockerfile)
    if port is None:
        problems.append(pm.Problem("error", "templates/serve/Dockerfile.serve: ENTRYPOINT に --port が無い"))
    elif port.group(1) != ref:
        problems.append(
            pm.Problem(
                "error",
                f"templates/serve/Dockerfile.serve: ENTRYPOINT の --port {port.group(1)} が EXPOSE（{ref}）と不一致",
            )
        )

    for name, svc in _services(compose).items():
        for spec in svc.get("ports", []) or []:
            container = str(spec).split(":")[-1]
            if container != ref:
                problems.append(
                    pm.Problem(
                        "error",
                        f"templates/serve/docker-compose.serve.yml: サービス {name} の ports コンテナ側 {container} が "
                        f"EXPOSE ポート（{ref}）と一致しない",
                    )
                )

    for cont in _containers(deployment):
        for p in cont.get("ports", []) or []:
            cp = p.get("containerPort")
            if cp is not None and str(cp) != ref:
                problems.append(
                    pm.Problem(
                        "error",
                        f"templates/serve/k8s/deployment.yaml: containerPort {cp} が EXPOSE（{ref}）と不一致",
                    )
                )

    for p in _svc_ports(service):
        for key in ("port", "targetPort"):
            val = p.get(key)
            if val is not None and str(val) != ref:
                problems.append(
                    pm.Problem(
                        "error",
                        f"templates/serve/k8s/service.yaml: {key} {val} が EXPOSE ポート（{ref}）と一致しない",
                    )
                )


# --- image 名一貫（compose の model-in-image ＝ deployment） ---


def _check_image(problems: list[pm.Problem], compose: Any, deployment: Any) -> None:
    if deployment is None:
        return
    deploy_imgs = [c.get("image") for c in _containers(deployment) if c.get("image")]
    if not deploy_imgs:
        return
    deploy_img = deploy_imgs[0]
    targets = [
        svc.get("image")
        for svc in _services(compose).values()
        if (svc.get("build") or {}).get("target") == _MODEL_IN_IMAGE
    ]
    if not targets:
        problems.append(
            pm.Problem(
                "error",
                f"templates/serve/docker-compose.serve.yml: build.target が {_MODEL_IN_IMAGE} のサービスが無い"
                "（k8s/deployment.yaml の image と突き合わせられない）",
            )
        )
        return
    if targets[0] != deploy_img:
        problems.append(
            pm.Problem(
                "error",
                f"templates/serve/k8s/deployment.yaml: image {deploy_img} が docker-compose.serve.yml の "
                f"{_MODEL_IN_IMAGE}（{targets[0]}）と一致しない",
            )
        )


# --- namespace 一貫（namespace.yaml ＝ deployment ＝ service） ---


def _check_namespace(problems: list[pm.Problem], namespace_doc: Any, deployment: Any, service: Any) -> None:
    ref = (namespace_doc or {}).get("metadata", {}).get("name") if isinstance(namespace_doc, dict) else None
    if ref is None:
        return
    for rel, doc in (("k8s/deployment.yaml", deployment), ("k8s/service.yaml", service)):
        if not isinstance(doc, dict):
            continue
        ns = doc.get("metadata", {}).get("namespace")
        if ns != ref:
            problems.append(
                pm.Problem(
                    "error",
                    f"templates/serve/{rel}: metadata.namespace {ns} が namespace.yaml（{ref}）と一致しない",
                )
            )


# --- selector 整合（deployment matchLabels⊆template labels・service selector⊆template labels） ---


def _check_selectors(problems: list[pm.Problem], deployment: Any, service: Any) -> None:
    if not isinstance(deployment, dict):
        return
    spec = deployment.get("spec", {})
    pod_labels = spec.get("template", {}).get("metadata", {}).get("labels", {}) or {}
    match_labels = spec.get("selector", {}).get("matchLabels", {}) or {}
    for k, v in match_labels.items():
        if pod_labels.get(k) != v:
            problems.append(
                pm.Problem(
                    "error",
                    f"templates/serve/k8s/deployment.yaml: selector.matchLabels {k}={v} が Pod テンプレートの "
                    f"labels（{_fmt(pod_labels)}）に無い＝Pod を選べない",
                )
            )
    if isinstance(service, dict):
        selector = service.get("spec", {}).get("selector", {}) or {}
        for k, v in selector.items():
            if pod_labels.get(k) != v:
                problems.append(
                    pm.Problem(
                        "error",
                        f"templates/serve/k8s/service.yaml: selector {k}={v} が Deployment の Pod labels"
                        f"（{_fmt(pod_labels)}）に無い＝振り分け先が無い",
                    )
                )


# --- uv sync に --extra serve ---


def _check_uv_sync(problems: list[pm.Problem], dockerfile: str | None) -> None:
    if dockerfile is None:
        return
    for line in dockerfile.splitlines():
        if "uv sync" in line and "--extra serve" not in line:
            problems.append(
                pm.Problem(
                    "error",
                    "templates/serve/Dockerfile.serve: uv sync に --extra serve が無い"
                    f"（配信依存が入らない）: {line.strip()}",
                )
            )


# --- env SERVE_WORK / SERVE_NAME の三者一致（Dockerfile ENTRYPOINT・compose・deployment） ---


def _check_env(problems: list[pm.Problem], dockerfile: str | None, compose: Any, deployment: Any) -> None:
    if dockerfile is not None:
        entrypoint = next((ln for ln in dockerfile.splitlines() if ln.lstrip().startswith("ENTRYPOINT")), "")
        for name in _REQUIRED_ENV:
            if f"${name}" not in entrypoint:
                problems.append(
                    pm.Problem(
                        "error",
                        f"templates/serve/Dockerfile.serve: ENTRYPOINT が env ${name} を参照していない",
                    )
                )

    for svc_name, svc in _services(compose).items():
        keys = _env_keys(svc.get("environment"))
        for name in _REQUIRED_ENV:
            if name not in keys:
                problems.append(
                    pm.Problem(
                        "error",
                        f"templates/serve/docker-compose.serve.yml: サービス {svc_name} の environment に "
                        f"{name} が無い",
                    )
                )

    for cont in _containers(deployment):
        names = {e.get("name") for e in (cont.get("env") or [])}
        for name in _REQUIRED_ENV:
            if name not in names:
                problems.append(
                    pm.Problem("error", f"templates/serve/k8s/deployment.yaml: container env に {name} が無い")
                )


# --- YAML 構造の取り出し（欠けても落ちない：常に空を返す） ---


def _services(compose: Any) -> dict[str, dict[str, Any]]:
    services = compose.get("services") if isinstance(compose, dict) else None
    return {k: v for k, v in services.items() if isinstance(v, dict)} if isinstance(services, dict) else {}


def _containers(deployment: Any) -> list[dict[str, Any]]:
    if not isinstance(deployment, dict):
        return []
    conts = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers")
    return [c for c in conts if isinstance(c, dict)] if isinstance(conts, list) else []


def _svc_ports(service: Any) -> list[dict[str, Any]]:
    if not isinstance(service, dict):
        return []
    ports = service.get("spec", {}).get("ports")
    return [p for p in ports if isinstance(p, dict)] if isinstance(ports, list) else []


def _env_keys(environment: Any) -> set[str]:
    """compose の environment（dict でも `KEY=val` の list でも）からキー集合を取り出す。"""
    if isinstance(environment, dict):
        return set(environment)
    if isinstance(environment, list):
        return {str(item).split("=", 1)[0].split(":", 1)[0].strip() for item in environment}
    return set()


def _fmt(labels: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in labels.items()) or "（無し）"
