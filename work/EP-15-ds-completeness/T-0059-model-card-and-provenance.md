---
id: T-0059
kind: task
status: done
title: モデルカード＋来歴（manifest に git commit/branch/dirty＋lock 指紋・model_card レンダラ）
created: 2026-07-06
depends_on: [T-0047]
verified_by:
  - tests/test_ds_models.py::test_manifest_records_git_provenance_and_lock_fingerprint
  - tests/test_ds_models.py::test_provenance_is_none_outside_git_and_without_lock
  - tests/test_ds_models.py::test_old_manifest_without_provenance_keys_reads_as_none
  - tests/test_ds_models.py::test_model_card_contains_key_fields
  - tests/test_ds_models.py::test_model_card_without_provenance_shows_placeholder
---
# T-0059 モデルカード＋来歴

## 背景
参考リポ（実践MLOps metadata.py）は git commit/branch・依存・計算資源を保存する。当リポは manifest に**来歴**
（どのコード・どのロックで作られたか）を足し、`model_card(record)` で人・エージェントが 1 目で読める要約を出す
（監査・再現の担保）。DS 監査 P2・ideal-build-plan §参考。

## 受け入れ基準
- `save_model` の manifest に追加（後方互換＝古い manifest も読める。読み側は `.get(..., default)`）：
  - `git`：`{"commit": <短縮 sha>, "branch": <名>, "dirty": <bool>}`。**git リポでない/git 不在なら None**（`subprocess`
    の失敗を握って落とさない＝保存は止めない）。commit は `git rev-parse --short HEAD`、branch は `--abbrev-ref HEAD`、
    dirty は `git status --porcelain` が非空か。cwd は保存先 root（or リポ探索）。認証情報は読まない。
  - `lock_fingerprint`：`uv.lock` があれば storage.fingerprint（sha256）、無ければ None。どのロックで作ったかの印。
- `ModelRecord` に `git: dict|None` と `lock_fingerprint: str|None` を追加（`_record_from_manifest` も対応・古い manifest は None）。
- `model_card(record: ModelRecord) -> str`：name/version/format/fingerprint/data_fingerprint/主要 metrics/python/
  主要依存/git 来歴/created を人向けに整形した複数行文字列（構造化・読みやすさ優先）。エージェントが元コードを読まず
  使えるよう docstring＋（可能なら）`data card <name>` の導線は別途でよいがレンダラは実装する。

## 触ってよいファイル
`src/harness/ds/models.py`（manifest 追加・ModelRecord 拡張・model_card）＋`tests/test_ds_models.py`。
`pipeline.py`/`tune.py`/`eval.py`/`cv.py` は触らない（並行作業あり）。

## 検査（テスト先書き・構成から導く）
- 保存した manifest に git フィールドが載る（当リポは git リポなので commit は非空文字列・dirty は bool）。型・キーの存在を検査
  （具体 commit 値はハードコードしない＝環境依存を写経しない）。
- lock_fingerprint：uv.lock がある構成で sha256（64 桁 hex）・無い構成で None（一時ディレクトリで対比）。
- 古い manifest（git/lock キー無し）を読んでも `load_model`/`_record_from_manifest` が None 埋めで落ちない（後方互換）。
- `model_card` が record の主要フィールドを文字列に含む（name・version・fingerprint・metrics の 1 つ等・構成から）。

## 独立レビュー（2026-07-06・maker≠checker）
セキュリティ（shell=True 無し・引数固定リスト・cwd/timeout・.env 非参照・悪意 branch 名でも yaml 安全）と後方互換
（古い manifest を None 埋めで読む）を実測で確認。important 1：`dirty` 判定が利用者のグローバル git 設定
（status.showUntrackedFiles）に依存＝環境で意味が変わる/テストが他環境で落ちうる → `git status --porcelain --untracked-files=normal`
を明示（環境非依存に）。minor：model_card に feature_names 件数を追加、subprocess+fit の git テストを integration へ降格
（unit 二重マーカー解消）。lock 探索の root 限定は現運用で許容（記録）。

## 結果
実装・独立レビュー（dirty の環境非依存化を反映）・verify 緑で done。参考リポ metadata 取り込み＝ideal-build-plan Wave 3・§参考。
