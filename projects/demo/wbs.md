---
project: demo
epics:
  - id: EP-01
    name: PM層の骨格
    plan: detailed
    status: in-progress
    requirements: [REQ-001]
  - id: EP-02
    name: 開発ループの残り
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

計画は時間で成熟する（ローリングウェーブ）。立ち上げでは粗い全体像だけを置き、
着手が近いエピックだけを直前に detailed 化する。outline のままは正常な余白。

- **EP-01 PM層の骨格（detailed）**：charter/wbs/tasks・STATUS 導出・孤児検出・共通の検証コマンド。
- **EP-02 開発ループの残り（outline）**：スキル一式・仕様駆動・TDD ゲート。着手時に具体化する。
- **EP-03 引き渡し・振り返り（outline）**：DoD 確認・friction の learnings 反映。
