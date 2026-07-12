"""ANOMALY の符号契約：全住人で「大きいほど異常」を挙動で固定する（T-0219）。

なぜ挙動で固定するか：sklearn の `score_samples` は「低いほど異常」、PyOD の `decision_function` は
「高いほど異常」で、同じ IsolationForest でも符号が逆になる（2026-07-11 実測）。包む側で符号を揃えて
いるが、その性質を「住人が増えたら自動で新住人に掛かる」形で守らないと、逆符号の住人を足した第 1 号で
`anomaly_score` の意味が kind ごとに割れる（黙って間違う側の欠陥）。

対象集合は `sorted(ANOMALY)` から機械的に導く＝kind 名のハードコード列挙をしない。住人を足した瞬間に
自動で対象になる（保証の段階 (b)）。期待値はデータの構成から導く：明白な外れ行を既知の位置に 1 つ仕込み、
最大スコアの行がその行であることだけを言う（実装出力の写経をしない）。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
import pytest

from harness.ds import pipeline, unsupervised

pytestmark = pytest.mark.integration

_OUTLIER_ROW = 0  # 仕込む外れ行の位置（データの構成から既知＝この行が全 kind で argmax になるはず）


def _one_planted_outlier(n_normal: int, seed: int) -> pl.DataFrame:
    """原点近傍に密集した正常行＋遠く離れた外れ行 1 つ。外れ行は先頭（_OUTLIER_ROW）に置く。

    正常のばらつき（0.3）に対し外れは 100 離す＝どの手法でも「浮いている行」が一意に定まる構成。
    """
    rng = np.random.default_rng(seed)
    normal = rng.normal(loc=[0.0, 0.0], scale=0.3, size=(n_normal, 2))
    outlier = np.array([[100.0, 100.0]])
    x = np.vstack([outlier, normal])  # 先頭が外れ行
    return pl.DataFrame({"x1": x[:, 0], "x2": x[:, 1]})


@pytest.mark.parametrize("method", sorted(unsupervised.ANOMALY))
def test_planted_outlier_is_argmax_for_every_anomaly_kind(method: str) -> None:
    """(A) 経路：登録済みの全 kind で、仕込んだ外れ行が最大スコアになる（符号が「大きいほど異常」に揃う）。

    対象は `sorted(ANOMALY)` から導出（parametrize が住人を足すたび自動で増える）。逆符号の住人を
    仮登録すると、その kind でここが argmin を返して落ちる＝別の立場を挙動で検出できる。
    """
    df = _one_planted_outlier(n_normal=60, seed=0)
    report = unsupervised.anomaly_scores(df, method=method, seed=0)
    scores = report.scores.to_numpy()
    assert int(np.argmax(scores)) == _OUTLIER_ROW  # 大きいほど異常＝外れ行が最大（構成から導出）


def test_contract_would_catch_a_reversed_sign_resident() -> None:
    """契約が本物であることの証明：符号が逆（低いほど異常）のスコアを同じデータに当てると、外れ行は
    argmax にならない。つまり逆符号の住人を足せば上の parametrize 検査が落ちる（この検査は飾りでない）。
    """
    df = _one_planted_outlier(n_normal=60, seed=0)
    x = df.to_numpy()
    # sklearn の生スコア（大きいほど正常＝符号を揃えていない）を直に読む＝逆符号住人の代役。
    from sklearn.ensemble import IsolationForest

    raw = IsolationForest(random_state=0).fit(x).score_samples(x)  # 外れ行が最小になる向き
    assert int(np.argmax(raw)) != _OUTLIER_ROW  # 符号を揃えないと外れ行は argmax にならない＝契約が効く


_INDUCTIVE_ANOMALY = sorted(k for k in unsupervised.ANOMALY if unsupervised.ANOMALY[k].inductive)


@pytest.mark.parametrize("method", _INDUCTIVE_ANOMALY)
def test_b_path_encoder_shares_the_same_direction(method: str) -> None:
    """(B) 特徴経路の `anomaly_score` エンコーダも「大きいほど異常」（(A) と (B) で意味が割れない）。

    (B) に載るのは inductive=True の kind だけ（非帰納は _anomaly_score が拒否する）。対象は
    ANOMALY の inductive 住人から導出＝新住人も自動で対象になる。fit-on-train は run_cv の
    clone-per-fold が担保する構造なので、ここでは向きだけを見る：全データに fit → transform し、
    仕込んだ外れ行が最大スコアの 1 列になることを確かめる。
    """
    df = _one_planted_outlier(n_normal=60, seed=0)
    x = df.to_numpy()
    encoder: Any = pipeline._anomaly_score(seed=0, method=method)
    scores = np.asarray(encoder.fit(x).transform(x)).ravel()
    assert scores.shape == (df.height,)  # スコア 1 列・n 行
    assert int(np.argmax(scores)) == _OUTLIER_ROW  # (A) と同じ向き（大きいほど異常）
