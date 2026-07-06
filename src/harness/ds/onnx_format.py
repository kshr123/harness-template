"""ONNX 保存形式（FORMATS "onnx" の実体・sklearn 尾部のみ変換・OnnxClassifier/OnnxRegressor）。

- 当リポの Pipeline は polars 特徴量＋sklearn の混成で、step 名 `to_numpy` が numpy↔polars の境界（pipeline.py）。
  ONNX に乗るのはその尾部（select?＋model）だけ＝fit 済み段をそのまま再配線して変換する（refit しない）。
  前段（特徴量・エンコード）は変換しないので、**読み込んだモデルの入力は特徴量計算済みの数値テーブル
  （float32・列は metadata の feature_names）**。`to_numpy` 段が無ければ全体を変換する（純 numpy の推定器向け）。
- 対象外（dump 時に明示エラー）：tail 入力が疎になる構成（tfidf 等・fit 済み段の sparse_output_ で検出）・
  lightgbm 尾部（skl2onnx 標準に変換器が無い）。古典時系列（forecast）は sklearn Pipeline に載らない＝そもそも来ない。
- metadata_props（キー harness_ds）に契約を JSON で焼き込む：feature_names / n_features / input_dtype="float32" /
  prediction_kind（proba | multiclass_proba | value）/ classes / source="harness.ds"。ファイル単体で自己記述＝可搬。
- 保存時ラウンドトリップ自己検査：決定的乱数の入力で InferenceSession と tail の予測を allclose 照合し、
  不一致・変換不能は ValueError＝「保存できたが読めない/違う」ファイルを作らない（skops の保存時検査と同じ作法）。
- 安全性：ONNX は計算グラフ＋重みのデータで、pickle と違い読込で任意コードが走らない（信頼リストは不要）。
- module top は stdlib＋numpy のみ。skl2onnx / onnxruntime / onnx / sklearn は関数内の遅延 import（skops と同じ作法）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

METADATA_KEY = "harness_ds"  # metadata_props の契約キー（load はこのキーの JSON だけを信じる）
_SOURCE = "harness.ds"
_TO_NUMPY_STEP = "to_numpy"  # pipeline.build_estimator が焼き込む固定名（numpy↔polars 境界）
# 自己検査の入力（決定的乱数）と許容差。ONNX 側は float32 計算なので 1e-4 程度の丸め差は正常
# （それ以上のずれ＝変換の壊れ）。木モデルはしきい値ちょうどの点で稀に割れうるが、連続値乱数では実質起きない。
_CHECK_ROWS = 16
_CHECK_SEED = 0
_CHECK_RTOL = 1e-3
_CHECK_ATOL = 1e-4


def _flat_estimators(est: object) -> list[object]:
    """est の中の推定器を平らに列挙する（Pipeline は各 step を再帰・単体はそれ 1 つ）。lightgbm 検査用。"""
    steps = getattr(est, "steps", None)
    if steps is None:
        return [est]
    out: list[object] = []
    for _, sub in steps:
        out.extend(_flat_estimators(sub))
    return out


def _split_at_to_numpy(model: object) -> tuple[object, tuple[str, ...]]:
    """Pipeline を `to_numpy` 境界で頭と尾に割り、(tail, 境界の列名) を返す。境界が無ければ全体が tail。

    tail は fit 済み step の再配線（sklearn Pipeline は最終段の fit 済み判定を委譲するので refit 不要）。
    頭に疎出力の段（tfidf を含む ColumnTransformer 等）があれば ValueError（tail 入力が疎＝ONNX 化の対象外）。
    """
    from sklearn.pipeline import Pipeline

    if not isinstance(model, Pipeline) or _TO_NUMPY_STEP not in dict(model.steps):
        return model, ()
    names = [name for name, _ in model.steps]
    at = names.index(_TO_NUMPY_STEP)
    head = model[: at + 1]
    for name, step in head.steps:
        if getattr(step, "sparse_output_", False):
            raise ValueError(
                f"tail の入力が疎になる構成（'{name}' 段の出力が scipy 疎行列。tfidf 等）は ONNX 形式の対象外。"
                "format='pickle' か 'skops' を使うこと"
            )
    tail_steps = model.steps[at + 1 :]
    if not tail_steps:
        raise ValueError(f"'{_TO_NUMPY_STEP}' の後段が無い（model 段の無い Pipeline は ONNX 化の対象外）")
    tail: object = tail_steps[0][1] if len(tail_steps) == 1 else Pipeline(tail_steps)
    try:
        feature_names = tuple(str(n) for n in head.get_feature_names_out())
    except Exception:
        feature_names = ()  # 境界の列名が取れない構成でも保存は許す（numpy 入力の口は生きる）
    return tail, feature_names


def _classes_of(tail: Any) -> NDArray[np.int64]:
    """分類 tail のクラスを int64 で返す。非整数ラベル・多クラス非連番は ValueError（cv._predict と同契約）。"""
    classes = np.asarray(tail.classes_)
    if not np.issubdtype(classes.dtype, np.number):
        raise ValueError(f"ONNX 形式は整数ラベルのみ対応（classes_={classes.tolist()}）")
    as_int = classes.astype(np.int64)
    if not np.array_equal(as_int.astype(classes.dtype), classes):
        raise ValueError(f"ONNX 形式は整数ラベルのみ対応（classes_={classes.tolist()} は整数に丸まらない）")
    if len(as_int) < 2:
        raise ValueError(f"クラスが 2 未満（classes_={as_int.tolist()}）の分類器は保存できない")
    if len(as_int) > 2 and not np.array_equal(as_int, np.arange(len(as_int))):
        raise ValueError(
            "多クラスのラベルは 0..k-1 の連番が前提（proba の列順＝クラス番号・cv._predict と同契約）。"
            f"実際のラベル: {as_int.tolist()}"
        )
    return as_int


def _session(path: Path) -> Any:
    """onnxruntime InferenceSession（CPU）。壊れた/ONNX でないファイルは ValueError に揃える。"""
    import onnxruntime

    try:
        return onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    except Exception as exc:
        raise ValueError(f"{path}: ONNX ファイルを読めない（壊れているか ONNX 形式でない）: {exc}") from exc


def _self_check(path: Path, tail: Any, *, n_features: int, classifier: bool) -> None:
    """保存直後のラウンドトリップ自己検査。ORT と tail の予測が一致しない保存は作らない（読めない保存の防止）。"""
    sess = _session(path)
    rng = np.random.default_rng(_CHECK_SEED)  # 明示 seed（グローバル種は使わない）
    x = rng.standard_normal((_CHECK_ROWS, n_features)).astype(np.float32)
    got = sess.run(None, {sess.get_inputs()[0].name: x})
    if classifier:  # 分類の出力は [label, probabilities] の順（zipmap=False・skl2onnx の規約）
        expected = np.asarray(tail.predict_proba(x), dtype=np.float64)
        actual = np.asarray(got[1], dtype=np.float64)
    else:
        expected = np.asarray(tail.predict(x), dtype=np.float64).reshape(-1)
        actual = np.asarray(got[0], dtype=np.float64).reshape(-1)
    if actual.shape != expected.shape:
        raise ValueError(f"ONNX 自己検査に失敗（出力の形 {actual.shape} が元の推定器 {expected.shape} と違う）")
    if not np.allclose(actual, expected, rtol=_CHECK_RTOL, atol=_CHECK_ATOL):
        raise ValueError(
            "ONNX 自己検査に失敗（InferenceSession と元の推定器の予測が一致しない。読めない/違う保存は作らない）。"
            f"最大差 {float(np.max(np.abs(actual - expected))):.3g}"
        )


def _onnx_dump(model: object, path: Path) -> None:
    """model（学習済み Pipeline）の to_numpy 尾部を ONNX へ変換し、契約 metadata＋自己検査つきで path に書く。

    atomic_write 経由で一時パスに書かれる（自己検査で失敗すれば一時ファイルごと消える＝不完全な保存は残らない）。
    """
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    from sklearn.base import is_classifier

    tail, feature_names = _split_at_to_numpy(model)
    if any(type(e).__module__.split(".")[0] == "lightgbm" for e in _flat_estimators(tail)):
        raise ValueError(
            "lightgbm 尾部は ONNX 形式の対象外（skl2onnx 標準に変換器が無い）。format='skops' か 'pickle' を使うこと"
        )
    n_raw = getattr(tail, "n_features_in_", None)
    if n_raw is None:
        raise ValueError(f"tail（{type(tail).__name__}）に n_features_in_ が無い（fit 済みの sklearn 推定器のみ対応）")
    n_features = int(n_raw)
    if feature_names and len(feature_names) != n_features:
        raise ValueError(f"境界の列名 {len(feature_names)} 列と tail の入力 {n_features} 列が食い違う（構成の誤り）")

    classes: NDArray[np.int64] | None = None
    if is_classifier(tail):
        classes = _classes_of(tail)
        prediction_kind = "proba" if len(classes) == 2 else "multiclass_proba"
        # zipmap=False：分類の出力を dict 列でなく label(n,)＋proba(n,k) の 2 テンソルにする（id はこの tail の分）。
        options: dict[int, dict[str, bool]] | None = {id(tail): {"zipmap": False}}
    else:
        prediction_kind = "value"
        options = None
    try:
        proto = convert_sklearn(tail, initial_types=[("input", FloatTensorType([None, n_features]))], options=options)
    except Exception as exc:  # 変換器の無い段（自作 transformer 等）＝対象外の構成。読めない保存を作る前に止める
        raise ValueError(f"ONNX 変換に失敗（tail={type(tail).__name__} に対応しない段が含まれる）: {exc}") from exc

    import onnx

    meta = {
        "feature_names": list(feature_names),
        "n_features": n_features,
        "input_dtype": "float32",
        "prediction_kind": prediction_kind,
        "classes": None if classes is None else [int(c) for c in classes],
        "source": _SOURCE,
    }
    onnx.helper.set_model_props(proto, {METADATA_KEY: json.dumps(meta)})
    onnx.save_model(proto, str(path))
    _self_check(path, tail, n_features=n_features, classifier=classes is not None)


def _onnx_load(path: Path) -> object:
    """指紋照合済みの ONNX ファイル（load_model が照合してから呼ぶ）を包んで返す。

    metadata_props の契約（METADATA_KEY の JSON）から prediction_kind を読み、OnnxClassifier / OnnxRegressor を選ぶ。
    壊れたファイル・契約 metadata 無し・source 不一致は ValueError。
    """
    sess = _session(path)
    raw = sess.get_modelmeta().custom_metadata_map.get(METADATA_KEY)
    if raw is None:
        raise ValueError(f"{path}: 契約 metadata（{METADATA_KEY}）が無い（harness.ds の保存でない ONNX は包めない）")
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: 契約 metadata が JSON として読めない: {exc}") from exc
    if meta.get("source") != _SOURCE:
        raise ValueError(f"{path}: 契約 metadata の source が {_SOURCE!r} でない（{meta.get('source')!r}）")
    kind = meta.get("prediction_kind")
    if kind in ("proba", "multiclass_proba"):
        return OnnxClassifier(sess, meta)
    if kind == "value":
        return OnnxRegressor(sess, meta)
    raise ValueError(f"{path}: 未知の prediction_kind {kind!r}（proba | multiclass_proba | value のいずれか）")


class _OnnxModel:
    """InferenceSession の薄い包み（入力正規化の共通部）。

    入力は polars DataFrame（feature_names で select→to_numpy）か numpy 互換の 2 次元配列（列数検査）。
    どちらも float32 に揃えて session へ渡す（契約 input_dtype="float32"）。
    """

    def __init__(self, session: Any, meta: Mapping[str, Any]) -> None:
        self._session = session
        self._input_name: str = session.get_inputs()[0].name
        self.feature_names: tuple[str, ...] = tuple(str(n) for n in meta.get("feature_names") or ())
        self.n_features: int = int(meta["n_features"])

    def _as_input(self, x: object) -> NDArray[np.float32]:
        if hasattr(x, "select") and hasattr(x, "columns"):  # polars DataFrame（duck typing・module top を軽く保つ）
            frame: Any = x
            if self.feature_names:
                missing = [c for c in self.feature_names if c not in frame.columns]
                if missing:
                    raise ValueError(f"入力に特徴量列が無い: {missing}（必要な列: {list(self.feature_names)}）")
                frame = frame.select(list(self.feature_names))
            arr = np.asarray(frame.to_numpy(), dtype=np.float32)
        else:
            try:
                arr = np.asarray(x, dtype=np.float32)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"入力を float32 の 2 次元配列にできない: {exc}") from exc
        if arr.ndim != 2 or arr.shape[1] != self.n_features:
            raise ValueError(f"入力の形 {arr.shape} が契約 (n, {self.n_features}) と合わない")
        return arr

    def _run(self, x: object) -> list[Any]:
        out: list[Any] = self._session.run(None, {self._input_name: self._as_input(x)})
        return out


class OnnxClassifier(_OnnxModel):
    """分類の ONNX 包み。classes_ / predict_proba / predict を持つ＝cv._predict・data predict がそのまま使える。"""

    def __init__(self, session: Any, meta: Mapping[str, Any]) -> None:
        super().__init__(session, meta)
        self.classes_: NDArray[np.int64] = np.asarray(meta["classes"], dtype=np.int64)

    def predict_proba(self, x: object) -> NDArray[np.float64]:
        """(n, k) の確率（float64・列順は classes_）。ONNX の 2 出力（label, probabilities）の 2 本目。"""
        return np.asarray(self._run(x)[1], dtype=np.float64)

    def predict(self, x: object) -> NDArray[np.int64]:
        """ラベル（int64・(n,)）。ONNX の label 出力そのまま（sklearn の predict と同じ値）。"""
        return np.asarray(self._run(x)[0], dtype=np.int64).reshape(-1)


class OnnxRegressor(_OnnxModel):
    """回帰の ONNX 包み。predict のみ（predict_proba を持たない＝cli の hasattr 分岐がそのまま効く）。"""

    def predict(self, x: object) -> NDArray[np.float64]:
        """予測値（float64・(n,)）。ONNX の (n, 1) 出力を cv._predict の value 契約（1 次元）に揃える。"""
        return np.asarray(self._run(x)[0], dtype=np.float64).reshape(-1)
