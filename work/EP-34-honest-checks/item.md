---
id: EP-34
kind: epic
status: in-progress
plan: detailed
requirements: []
depends_on: []
created: 2026-07-10
---
# EP-34 検査の抜け道を塞ぐ（honest checks）

## 目的
`uv run verify` の各検査には「理由を書けば止めてよい、書かなければ止めるな」という共通のルールがある
（skip・xfail は ISS 参照必須）。このルールを迂回できる経路が見つかったら、同じ理屈（理由不要で
「テストを永久に回さない」効果を持つものは、skip/xfail と同格に理由必須にする）で塞ぐ。

## 最初の実測（T-0202 の背景）
テストの層を示すマーカーに `slow`（重い）がある。`checks.toml` の全 3 段階（fast/standard/full）が
`not slow` で除外しており、`slow` を回す段階も CI job も無い。一方 skip・xfail は ISS 参照必須
（理由の無い skip 禁止）。`slow` は理由不要で同じ「永久に回らない」効果を持つ＝抜け道。

## この束でやらないこと
`slow` を回す CI job は足さない。実測で `slow` マーカー付きテストは 0 件（T-0202 時点）であり、
0 件の集合に pytest job を足すと `exit 5`（該当テストなし）で空回りする。「該当 0 件＝合格」の
job は何の保証にもならない。回す段階が要るようになったとき（実際に `slow` を使うテストが増えたとき）
に改めて判断する。
