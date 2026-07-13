"""PSIS-LOO によるベイズモデルの比較と採用（`harness.promotion` の作法を共有）。

LOO（Leave-One-Out 交差検証の PSIS 近似）は、点別の対数尤度から「新しい観測をどれだけうまく予測できるか」
（elpd）を推定する。**比べられるのはベイズモデル同士だけ**：ds の champion（GBM 等）と統計モデルのどちらを
配信するかは LOO では決められない（共通のホールドアウトで事後予測の点要約を採点するしかない）。この限界は
プロファイル跨ぎのブリッジを作らない判断の代償で、跨ぐ比較が実際に要ると分かった時点で見直す（docs/stats.md）。

採用は `harness.promotion.promote` に載せる（stats 専用の採用機構を作らない＝複製を 3 つ目にしない）。elpd_loo を
primary（大きいほど良い）に、value_threshold（下限）と change_threshold（現 champion からの厳密な改善）で判定する。
pymc/arviz は関数内で遅延 import する。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from harness import promotion
from harness.fingerprint import input_fingerprint
from harness.stats import store

PRIMARY_METRIC = "elpd_loo"  # LOO の期待対数予測密度（大きいほど良い＝予測が上手い）


def observed_fingerprint(model: Any) -> str:  # noqa: ANN401  pm.Model
    """モデルが抱く観測データの指紋。elpd は n 点の和なので、比較は同じ観測同士でしか意味を持たない
    （independent レビュー M1）。champion と候補で観測が違えば採用を止めるための鍵。

    観測は idata でなくモデルから取る（nutpie の InferenceData は observed_data 群を持たないため）。
    観測名でソートした対応を指紋にする（順序に依らず同じデータなら同じ指紋）。
    """
    obs = {rv.name: np.asarray(model.rvs_to_values[rv].eval()).ravel().tolist() for rv in model.observed_RVs}
    return input_fingerprint(dict(sorted(obs.items())))


def add_log_likelihood(model: Any, idata: Any) -> Any:  # noqa: ANN401  pm.Model/InferenceData
    """idata に log_likelihood 群を足す（無ければ計算する）。LOO は点別対数尤度が要る（nutpie は既定で出さない）。"""
    import pymc as pm

    if not hasattr(idata, "log_likelihood"):
        with model:
            pm.compute_log_likelihood(idata, progressbar=False)
    return idata


def loo(idata: Any, *, require_reliable: bool = False) -> float:  # noqa: ANN401  arviz.InferenceData
    """PSIS-LOO の elpd（期待対数予測密度・大きいほど良い）。log_likelihood 群が無ければ ValueError。

    require_reliable=True のとき、PSIS 近似が信頼できない（Pareto k が閾値超え＝ELPDData.warning）なら ValueError。
    採用の判断（adopt）では True にする＝当てにならない elpd で champion を差し替えない（うるさく失敗する側）。
    """
    if not hasattr(idata, "log_likelihood"):
        raise ValueError("log_likelihood 群が無い（先に add_log_likelihood で計算する）")
    import arviz as az

    result = az.loo(idata)
    if require_reliable and bool(getattr(result, "warning", False)):
        raise ValueError(
            "PSIS-LOO が信頼できない（Pareto k が閾値超え＝elpd の推定が当てにならない）。"
            "モデルを見直すか、より頑健な比較（refit LOO 等）を使うまで採用しない"
        )
    return float(result.elpd)


def compare_models(idata_map: Mapping[str, Any]) -> Any:  # noqa: ANN401  pandas.DataFrame
    """複数のベイズモデルを LOO で比較して順位表（arviz.compare）を返す。各 idata に log_likelihood が要る。

    rank 0 が最良（elpd 最大）。同じ観測に当てたモデル同士だけを比べること（LOO の前提）。1 つでは比較にならない。
    """
    if len(idata_map) < 2:
        raise ValueError("compare は 2 つ以上のモデルが要る（1 つでは順位づけにならない）")
    import arviz as az

    return az.compare(dict(idata_map))


def select_best(idata_map: Mapping[str, Any]) -> str:  # noqa: ANN401
    """LOO で最良（rank 0）のモデル名を返す。"""
    ranking = compare_models(idata_map)
    best = ranking.index[ranking["rank"] == 0]
    return str(best[0])


def adopt(
    root: Path,
    model: Any,  # noqa: ANN401  pm.Model
    idata: Any,  # noqa: ANN401  arviz.InferenceData
    *,
    name: str,
    work: str,
    version: str | None = None,
    thresholds: Mapping[str, float] | None = None,
    decided: str | None = None,
) -> promotion.Promotion:
    """推論結果を保存し、LOO の elpd を primary に harness.promotion で採用（昇格）判定する。

    log_likelihood を計算 → elpd_loo を求め → InferenceData を metrics つきで保存 → promotion.promote に載せる。
    初回は baseline が無いので change_threshold は課さない（有限性は問う）。2 回目以降は現 champion からの厳密な
    改善（elpd_loo が大きくなる）を要求する。却下は promotion.gates.PromotionError（記録は rejected で残る）。
    **同じ観測データ同士でしか比較しない**：champion と候補の観測の指紋が違えば ValueError（elpd は n 点の和で、
    別の観測に当てた elpd を比べても意味が無い＝M1）。**信頼できない LOO では採用しない**（Pareto k 超え→ValueError）。
    """
    add_log_likelihood(model, idata)
    elpd = loo(idata, require_reliable=True)  # 当てにならない elpd で champion を差し替えない（M2）
    data_fp = observed_fingerprint(model)
    ent = store.entity_dir(root, name=name)
    champion = promotion.champion_version(ent, label=name)
    if champion is not None:  # 現 champion があるなら、同じ観測に当てた版だけ比較する（M1）
        champ_manifest = store.version_manifest(root, name=name, version=champion)
        champ_fp = champ_manifest.get("provenance", {}).get("data_fingerprint")
        if champ_fp is not None and champ_fp != data_fp:
            raise ValueError(
                f"champion({champion})と候補で観測データが違う（data_fingerprint 不一致）。elpd_loo は同じ観測"
                "同士でしか比較できない（別データの elpd を比べても意味が無い）"
            )
    resolved_version = version if version is not None else datetime.now(UTC).strftime(store.VERSION_FORMAT)
    store.save_inference(
        root,
        idata,
        name=name,
        version=resolved_version,
        metrics={PRIMARY_METRIC: elpd},
        provenance={"work": work, "data_fingerprint": data_fp},
    )
    resolved_decided = decided if decided is not None else datetime.now(UTC).strftime(store.VERSION_FORMAT)
    return promotion.promote(
        store.entity_dir(root, name=name),
        work=work,
        name=name,
        version=resolved_version,
        label=name,
        candidate_metrics={PRIMARY_METRIC: elpd},
        thresholds=dict(thresholds) if thresholds else {},
        primary=PRIMARY_METRIC,
        direction=True,  # elpd は大きいほど良い
        directions={PRIMARY_METRIC: True},
        decided=resolved_decided,
    )
