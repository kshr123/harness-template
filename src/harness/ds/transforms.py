"""ターゲット変換：学習の前後で目的変数 y を往復させる純粋な部品（numpy のみ）。

- 学習器は変換後のスケールで学習し、予測は必ず元スケールへ戻す。戻し忘れを型（Protocol）で防ぐ。
- どの案件・どのデータにも使える汎用部品にする（列名・データ形・グローバル状態に依存しない）。
  変換は純粋（同じ入力→同じ出力・副作用なし）。統計が要る標準化だけ fit で得た値をインスタンスが持つ。
- API は scikit-learn の慣習（transform / inverse_transform / fit）に合わせ、広く差し替え可能にする。

出典：ml-competition-template（`src/mlcomp/domain/transforms.py`。README 記載のライセンス＝MIT）。
逐語ではなく、同じ契約（transform/inverse_transform の往復）を型付きの汎用部品として移植した。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]


@runtime_checkable
class TargetTransform(Protocol):
    """目的変数の往復変換の契約。非負ターゲット等の含みは実装ごと。

    学習系はこの型だけに依存し、具体（Identity/Log1p/StandardScale）を差し替えられる。
    """

    def transform(self, y: Array) -> Array:
        """元スケール → 学習用スケール。"""
        ...

    def inverse_transform(self, y: Array) -> Array:
        """学習用スケール → 元スケール。"""
        ...


class Identity:
    """変換なし（そのまま使う）。既定の差し替え先。"""

    def transform(self, y: Array) -> Array:
        return np.asarray(y, dtype=np.float64)

    def inverse_transform(self, y: Array) -> Array:
        return np.asarray(y, dtype=np.float64)


class Log1p:
    """y -> log(1+y)。非負・右裾の長い目的変数（価格など）を圧縮する。

    inverse は expm1。逆変換で負に振れた値は 0 に切り上げる（非負ターゲットの下限を守る）。
    このため往復（inverse_transform∘transform）が厳密に元へ戻るのは y ≥ 0 の範囲。
    """

    def transform(self, y: Array) -> Array:
        return np.log1p(np.asarray(y, dtype=np.float64))

    def inverse_transform(self, y: Array) -> Array:
        return np.maximum(np.expm1(np.asarray(y, dtype=np.float64)), 0.0)


class StandardScale:
    """y を (y-mean)/std に標準化する。mean・std は fit で学習し、inverse は同じ値で戻す。

    グローバル状態を持たず、fit した統計をこのインスタンスだけが持つ（漏れ防止のため train でだけ fit する）。
    定数配列（std=0）は 0 除算を避けるため std=1 とみなす。fit 前の呼び出しは失敗させる。
    """

    def __init__(self) -> None:
        self._mean: float | None = None
        self._std: float | None = None

    def fit(self, y: Array) -> StandardScale:
        arr = np.asarray(y, dtype=np.float64)
        self._mean = float(arr.mean())
        std = float(arr.std())
        self._std = std if std != 0.0 else 1.0
        return self

    def _fitted(self) -> tuple[float, float]:
        if self._mean is None or self._std is None:
            raise RuntimeError("先に fit() で平均・分散を学習すること")
        return self._mean, self._std

    def transform(self, y: Array) -> Array:
        mean, std = self._fitted()
        return (np.asarray(y, dtype=np.float64) - mean) / std

    def inverse_transform(self, y: Array) -> Array:
        mean, std = self._fitted()
        return np.asarray(y, dtype=np.float64) * std + mean
