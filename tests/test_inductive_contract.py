"""帰納性（inductive）の契約：`inductive=True` と申告した住人は、本当に新規行を変換・採点できる（T-0220）。

なぜ挙動で検証するか：`inductive` は Entry の申告フィールドなので、申告が嘘（inductive=True なのに新規行を
通せない）だと (B) 特徴経路で黙って壊れる。対象集合は各レジストリの登録から機械的に導く（inductive=True の
kind を列挙＝住人を足した瞬間に自動で検査対象になる。kind 名のハードコードをしない）。学習に使っていない
新規 3 行を通し、正しい形の出力が返ることだけを言う（実装出力の写経をしない＝構成から導く）。

申告の**両方向**を挙動で確かめる：(1) inductive=True と申告した住人は本当に新規行を通せる（下の正の
テスト）。(2) inductive=False と申告した住人は本当に新規行を通せない＝帰納の操作を持たない（下の負の
テスト）。後者が無いと、使える手法を inductive=False と誤申告して (B) の口を黙って塞ぐ嘘を見逃す。
また inductive=True の一覧が空になると parametrize が黙って skip 化するので、非空を明示的に検査する。

(B) 経路の直書き除去（`pipeline._cluster`／`_anomaly_score` の method 軸）は、inductive=False の method を
実行前に `ValueError` で止めることと、既定（kmeans／iforest）が不変であることで確かめる。
"""

from __future__ import annotations

import inspect
from typing import Any

import numpy as np
import pytest

from harness.ds import pipeline
from harness.ds.unsupervised import ANOMALY, CLUSTERERS, DIMRED, UnsupervisedEntry

pytestmark = pytest.mark.integration

# 必須引数（既定なし）の構成値。**引数名で引く**（kind 名ではない）ので、n_clusters/n_components を要する
# 新住人（kmedoids/kmodes 等）はテスト変更なしで通る。全く新しい必須引数の住人が来たらここに 1 行足す
# （その追加は「答えの写経」ではなく構成の足場＝テストの決まりごとに反しない）。
_CONSTRUCTION_PARAMS: dict[str, Any] = {"n_clusters": 2, "n_components": 2}


def _build(entry: UnsupervisedEntry, seed: int) -> Any:  # noqa: ANN401  工場の返り値（sklearn 推定器）へ素通し
    """工場を必要最小限の構成値で作る（必須引数だけ _CONSTRUCTION_PARAMS から埋める・seed は別途渡す）。"""
    kwargs: dict[str, Any] = {}
    for name, param in inspect.signature(entry.factory).parameters.items():
        if name == "seed" or param.kind in (param.VAR_KEYWORD, param.VAR_POSITIONAL):
            continue
        if param.default is inspect.Parameter.empty:  # 既定なし＝構築に必須
            assert name in _CONSTRUCTION_PARAMS, (
                f"帰納性テスト：必須引数 '{name}' の構成値が無い。_CONSTRUCTION_PARAMS に足す（構成の足場）"
            )
            kwargs[name] = _CONSTRUCTION_PARAMS[name]
    return entry.factory(seed, **kwargs)


def _train_and_new(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """学習用 40 行と、学習に使っていない新規 3 行（3 数値列）。決定性は seed 明示引数から。"""
    rng = np.random.default_rng(seed)
    x_train = rng.normal(size=(40, 3))
    x_new = rng.normal(size=(3, 3))  # fit に一切使わない行
    return x_train, x_new


_INDUCTIVE_CLUSTERERS = sorted(k for k in CLUSTERERS if CLUSTERERS[k].inductive)
_INDUCTIVE_DIMRED = sorted(k for k in DIMRED if DIMRED[k].inductive)
_INDUCTIVE_ANOMALY = sorted(k for k in ANOMALY if ANOMALY[k].inductive)

_NON_INDUCTIVE_CLUSTERERS = sorted(k for k in CLUSTERERS if not CLUSTERERS[k].inductive)
_NON_INDUCTIVE_DIMRED = sorted(k for k in DIMRED if not DIMRED[k].inductive)
_NON_INDUCTIVE_ANOMALY = sorted(k for k in ANOMALY if not ANOMALY[k].inductive)


def test_every_registry_has_inductive_residents() -> None:
    """各レジストリに inductive=True の住人が最低 1 つある。空だと上の parametrize が黙って skip 化する
    （全 kind を誤って inductive=False にした回帰を、緑の見た目で通さない）。"""
    assert _INDUCTIVE_CLUSTERERS, "CLUSTERERS に inductive=True の住人が無い（帰納性契約が空回りする）"
    assert _INDUCTIVE_DIMRED, "DIMRED に inductive=True の住人が無い（帰納性契約が空回りする）"
    assert _INDUCTIVE_ANOMALY, "ANOMALY に inductive=True の住人が無い（帰納性契約が空回りする）"


@pytest.mark.parametrize("method", _INDUCTIVE_CLUSTERERS)
def test_inductive_clusterer_predicts_new_rows(method: str) -> None:
    """inductive=True の全クラスタリング住人は、fit 後に新規 3 行のクラスタ番号を返せる（predict）。"""
    x_train, x_new = _train_and_new(seed=0)
    model = _build(CLUSTERERS[method], seed=0).fit(x_train)
    labels = np.asarray(model.predict(x_new))
    assert labels.shape == (3,)  # 新規 3 行それぞれに 1 つのクラスタ番号


@pytest.mark.parametrize("method", _INDUCTIVE_DIMRED)
def test_inductive_dimred_transforms_new_rows(method: str) -> None:
    """inductive=True の全次元圧縮住人は、fit 後に新規 3 行を埋め込める（transform）。"""
    x_train, x_new = _train_and_new(seed=0)
    model = _build(DIMRED[method], seed=0).fit(x_train)
    coords = np.asarray(model.transform(x_new))
    assert coords.shape[0] == 3  # 新規 3 行それぞれに座標


@pytest.mark.parametrize("method", _INDUCTIVE_ANOMALY)
def test_inductive_anomaly_scores_new_rows(method: str) -> None:
    """inductive=True の全異常検知住人は、fit 後に新規 3 行を採点できる（score_samples）。"""
    x_train, x_new = _train_and_new(seed=0)
    model = _build(ANOMALY[method], seed=0).fit(x_train)
    scores = np.asarray(model.score_samples(x_new))
    assert scores.shape == (3,)  # 新規 3 行それぞれに 1 つのスコア


@pytest.mark.parametrize("method", _NON_INDUCTIVE_CLUSTERERS)
def test_non_inductive_clusterer_truly_lacks_predict(method: str) -> None:
    """inductive=False のクラスタリング住人は本当に predict を持たない（持てば「使えるのに False」の誤申告）。"""
    model = _build(CLUSTERERS[method], seed=0)
    assert not hasattr(model, "predict")  # 新規行に predict できてしまうなら inductive=True が正しい


@pytest.mark.parametrize("method", _NON_INDUCTIVE_DIMRED)
def test_non_inductive_dimred_truly_lacks_transform(method: str) -> None:
    """inductive=False の次元圧縮住人は本当に transform を持たない（持てば誤申告＝(B) の口を塞いでいる）。"""
    model = _build(DIMRED[method], seed=0)
    assert not hasattr(model, "transform")  # 新規行を transform できてしまうなら inductive=True が正しい


@pytest.mark.parametrize("method", _NON_INDUCTIVE_ANOMALY)
def test_non_inductive_anomaly_truly_lacks_score_samples(method: str) -> None:
    """inductive=False の異常検知住人は本当に score_samples を持たない（持てば誤申告）。"""
    model = _build(ANOMALY[method], seed=0)
    assert not hasattr(model, "score_samples")  # 新規行を採点できてしまうなら inductive=True が正しい


def test_b_cluster_rejects_non_inductive_method() -> None:
    """(B) の cluster エンコーダに inductive=False の method（hdbscan）を指定すると kind を名指しした ValueError。"""
    with pytest.raises(ValueError, match="hdbscan"):
        pipeline._cluster(seed=0, method="hdbscan")


def test_b_anomaly_rejects_non_inductive_method() -> None:
    """(B) の anomaly_score エンコーダに inductive=False の method（lof）を指定すると kind を名指しした ValueError。"""
    with pytest.raises(ValueError, match="lof"):
        pipeline._anomaly_score(seed=0, method="lof")


def test_b_cluster_distance_rejected_when_no_transform() -> None:
    """distance 出力は transform を持つ手法のみ（gmm は predict はできるが中心への距離が無い）＝ValueError。"""
    with pytest.raises(ValueError, match="distance"):
        pipeline._cluster(seed=0, method="gmm", output="distance", n_components=2)


def test_b_cluster_default_is_kmeans_and_transforms_new_rows() -> None:
    """method 未指定の既定は kmeans（既存 config 互換）。label 出力は新規行のクラスタ番号 1 列を返す。"""
    x_train, x_new = _train_and_new(seed=0)
    enc: Any = pipeline._cluster(seed=0, n_clusters=2, output="label")  # method 未指定＝kmeans
    out = np.asarray(enc.fit(x_train).transform(x_new))
    assert out.shape == (3, 1)  # 新規 3 行 × クラスタ番号 1 列
