---
id: T-0198
kind: task
status: done
title: checks.toml のマーカー不変条件を起動時に検査し、満たさなければ verify を起動拒否する
created: 2026-07-10
depends_on: []
verified_by:
  - tests/test_verification_mechanism.py::test_checks_config_accepts_valid_config
  - tests/test_verification_mechanism.py::test_checks_config_rejects_marker_typo
  - tests/test_verification_mechanism.py::test_checks_config_rejects_missing_pytest_layer
  - tests/test_verification_mechanism.py::test_checks_config_rejects_missing_ruff
  - tests/test_verification_mechanism.py::test_checks_config_rejects_missing_mypy
  - tests/test_verification_mechanism.py::test_run_check_rejects_broken_config_before_pytest
---
# T-0198 checks.toml のマーカー不変条件（起動時 precondition）

## 何が問題か（実測済みの欠陥）
`checks.toml` はマーカー式つきの pytest コマンドを持つ（例 `pytest -q -m 'unit and not slow'`）。

1. `unit` を `unitt` と綴り間違えると、pytest は「該当テスト 0 件」を **終了コード 5** で返す。
   `checks.run_check` はこれを「この目印に該当するテストは無し＝合格」として読み飛ばす。
   結果、全テストが消えたまま verify が緑になる（fail-open）。
2. さらに、この typo を捕まえるはずの
   `tests/test_verification_mechanism.py::test_checks_toml_uses_only_registered_markers` は、
   モジュール冒頭の `pytestmark = pytest.mark.unit` で `unit` マーカーが付いている。
   **typo が起きたときに限って番人自身も deselect され走らない**。門番が門の内側に住んでいる。
3. `commands = []` に置換すると、verify は ruff/mypy/pytest ゼロで緑になる。CI も同じ入口。

## 設計
`checks.toml` の不変条件を、`run_check` の**冒頭**（pytest ではなく無条件に走る層）で検査し、
満たさなければ `ValueError` で**起動そのものを拒否**する。「検査した結果 0 件でした」ではなく
「そもそも走らせない」。実体は `checks._verify_checks_config(root)`。

不変条件（対象集合はツール自身の定数から機械的に導けるので、自己申告の台帳ではない）：
- `full` レベルまでに `ruff` と `mypy` が各 1 回以上現れる。
- pytest コマンドの `-m` 式に現れるマーカーの和集合が、テストの層（`testing.PYRAMID` の
  `unit` / `integration` / `e2e`）を被覆する。
- `-m` 式に現れるすべてのマーカーが `pyproject.toml` に登録済みである。

## やらないこと（と理由）
- **pytest の exit 5 の扱いを廃止しない**。複製先（非 DS 案件）は DS のテストを正当に消すので、
  層が正当に空になる。「tests/ が空でない限り失敗」にすると複製先にダミーテストを書かせることになる。
  マーカーの不変条件だけで typo 経路は閉じるので、exit 5 は残す。
- **`checks.toml` を廃止して定数に凍結しない**（このタスクでは）。複製先が段階を調整する余地を
  消すかどうかは別の判断（EP-31 の境界設計と関わる）。
- 頼まれた範囲の外は変更しない。

## 受け入れ基準
- マーカーを typo した `checks.toml` を与えると起動が拒否される（緑にならない）。
- `pytest` の行を丸ごと消した `checks.toml` を与えると拒否される（層の被覆に失敗）。
- `ruff` / `mypy` を消した `checks.toml` を与えると拒否される。
- 正しい `checks.toml`（このリポジトリの実物と同じ形）は通る。
- 検査は pytest のマーカー選択に依存しない層で効く（下記「番人が門の内側に住まない」で担保）。
- テストは tmp_path 上の `checks.toml`／`pyproject.toml` を使い、実リポジトリの値をハードコードしない。

## 番人が門の内側に住まないことの担保
不変条件の検査は pytest のテスト（マーカーで deselect され得る）ではなく、`run_check` の冒頭で
無条件に呼ばれる関数 `_verify_checks_config` に置いた。全 pytest テストが deselect されても
`run_check` はこの関数を必ず呼ぶ。`test_run_check_rejects_broken_config_before_pytest` は、
壊れた `checks.toml` を与えた `run_check` が **pytest のサブプロセスに到達する前に** `ValueError` で
落ちることを確かめる（＝マーカー選択の上流で効いている証拠）。

## ミューテーション実測
入れた guard を実際に外して、対象テストが RED になることを実測した（終わったら戻し、緑を確認済み）。

- ミューテーション A（配線を外す）：`run_check` 冒頭の `_verify_checks_config(root)` 呼び出しを削る。
  → `test_run_check_rejects_broken_config_before_pytest` が RED（1 failed / 10 passed）。
  ＝検査が「無条件に走る層」に配線されていることの裏付け（配線を外すと守れない）。
- ミューテーション B（判定ロジックを無効化）：`_verify_checks_config` を `checks.toml` 存在確認の直後で
  `return` させ、不変条件の判定を全て飛ばす。
  → `test_checks_config_rejects_marker_typo` / `..._rejects_missing_pytest_layer` /
  `..._rejects_missing_ruff` / `..._rejects_missing_mypy` / `test_run_check_rejects_broken_config_before_pytest`
  の 5 件が RED（5 failed / 6 passed。正常設定を通す `..._accepts_valid_config` は緑のまま）。
  ＝3 つの不変条件それぞれが実際に効いていることの裏付け。

いずれも復元後に `pytest tests/test_verification_mechanism.py` 11 passed を再確認した。

## 実測結果
- `uv run verify` 全成功（PM 検査 14 件通過＋ruff/mypy/pytest 全段階緑）。
- `uv run doc-sync`「変更なし（すでに最新）」。この guard は `PM_CHECKS` でも `checks.toml` の
  コマンドでもなく `run_check` 冒頭の precondition なので、`docs/core.md` の生成物には現れない。
