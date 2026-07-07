"""CI テンプレート（templates/ci/）の構造 lint の器（EP-21 の歩く骨組み）。

GitHub Actions は実行しない・ネットワークも使わない。テンプレートは「利用者がコピーする雛形」なので
実行はできないが、構造（必須ファイルの存在・verify ゲートの参照整合）は静的に検査できる。
deploy_lint（templates/serve/ の構造 lint）と同型の「実行できない資産を verify で腐らせない」検査
（DEC-0009）。

この骨組みでは必須ファイル一覧（_REQUIRED）が空＝templates/ci/ が在っても何も指摘しない。
後続タスク（T-0111〜）が _REQUIRED に `.github/workflows/verify.yml` を足し、内容検査
（verify step の有無・Python 版・extras、CT の retrain.yml）をデータ駆動で増やす
（deploy_lint の _REQUIRED＋_check_* の増やし方と同じ）。

`templates/ci/` が無いプロジェクト（＝テンプレートを同梱しないコピー先の案件）では何も指摘しない
（誤検知しない）。依存は stdlib＋pyyaml のみに保つ（内容検査を足すとき yaml は関数内で遅延取り込み
＝deploy_lint と同じ規約。プロファイルのモジュールを軽く保つ＝DEC-0013）。
"""

from __future__ import annotations

from pathlib import Path

from harness import pm

# 必須ファイル（templates/ci/ からの相対）。骨組みでは空タプル。
# T-0111 で ".github/workflows/verify.yml"、T-0114 で retrain の雛形を足す（データ駆動の拡張点）。
_REQUIRED: tuple[str, ...] = ()


def run_checks(root: Path) -> list[pm.Problem]:
    """templates/ci/ の構造を検査し、指摘（error/info）を返す。root は自リポ or コピー先。"""
    base = root / "templates" / "ci"
    if not base.exists():
        return []  # テンプレートを同梱しないコピー先の案件＝検査対象外（誤検知しない）
    problems: list[pm.Problem] = []
    for rel in _REQUIRED:
        if not (base / rel).is_file():
            problems.append(
                pm.Problem(
                    "error",
                    f"templates/ci/{rel}: 必須ファイルが無い（複製先が CI verify ゲート無しで始まって"
                    "しまう。雛形を復元するか、同梱をやめるなら templates/ci/ ごと消す）",
                )
            )
    return problems
