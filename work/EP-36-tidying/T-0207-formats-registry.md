---
id: T-0207
kind: task
status: done
title: FORMATS を素の dict から Registry にする（名前と実体のずれを直す・未知形式エラーを 1 か所へ）
created: 2026-07-14
closed: 2026-07-14
depends_on: []
verified_by:
  - tests/test_ds_models.py::test_formats_is_a_registry_not_a_bare_dict
  - tests/test_ds_models.py::test_unknown_format_is_rejected_with_hint
  - tests/test_ds_models.py::test_format_roundtrip
---
## 実装（done）
- `harness.ds.models`：`ModelFormat`（素の dataclass）を `FormatEntry(Entry)` に置換し、`FORMATS` を
  `Registry[FormatEntry]("保存形式", catalog="data formats", extras_hint={"skops": "skops", "onnx": "onnx"})`
  にした。`FormatEntry` は `load`・`file_name` を持ち、`dump` プロパティで `factory` を別名公開する
  （`MetricEntry.fn` と同型＝呼ぶ側は `fmt.dump/load/file_name` のまま）。登録は `FORMATS.register(...)`
  （pickle は常時・skops/onnx は `find_spec` の条件登録）。dump に docstring が無いので description は明示で渡す。
- `save_model`：未知形式の手書きチェックを `fmt = FORMATS.resolve(format)` に置換。候補一覧＋カタログ案内＋
  extra 導入ヒントが resolve の 1 か所から出る（他の 9 レジストリと同じ）。版ディレクトリ作成の前に落ちる
  （fail closed・孤児ディレクトリを作らない）は維持。
- `load_model`：**NotImplementedError は保持**（保存の「引数が変」＝ValueError と、記録が指す形式がこの環境に
  「無い＝実現できない」＝NotImplementedError は別の状況で、別の型が正しい）。有効な形式集合の正本は
  `FORMATS`（Registry）1 か所から引く（`record.format not in FORMATS`）。
- `ds/cli.py` の formats カタログ：「FORMATS は素の dict」という古いコメントを訂正（file_name の列を足すので
  render_catalog でなく自前描画、という理由に）。Mapping なので `.items()` はそのまま効く。

## 何が問題だったか
`models.py` の docstring とコメントは `FORMATS` を「レジストリ」と呼ぶのに、実体は素の `dict[str, ModelFormat]`
だった（名前と実体のずれ＝この基盤が最も嫌う腐り方）。未知 kind のエラー文（候補一覧の再構成）が save と load の
2 か所に手書きで重複し、他の 9 レジストリが持つ「未知 kind は resolve の 1 か所」から外れていた。

## 受け入れ基準（満たした）
- `FORMATS` が `Registry` のインスタンス（`test_formats_is_a_registry_not_a_bare_dict`・実測で緑）。
- 未知形式の保存は resolve の統一メッセージ（候補一覧＋`uv run data formats` 案内）で拒否＋版ディレクトリ未作成。
- 全形式（optional 導入済みぶんを含む）で save→load の往復が動く（`test_format_roundtrip`）。

# T-0207 FORMATS を Registry にする

docstring は自ら「レジストリ」と名乗るのに実体は素の dict。未知 kind エラーが 2 か所に重複していた。
