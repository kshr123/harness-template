---
id: EP-51
kind: epic
status: done
plan: detailed
requirements: []
depends_on: [EP-50]
---
# EP-51 クロスプラットフォーム是正（ISS-0018 / ISS-0019）

「Mac でも Windows でも同じに動く構成」にする。ISS-0018（ブラウザ実測テストが Windows で skip）と
ISS-0019（`\` 区切りに依存する残存箇所・doclint 免除の広さ）を潰す。設計は fable、実装は本セッション。

## 含む作業
- T-0296 ブラウザ実測テストを Windows でも動く構成にする（Chrome ロケータに各 OS の既定パス＝ubuntu/windows の
  CI ランナーは Chrome 標準搭載なので、パスを足すだけで Windows CI でも実測が走る）。CI に Chrome を「入れる」
  作業は不要だった（既に在る）。
- T-0297 リポ相対パスの `\` 依存を潰す（`as_posix()` 統一・5 箇所）＋再発防止の機械検査（conventions 規則5）＋
  doclint の案件領域免除をセグメント境界一致に厳密化（`*` が `/` を跨がない・OS で挙動が変わらない）。

## 含めない
- 非 ID の案件領域パス（例 `work/README.md`）の二重すり抜けは、免除台帳を二重化しないため今回は塞がず記録のみ
  （ISS-0019 に判断を明記）。
