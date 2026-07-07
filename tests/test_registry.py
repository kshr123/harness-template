"""汎用レジストリ（harness.registry）の単体テスト。

9 個の DS レジストリを 1 つの形に揃える中核。ここでは Registry/Entry/MetricEntry の契約
（説明文の自動導出・未知 kind のエラー・Mapping 互換・build の素通し・task 突き合わせ）を固定する。
"""

from __future__ import annotations

import pytest

from harness.registry import Entry, MetricEntry, Registry

pytestmark = pytest.mark.unit


def _make() -> Registry[Entry]:
    return Registry("モデル", catalog="data models", extras_hint={"lightgbm": "lightgbm"})


def _factory_with_doc(seed: int, *, scale: float = 1.0) -> float:
    """説明文はこの 1 行目から取られる。"""
    return seed * scale


def test_description_derived_from_docstring_first_line() -> None:
    reg = _make()
    reg.register("f", _factory_with_doc)
    assert reg["f"].description == "説明文はこの 1 行目から取られる。"


def test_register_without_description_or_docstring_raises() -> None:
    reg = _make()

    def no_doc(seed: int) -> int:
        return seed

    # docstring も description= も無い＝カタログに載れない 違反として登録時に失敗。
    with pytest.raises(ValueError, match="説明文が無い"):
        reg.register("nodoc", no_doc)


def test_class_factory_does_not_inherit_parent_docstring() -> None:
    reg = _make()

    class Base:
        """親の説明（継承させない）。"""

    class Child(Base):  # 自前 docstring 無し
        pass

    # 親の docstring を継承して空振りさせない（test_catalog の規約）。自前が無ければ失敗。
    with pytest.raises(ValueError, match="説明文が無い"):
        reg.register("child", Child)


def test_duplicate_kind_is_rejected() -> None:
    reg = _make()
    reg.register("f", _factory_with_doc)
    with pytest.raises(ValueError, match="登録済み"):
        reg.register("f", _factory_with_doc)


def test_resolve_unknown_kind_lists_candidates_and_catalog_and_extra_hint() -> None:
    reg = _make()
    reg.register("logreg", _factory_with_doc)
    with pytest.raises(ValueError) as exc:
        reg.resolve("lightgbm")  # 未登録だが extras_hint にある
    msg = str(exc.value)
    assert "未知のモデル" in msg
    assert "logreg" in msg  # 候補一覧
    assert "uv run data models" in msg  # カタログコマンド
    assert "uv sync --extra lightgbm" in msg  # 導入ヒント


def test_mapping_protocol() -> None:
    reg = _make()
    reg.register("a", _factory_with_doc)
    reg.register("b", _factory_with_doc)
    assert "a" in reg and "z" not in reg
    assert sorted(reg) == ["a", "b"]
    assert len(reg) == 2
    assert {k for k, _ in reg.items()} == {"a", "b"}


def test_build_calls_factory_with_seed_and_params_dropping_wiring_keys() -> None:
    reg = _make()
    reg.register("f", _factory_with_doc)
    # kind/name/columns は params から落ちる。seed は第 1 引数、scale は params。
    got = reg.build({"kind": "f", "name": "x", "columns": ["c"], "scale": 3.0}, seed=2)
    assert got == 6.0  # 2 * 3.0（seed*scale）


def test_build_rejects_task_mismatch() -> None:
    reg = _make()
    reg.register("clf", _factory_with_doc, task="classification")
    with pytest.raises(ValueError, match="regression"):
        reg.build({"kind": "clf"}, seed=0, task="regression")


def test_metric_entry_carries_fields_and_fn_alias() -> None:
    reg: Registry[MetricEntry] = Registry("指標", catalog="data metrics")
    reg.register(
        "roc_auc",
        _factory_with_doc,
        entry_cls=MetricEntry,
        input="score",
        higher_is_better=True,
        tasks=("binary",),
    )
    e = reg["roc_auc"]
    assert e.input == "score"
    assert e.higher_is_better is True
    assert e.tasks == ("binary",)
    assert e.fn is _factory_with_doc  # 旧 Metric.fn 互換
