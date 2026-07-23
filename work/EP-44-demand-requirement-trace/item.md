---
id: EP-44
kind: epic
status: done
plan: detailed
created: 2026-07-23
closed: 2026-07-23
requirements: []
depends_on: []
---
# EP-44 要求（DEM）→要件（REQ）の上流トレースを足す

コンサル層のバックボーン第2段。標準（ISO/IEC/IEEE 29148）が分ける「要求（クライアントの言葉・Why）」と
「要件（システムが満たす検証可能な条件・What）」を、この基盤に軽量に載せる。要件↔作業↔検証の鎖は既にあるので、
その上流（誰の要求から来たか）を繋ぐ。

## 変更（T-0244）
- 要求層 `docs/demands/DEM-*.md`（要件 REQ と同型の軽量ファイル＝frontmatter＋本文）。雛形 `.harness/templates/demand.md`
  （MoSCoW 優先度・stakeholder・source・却下/保留理由）。
- 要件 `REQ` に `satisfies: [DEM-…]`（上流参照）。雛形に追記。
- `pm.lint`（task-lint）に参照検査：REQ の `satisfies` が実在 DEM を指すこと（要件→作業の参照検査と対称・上流側）。
  要求層を持たない案件は satisfies を書かなければ何も要求されない。
- 案件領域の単一正本（EP-42 の `CASE_AREA_ROOTS`）に `docs/demands` を追加＝init-project の白紙化・merge 復旧の
  両方が自動追随（既存の双方向検査が強制）。
- 自リポで dogfood：`docs/demands/DEM-001`（3者充足の要求）を作り `REQ-001` が satisfies する（鎖が実リポで通ることを実証）。

## 位置づけ
鎖：要求 DEM → 要件 REQ（satisfies）→ 作業 work（requirements）→ 検証 verified_by。RTM（トレーサビリティ表）は
将来この鎖から生成ビューとして出す（手維持の表は作らない）。
