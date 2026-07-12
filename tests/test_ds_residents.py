"""教師なしレジストリに増やした住人の個別検査（T-0221/0222/0223）。

符号・帰納性の契約（レジストリ駆動）は test_anomaly_sign_contract / test_inductive_contract が全 kind に
掛ける。ここは各住人の**固有の性質**を、汎用契約が拾わない所だけ確かめる：kmedoids の predict 体系差の吸収・
openTSNE の決定性・lof_novelty の登録。期待値はデータの構成（離れた 2 塊）から導く。
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from sklearn.metrics import adjusted_rand_score

from harness.ds import unsupervised

pytestmark = pytest.mark.integration


def _two_blobs(n: int, seed: int) -> tuple[pl.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    a = rng.normal(loc=[0.0, 0.0], scale=0.3, size=(n, 2))
    b = rng.normal(loc=[10.0, 10.0], scale=0.3, size=(n, 2))  # 中心距離 ≫ ばらつき
    x = np.vstack([a, b])
    true = np.array([0] * n + [1] * n)
    return pl.DataFrame({"x1": x[:, 0], "x2": x[:, 1]}), true


def test_kmedoids_recovers_two_blobs() -> None:
    """kmedoids は離れた 2 塊を完全分離する（構成から adjusted_rand_score=1.0）。"""
    df, true = _two_blobs(80, seed=0)
    report = unsupervised.cluster_summary(df, method="kmedoids", seed=0, n_clusters=2)
    assert adjusted_rand_score(true, report.labels.to_numpy()) == pytest.approx(1.0)


def test_kmedoids_predict_is_remapped_to_label_system() -> None:
    """kmedoids.predict は近傍メドイドの行番号を返すが、包みが labels_ 体系（0..k-1）へ揃える。

    実測（2026-07-13）で predict が行番号を返すことを確認済み。包みが効いていれば：学習データへの predict が
    fit_predict のラベルと一致し（同一データなら同じ割当）、値域が 0..k-1 に収まる（行番号 0..2n-1 でない）。
    """
    df, _ = _two_blobs(80, seed=0)  # 160 行
    factory = unsupervised.CLUSTERERS["kmedoids"].factory
    model = factory(0, n_clusters=2)
    x = df.to_numpy()
    fit_labels = np.asarray(model.fit_predict(x))
    pred_labels = np.asarray(model.predict(x))
    assert np.array_equal(pred_labels, fit_labels)  # 同一データ→同じ割当（体系差が残っていれば False）
    assert set(pred_labels.tolist()) <= {0, 1}  # 0..k-1 に収まる（メドイドの行番号 0..159 でない）


def test_kmedoids_survives_clone_and_refit() -> None:
    """kmedoids の包み（_MedoidLabelAdapter）は sklearn.clone で複製でき、複製が再学習・predict できる。

    (B) 特徴経路は run_cv が fold ごとに clone-per-fold で新品を作るので、clone を通らないと (B) で使えない。
    複製後に別データで fit → predict が 0..k-1 のラベルを返す（体系差の吸収が clone 後も効く）ことを確かめる。
    """
    from sklearn.base import clone

    df, _ = _two_blobs(60, seed=0)
    original = unsupervised.CLUSTERERS["kmedoids"].factory(0, n_clusters=2)
    fresh = clone(original)  # get_params/クローン不能なら here で落ちる
    x = df.to_numpy()
    labels = np.asarray(fresh.fit(x).predict(x))
    assert set(labels.tolist()) <= {0, 1}  # クローン後も predict は labels_ 体系（0..k-1）


def test_opentsne_embed_is_deterministic() -> None:
    """openTSNE の 2D 埋め込みは同じ (df, seed) で同じ座標（n_jobs=1＋random_state=seed の決定性）。"""
    df, _ = _two_blobs(60, seed=0)
    c1 = unsupervised.embed_2d(df, method="opentsne", seed=0).coords.to_numpy()
    c2 = unsupervised.embed_2d(df, method="opentsne", seed=0).coords.to_numpy()
    assert np.allclose(c1, c2)  # 同 seed で座標一致（決定的）


def test_opentsne_is_registered_inductive() -> None:
    """openTSNE は DIMRED に inductive=True で登録される（(B) 経路に載る帰納的な非線形埋め込み）。"""
    assert "opentsne" in unsupervised.DIMRED
    assert unsupervised.DIMRED["opentsne"].inductive is True


def test_lof_novelty_is_registered_inductive() -> None:
    """lof_novelty は ANOMALY に inductive=True で登録される（既存の lof＝非帰納とは別 kind で共存）。"""
    assert "lof_novelty" in unsupervised.ANOMALY
    assert unsupervised.ANOMALY["lof_novelty"].inductive is True
    assert unsupervised.ANOMALY["lof"].inductive is False  # 既存の (A) 専用 LOF はそのまま
