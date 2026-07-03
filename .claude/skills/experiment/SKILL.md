---
name: experiment
description: DS の実験（仮説検証・モデル比較・特徴量の効果確認）を始める際に自動参照。用意済みの部品（build_estimator・run_experiment・store）を config で組み合わせ、学習コードを書かない。実験・仮説・変種・比較・ベースライン・モデル評価の語で発火。
---

# experiment（実験＝1 仮説 1 フォルダ・部品は書かずに組む）

## 手順
1. 仮説を 1 つ決め、`work/…/E-xxxx-<短い説明>/` を作る（item.md は kind: experiment、SPEC.md に仮説と判定基準＝どの指標がいくつ動いたら採択）。
2. 直近の実験フォルダ（無ければ `work/EP-06-ds-experiment-loop/E-0001-interaction-feature/`）を丸ごとコピーし、**config.yaml だけを書き換える**。変種は variants 節（features / encode）で持つ。入力は `data` 節（`{kind: synthetic}` か `{kind: table, table_id: <ID>}`）・目的変数は `target`・モデルは `model` 節（`{kind: logreg, ...params}`）で選ぶ。モデル比較の実験は variant 側に `model` を書く。
3. 特徴量・エンコーダ・モデルは `uv run data blocks` / `data encoders` / `data models`（実データは `data list`）の一覧から kind を選んで config に書く。一覧に無い特徴量は features スキルへ。
4. code/train.py は**触らない**：config → `load_dataset` → `build_model` → `build_estimator` → `run_experiment` → store 保存 → results/ を一気通貫で回す雛形（e2e が毎回実行する正本）。入力・モデルも config で選ぶので手を入れる必要はない。
5. `python code/train.py --variant <名> --test` でスモーク → e2e テスト 1 本（subprocess で train.py を叩く）を足し、item の verified_by に明記して verify に接続。
6. 本規模を実行し、SPEC の判定基準どおり結論を results/summary.yaml に記録（負の結果も記録で done）。気づきは `docs/learnings.md` へ。

## 実験のあとで使う部品（入口・迷ったらここ）
- **閾値の選び方**：既定は `eval.select_threshold_max_f1`。運用の目標があるなら `eval.select_threshold_at_recall(..., target=)`（見逃し上限を決める）／`select_threshold_at_precision(..., target=)`（誤検知上限を決める）。**どれも OOF/valid で選ぶ**（train・test では選ばない）。
- **champion への昇格**：採択したら `models.promote_model(root, work=, name=, version=, thresholds=, primary=, higher_is_better=)`。絶対関門（`passes`）かつ相対関門（現 champion に primary で勝つ）を満たすときだけ champion を更新する（負けても保存は残る）。現状の一覧は `uv run data saved`（champion に ★）。
- **保存モデルを読む**：`models.load_model(root, name=, work=, version=None)`（再評価・推論。指紋・形式・依存版を検査してから読む）。version 未指定は最新。
- **最終評価（holdout）**：実験ループは全行 CV。最後に触っていない test での最終確認の段取りは未確定（ISS-0004・`data.fixed_split`／`cv.holdout_indices` を使う）。

## してはいけないこと
- CV・漏れ対策・メトリクス・保存・閾値選択を実験コードに再実装しない（run_experiment / run_cv / eval / store が正本）。
- 変種をコードの分岐で持たない（config の variants で持つ）。一度保存した fold 表を切り直さない。
- 閾値を train や test で選ばない（OOF で選ぶ）。`--test` の無い実験スクリプトを作らない。
