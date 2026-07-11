---
id: T-0226
kind: task
status: done
title: 配信予測×実績の答え合わせ（data score）＝入力が安定でも崩れた正解率を捉える
created: 2026-07-11
depends_on: []
verified_by:
  - tests/test_ds_scoring.py::test_perfect_binary_realized_matches_and_band_stable
  - tests/test_ds_scoring.py::test_degraded_binary_flags_big_change
  - tests/test_ds_scoring.py::test_regression_realized_and_lower_is_better_degradation
  - tests/test_ds_scoring.py::test_join_counts_from_set_overlap
  - tests/test_ds_scoring.py::test_conflicting_prediction_for_same_fingerprint_is_excluded
  - tests/test_ds_scoring.py::test_duplicate_actual_key_raises
  - tests/test_ds_scoring.py::test_reader_matches_serve_runtime_contract
  - tests/test_ds_scoring.py::test_issue_fingerprint_is_deterministic_and_metric_scoped
---
# T-0226 配信予測×実績の答え合わせ

## 何を作ったか
- `src/harness/ds/scoring.py`（純関数）：
  - `read_scored_predictions`＝予測 JSONL（docs/serve.md の契約）から input_fingerprint・予測・種類を集める。
    契約は `monitor._contract_error`＋input_fingerprint の存在を要求。壊れ行は 1 回警告して読み飛ばす（門番にしない）。
    version/role/since で絞れる。
  - `answer_check`＝input_fingerprint で実績テーブルと内部結合し、実測指標（`ds/eval` の evaluate 系へ委譲）と
    昇格時 metrics（約束）との delta・相対劣化・band を返す。task はログの prediction_kind から導く。
    同じ指紋で食い違う予測は除外（版混在の疑い・警告）。実績の鍵重複は ValueError・欠損は除外（警告）。
  - `score_issue_content`＝band=大変化の指標から決定的・冪等な起票内容（答え合わせ指紋）。
- `src/harness/ds/cli.py` に `data score`（champion を解決→その版の予測だけ読む→実績で答え合わせ→YAML。
  `--file-issue` で冪等起票・exit 0）と `_load_actuals`（.parquet/.csv）・`_file_score_issue`。
- docs：`docs/ops.md` に「答え合わせの閉ループ」節（保証しないことも明記＝L-022）・`docs/ds-code.md` に scoring.py。

## 受け入れ基準（すべて満たした）
- 実測指標がデータ構成から導ける（完全分離→accuracy 1.0・残差→rmse＝sqrt(14/3) 等）。
- 実測が約束から相対劣化 >= 0.10 で band=大変化（手計算と一致）。
- 突き合わせ数（matched/unmatched）が集合の重なりから導ける。
- serve が実際に書く行（`runtime.build_log_rows`）を読めて答え合わせできる（契約の両側一致）。
- 門番にしない（band は出すが exit code に載せない）。`uv run verify` 全成功。

## なぜこの形か
分布監視は入力のずれの代理。実測での答え合わせが無いと「入力は安定・正解率は崩壊」を誰も捉えない。
既存部品（PREDICTION_LOG_FIELDS 契約・eval・issues・fingerprint）の合成のみで、新しい監視ロジックを作らない。

## 独立レビュー（maker≠checker・2026-07-11）で直した実バグ
別セッションの reviewer が 7 件を指摘（全部再現手順つき）。門番にしない契約を壊す実バグを含む：
- **H1**：予測ログが空（昇格直後・未流入）だと ValueError で exit≠0 になり、CT の定期実行を毎回落としていた
  （かつエラー文が存在しない `--task` を案内）→ 空でも空の表を返し exit 0 に。CLI テスト追加。
- **M1/M2**：`model` が dict でない行・多クラス確率の長さ不揃いの行で crash → 「壊れ行は読み飛ばす」契約どおり skip に。
- **M3**：約束 0（rmse=0）からの悪化を「基準なし」に丸めて起票が盲目化 → 0 からの悪化は inf＝大変化として捉える。
- **M4**：NaN の予測/実績が sklearn を不透明に落とす → 予測は壊れ行 skip・実績 NaN は警告して除外。
- **H2/L1**：CLI の exit 0・冪等起票のテストが無かった → `tests/test_score_file_issue.py` を追加。約束と実測の
  指標が食い違う（未照合）ときの警告も追加。
いずれも `uv run verify` 全成功で確認。
