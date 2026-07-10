---
id: T-0177
kind: task
status: done
title: ドメイン語彙のレジストリは登録時に用語の出典を必須にする（造語の誕生を止める）
created: 2026-07-10
depends_on: [T-0176]
verified_by:
  - tests/test_registry.py::test_a_vocabulary_registry_refuses_a_name_without_a_source
  - tests/test_registry.py::test_source_is_optional_by_default
  - tests/test_gates.py::test_a_new_gate_cannot_be_registered_without_a_source
  - tests/test_gates.py::test_the_gates_catalog_shows_where_each_name_comes_from
---
# T-0177 名付けの瞬間に出典を要求する

## 何が問題か
「絶対関門」「相対関門」という造語は、docs で生まれたのではない。`work/EP-06/DESIGN.md` の
`promote_model` 設計、つまり**コードで名前を付ける瞬間**に生まれた。そのとき概念にはまだどこにも名前が
無く、名付けは避けられなかった。問題は名付けたことではなく、**出典の無い語を選べたこと**。
名前はエラーメッセージ → テストの `match=` → docs へと、正規の経路で拡散した。

禁止語の一覧を機械検査にしても、それは既に作られた語しか知らない。**次に作られる新語の第 1 号は必ず通る**。
検出は原理的に後追いなので、名付けの側を塞ぐ。

## 構造
`Registry.register` は既に「説明文が無ければ `ValueError`」で、部品を説明なしに登録できないようにしている。
同じ形を用語にも当てる：ドメイン語彙のレジストリは `require_source=True` で作り、
`register(..., source="…")`（その名前がどこから来たか）を必須にする。出典を書くには標準用語を調べるしか
なく、調査が名付けの瞬間に強制される。

`gates.py` の docstring に手書きしてある「用語の出所」節を、この構造へ移す。出典はカタログ
（`uv run gates`）に列として出るので、使う側も由来を辿れる。

`require_source` を付けるのは**名前そのものが新しい概念になるレジストリ**だけ。`MODELS` の kind は
sklearn の推定器名の写しなので不要（名前は既に外にある）。まず `GATES` に付ける。

## 何を止められないか（正直な限界）
- 偽の出典・標準用語の誤用は機械で確かめられない。ただし名付けが diff の 1 か所に集まるので、
  レビューは「出典が本物か」だけを見ればよくなる（レビュー観点として残す）。
- レジストリに載らない概念（散文の中だけで生まれる名詞）は止まらない。そこは T-0178（生成）が受け持つ。

## 受け入れ基準
- `require_source=True` のレジストリに `source` 無しで登録すると `ValueError`（空文字・空白のみも同じ）。
- `require_source=False`（既定）のレジストリは従来どおり登録できる。
- `uv run gates` の出力に、登録時に渡した出典の文字列がそのまま現れる。
- 既存の registry / catalog のテストが無変更で緑。
- `uv run verify` 全成功。
