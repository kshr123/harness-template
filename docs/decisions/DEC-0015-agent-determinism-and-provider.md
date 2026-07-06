---
id: DEC-0015
status: accepted
date: 2026-07-06
---
# DEC-0015 agent プロファイルの決定性は effort 固定＋記録再生で作る（temperature は使えない）・プロバイダ既定は Anthropic

## 状況（何を決める必要があったか）
LLMOps プロファイル `harness.agent`（EP-22）は「宣言（AgentSpec）→評価→合否→昇格」を verify に接続する。
verify は決定的・無ネットワークが前提（AGENTS の完了規約）。ところが現行の Claude モデル
（Opus 4.7/4.8・Sonnet 5・Fable 5）は **`temperature`/`top_p`/`top_k` がパラメータごと廃止**され、
**送ると 400 エラー**になる。旧来の「`temperature=0` で出力を決定的にする」手はもう使えない。
エージェント評価の決定性をどこで作るか、またプロバイダ抽象（PROVIDERS）の既定をどこに置くかを
正本として決める必要があった。

## 検討した選択肢
- A：temperature 相当の決定性ノブを AgentSpec に残し、対応プロバイダだけで使う（非対応モデルでは無視/変換）。
- B：**決定性はハーネス側の 2 軸で作る**：(a) `effort`（low/medium/high/xhigh/max）を AgentSpec の一部として
  **宣言に固定**する（サンプリングの決定性ではなく「同じ宣言＝同じ推論条件」の再現性）、(b) verify では実 API を
  **一切叩かず**、dummy（決定的合成応答）と cassette（記録再生・T-0092）だけで回す。モデル出力自体の
  非決定性は許容し、分散は本番監視（T-0093）で見る。
- プロバイダ：C：複数プロバイダを最初から実装する／D：**差し替え軸（PROVIDERS レジストリ）だけ用意し、
  実装は Anthropic Claude 1 社**（既定モデル `claude-opus-4-8`・高頻度/低コスト用は `claude-sonnet-5`）。

## 決定と理由
**B＋D を採用**。理由：
- A は「送ると 400」の現実に反する（存在しないノブを宣言に残すと、宣言が嘘をつく）。AgentSpec は
  `temperature` を**持たない**（load_agent_spec は `temperature` キーを明示エラーで弾き、effort への
  移行を案内する）。
- verify の決定性は入力側で作るのが唯一確実：dummy は入力メッセージ＋seed の正準 JSON ハッシュから
  応答を導く（グローバル種禁止・ネットワーク 0 をテストで遮断）。実応答の形状ドリフトは cassette
  （記録が無ければ fail closed）で無ネットワークのまま検知する（T-0092）。
- 複数プロバイダの同時実装は過剰設計（DEC-0012＝必要時に即）。差し替え口（PROVIDERS・extras_hint で
  `uv sync --extra agent` を案内）だけ先に切っておけば、2 社目は登録 1 件で足りる。

## 影響（良い点・悪い点・これからやること）
- 良い点：verify が課金・ネットワーク・モデル揺らぎから完全に独立する。宣言（AgentSpec）が実 API の
  受け付ける語彙と一致する（400 になるパラメータを持たない）。
- 悪い点：モデル出力の非決定性は残る（golden set の実測スコアは揺れうる）。→ 緩和：合否は閾値ゲート
  （passes・fail closed）で見る・分散は本番監視の関心に置く（門番にしない・ds monitor と同じ思想）。
- これからやること：T-0092 で AnthropicProvider（遅延 import・verify 経路外）＋CassetteProvider を足す。
  effort の実 API への渡し方（thinking/effort パラメータ対応）は T-0092 で SDK の語彙に合わせて確定する。
  関連 [[DEC-0004]] [[DEC-0006]] [[DEC-0013]] [[DEC-0014]]。
