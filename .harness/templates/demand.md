<!-- 要求（demand）のテンプレート。1 件 1 ファイル。docs/demands/DEM-xxx.md にコピーして埋める。
     要求＝クライアントの「言葉・Why」（何が欲しい・何に困っている）。要件（REQ）＝それを満たすためにシステムが
     満たすべき「What・検証可能な条件」。両者を分けるのは ISO/IEC/IEEE 29148 の中核（StRS→SyRS/SRS）。
     要件（docs/requirements/REQ-xxx.md）の frontmatter の satisfies でこの ID を参照する
     （要求→要件→作業→検証のトレース）。却下・保留も消さず残す＝「なぜやらない/後回しか」が合意の証跡。 -->
---
id: DEM-xxx              # 一意・再利用しない
priority: should        # MoSCoW：must（必須）| should（推奨）| could（できれば）| wont（今回やらない）
status: received        # received（受領）| accepted（要件化した）| rejected（却下）| deferred（保留）
stakeholder: <発言者・役割>
source: <出所（会議名・日付・メール等）>
---
# DEM-xxx：<要求の短い名前>

## 要求（クライアントの言葉で・原文に近く）
<「〜したい」「〜が困っている」をそのまま。分析でなく、言われたことを書く。>

## 背景の業務課題（なぜこの要求が出るか）
<現状 As-Is → あるべき姿 To-Be の差。>

## 却下/保留の理由（rejected・deferred のときは必須）
<なぜ今回やらない/後回しか。合意の証跡として残す。>
