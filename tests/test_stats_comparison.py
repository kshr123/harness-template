"""PSIS-LOO 比較とベイズモデルの採用（harness.promotion）の検査（T-0217）。

期待値は構成から：真のモデルは 2 特徴（beta=[1.5,-2.0]）。片方を落とした 1 特徴モデルは予測力を失うので LOO の
elpd が下がる＝2 特徴が rank 0。採用は promotion に載せる：初回は昇格・現 champion より悪い版は却下（strict 改善）。
MCMC は小さく回す。stats を使わない複製では importorskip で skip。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pymc")
pytest.importorskip("nutpie")

from harness import gates, promotion  # noqa: E402
from harness.stats import comparison, models, sampling, store  # noqa: E402

pytestmark = pytest.mark.integration


def _fit(n_features: int) -> tuple[object, object]:
    rng = np.random.default_rng(0)
    x = rng.normal(size=(90, 2))
    y = 0.5 + x @ np.array([1.5, -2.0]) + rng.normal(scale=0.3, size=90)  # 真は 2 特徴
    model = models.build_bayes_model({"kind": "linear"}, {"X": x[:, :n_features], "y": y})
    idata = sampling.run_inference(model, sampler="nutpie", draws=200, tune=200, chains=2, seed=0)
    comparison.add_log_likelihood(model, idata)
    return model, idata


def test_loo_requires_log_likelihood() -> None:
    """log_likelihood 群が無い idata（生の nutpie 出力）に loo を求めると明示的な ValueError（先に計算する）。"""
    rng = np.random.default_rng(0)
    x = rng.normal(size=(60, 2))
    y = x @ np.array([1.0, -1.0]) + rng.normal(scale=0.3, size=60)
    model = models.build_bayes_model({"kind": "linear"}, {"X": x, "y": y})
    idata = sampling.run_inference(model, sampler="nutpie", draws=100, tune=100, chains=2, seed=0)
    assert not hasattr(idata, "log_likelihood")  # add_log_likelihood を呼んでいない＝群が無い
    with pytest.raises(ValueError, match="log_likelihood"):
        comparison.loo(idata)


def test_compare_ranks_the_true_model_first() -> None:
    """2 特徴（真のモデル）は 1 特徴（予測子を 1 つ落とした劣モデル）より LOO の elpd が高く、rank 0 になる。"""
    _, full = _fit(2)
    _, reduced = _fit(1)
    assert comparison.loo(full) > comparison.loo(reduced)  # 真のモデルの方が予測が上手い（構成から）
    assert comparison.select_best({"full": full, "reduced": reduced}) == "full"


def test_adopt_first_promotes_and_sets_champion(tmp_path: Path) -> None:
    """初回の採用は昇格し、champion になる（baseline が無いので change_threshold は課さない）。"""
    model, idata = _fit(2)
    result = comparison.adopt(
        tmp_path, model, idata, name="m", work="w", version="v1", decided="20260713T000001000000Z"
    )
    assert result.status == "approved"
    ent = store.entity_dir(tmp_path, name="m")
    assert promotion.champion_version(ent, label="m") == "v1"


def test_adopt_worse_model_is_rejected(tmp_path: Path) -> None:
    """champion より悪い版（1 特徴・低い elpd）は却下され、champion は動かない（strict 改善の要求）。"""
    full_model, full = _fit(2)
    comparison.adopt(tmp_path, full_model, full, name="m", work="w", version="v1", decided="20260713T000001000000Z")
    red_model, reduced = _fit(1)
    with pytest.raises(gates.PromotionError):
        comparison.adopt(
            tmp_path, red_model, reduced, name="m", work="w", version="v2", decided="20260713T000002000000Z"
        )
    ent = store.entity_dir(tmp_path, name="m")
    assert promotion.champion_version(ent, label="m") == "v1"  # 却下は champion を動かさない


def test_compare_needs_two_models() -> None:
    _, idata = _fit(2)
    with pytest.raises(ValueError, match="2 つ以上"):
        comparison.compare_models({"only": idata})
