---
project: demo
epics:
  - id: EP-01
    name: プロジェクト管理の骨格
    plan: detailed
    status: in-progress
    requirements: [REQ-001]
  - id: EP-02
    name: 開発の進め方の残り
    plan: outline
    status: todo
    requirements: []
  - id: EP-03
    name: 引き渡し・振り返り
    plan: outline
    status: todo
    requirements: []
---
# WBS：demo

計画は近い作業だけ先に詳しくする。立ち上げでは全体の見出しだけを粗く置き、
着手が近いエピックだけを、その直前に詳しく分解する。まだ分解していない状態は正常。

- **EP-01 プロジェクト管理の骨格（detailed）**：charter/wbs/tasks・STATUS の自動算出・参照チェック・共通の検証コマンド。
- **EP-02 開発の進め方の残り（outline）**：スキル一式・仕様に沿った進め方・テスト先行の判定。着手時に詳しくする。
- **EP-03 引き渡し・振り返り（outline）**：完了の定義の確認・気づきの learnings への反映。
