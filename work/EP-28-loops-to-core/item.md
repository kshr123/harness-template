---
id: EP-28
kind: epic
status: todo
plan: outline
requirements: [REQ-001]
depends_on: [EP-27]
created: 2026-07-10
---
# EP-28 loops を中核へ（止め方の無いループを作らせない）

## 経緯（自分の誤りの訂正）
かつて私は「loops は agent 固有に留める。反復の所有者が agent 内にしかない」と論じた。**これは誤り**で、
*誰がループを回すか*（手段）の区別を、*概念の区別*にすり替えていた。

ds にも同一プロセス内のループは実在する（`TUNERS` の optuna 試行・`k_scan`・変種の反復）。
ops の継続学習、serve の shadow から champion への昇格も同じ形。ループは中核の横断概念。

## 何を中核に置くか
ハーネスが所有するのは**反復そのものではなく、停止の宣言・判定・来歴**。

`src/harness/loops.py`：
- 宣言の語彙：`Trigger`（`time` | `event` | `manual`）・`Stop`（dataclass）・
  `InProcessLoop | ExternalLoop` の直和。
- ループ台帳：`Profile.loops`（各プロファイルが自分のループを申告する）。
- `loop_lint`：**止め方の宣言が無いループを verify で失敗にする**。これが core 昇格の唯一の実利。

実行時プロトコル `StopCondition` は消費が 1 か所（`agent/goal.py`）なので agent に残す。
**型の置き場としての降格は正しく、概念の否定として誤りだった。**

## レジストリにしないもの
`TRIGGERS` / `STOP_CONDITIONS` / `POLICIES` は **Registry にしない**。住人はいるが「名前 → 工場」の
解決点が無い（config が kind で選んで組み立てる対象ではない）。入口の無いカタログは嘘の入口になる。

`Stop(kind="gate", gate=...)` は `GATES` の kind 名を参照するだけ。合否の正本は `harness/gates.py`
1 か所に置き、二重化しない。

## 今の非対称（これを直すのが目的）
`schedule_lint` は agent の定期実行に停止の宣言を要求するが、`ci_lint` は `retrain.yml` に要求していない。
同じ「止め方の無いループ」が、片方だけ検査されている。
