---
id: T-0090
kind: task
status: done
title: 評価スコアで昇格するライフサイクル（agent/store.py＝save/champion/promote_agent）
created: 2026-07-06
depends_on: [T-0089]
verified_by: [tests/test_agent_store.py::test_promote_agent_absolute_and_relative_gates]
---
# T-0090 評価スコアで昇格するライフサイクル（agent/store.py）

## 狙い（LLMOps の中核＝「評価に通った宣言」を champion に昇格）
T-0089 で宣言→採点→合否まで一巡した。次は **保存＋昇格**：eval に通った `AgentSpec` を版として保存し、
絶対関門（passes）＋相対関門（現 champion に primary で勝つ）を満たすときだけ champion に昇格する。
ML の `ds/models.py`（champion/promote_model）と**同じ形**だが、プロファイル境界（DEC-0004）を守り
`ds.models` を import せず **独立モジュール**として書く（研究 N-8 の結論。`harness.storage` の一次部品だけ再利用）。
**非対称**：agent の実体は宣言 YAML そのもの＝学習済みバイナリが無いので FORMATS（保存形式の差し替え口）は要らない
（manifest に spec を config として畳み込む・DEC-0006 の非対称）。

## 受け入れ基準（新規 `src/harness/agent/store.py`・`harness.storage` を再利用・`ds` を import しない）
- **`AgentRecord`**（frozen dataclass）：`name/work/version/spec(dict)/metrics(dict[str,float])/
  prompt_fingerprint(str)/created(str)/path(Path)`＋来歴 `git: dict|None`・`lock_fingerprint: str|None`（後方互換で既定 None）。
  `AgentPromotion`（frozen）：`work/name/version/decided/primary/higher_is_better/metrics/previous_version`
  （ds の `Promotion` と同形だが agent 独立の型・ds を import しないため）。
- **保存先**：`work/<work>/agents/<name>/<version>/manifest.yaml`（作業単位に同居＝AGENTS「意味のある 1 まとまり」。
  version は UTC タイムスタンプ・再利用しない＝ds と同じ規約）。バイナリ実体ファイルは無い（宣言が実体）。
- **`save_agent(root, spec, *, work, name, metrics) -> AgentRecord`**：版ディレクトリを作り（既存なら拒否＝版は再利用しない）、
  manifest を `storage.write_manifest`（atomic）で書く。manifest 内容＝spec の dict（config）＋metrics＋
  `prompt_fingerprint`（system_prompt の sha256＝`storage.fingerprint` 相当・どのプロンプトで測ったかの印）＋
  git 来歴＋python/依存＋created。`load_agent`/`list_agents` も対に用意（`_record_from_manifest` 相当）。
- **`champion(root, *, work, name) -> AgentRecord | None`**：promotions/*.yaml の最新が指す版（無ければ None）。ds 同型。
- **`promote_agent(root, *, work, name, version, thresholds, primary) -> AgentPromotion`**：
  - primary は `AGENT_METRICS` に登録済みであること（未登録は ValueError）。向きの正本は `AGENT_METRICS[primary].higher_is_better`。
  - **絶対関門**：`agent.eval.passes(record.metrics, dict(thresholds))` が True（fail-closed は T-0089 の passes 準拠）。
  - **相対関門**：champion があれば primary で向き通りに勝つこと（higher_is_better なら `>`）。負け/同点は昇格しない。
  - 満たせば `promotions/<decided>.yaml` を追記し `AgentPromotion` を返す。関門で落ちたら ValueError（門番＝ここは exit を止める・
    監視の「門番にしない」とは別の関心＝昇格は明示ゲート）。
- **CLI 導線（DEC-0009）**：`cli.py` に `agent promote --work --name --version --primary <指標> --threshold <名=値>...`・
  `agent champion --work --name`・`agent experiments --results <dir>`（変種比較＝`ds.experiment.leaderboard` を
  **遅延 import で再利用**。leaderboard は polars＋yaml の純関数で ds 特有型に非依存。CLI 経路なので重い import 可）。
- **導線更新**：`docs/agent.md` に「保存→昇格→champion→experiments」の節と CLI 例。`experiment` スキルに
  「LLM エージェントの変種比較も同じ手順（`uv run agent experiments`・昇格は `uv run agent promote`）」を 1〜2 行。

## この骨組みでやらないこと（soon・理由つき）
- **golden set の store テーブル化（`role: eval`）は soon**：昇格に必要なのは eval metrics であって、それは
  `run_agent_eval`（T-0089）が cases から算出済み。store テーブル化はスキーマ定義（`docs/data/*.yaml`＋layer/scope/role）を
  伴い範囲が広がるので、昇格ライフサイクルが緑になってから別スライスで足す（YAGNI・順序の問題）。cases は当面 YAML/JSON で渡す。
- `promote_model` のパラメータ化（`metrics=`）は**しない**：ds.models を agent 用に一般化すると `_model_dir`/FORMATS まで
  巻き込みプロファイル境界を汚す（研究 N-8）。gate ロジック ~25 行の複製は profile 独立を保つための許容コスト
  （agent.eval.passes の複製と同じ扱い＝3 箇所目が出たら軽い core への `passes` 昇格を DEC 化）。

## 触ってよいファイル
`src/harness/agent/store.py`（新規）・`src/harness/agent/cli.py`（promote/champion/experiments 追加）・
`docs/agent.md`（追記）・`.claude/skills/experiment/SKILL.md`（1〜2 行）・
`tests/test_agent_store.py`（新規）＋必要なら `tests/test_agent_e2e.py`（昇格まで通すスモーク 1 本追記）。
`ds/**`・`serve/**` は変更しない（`ds.experiment.leaderboard` は読むだけ＝遅延 import で再利用）。

## 検査（テスト先書き・構成から導く・マーカー必須）
- `test_agent_store.py::test_promote_agent_absolute_and_relative_gates`（**unit** or **integration**）：
  - save→未 champion で絶対関門だけ効く：metrics が閾値以上なら promote 成功・未満なら ValueError（構成した metrics から導く）。
  - 2 版目：primary で現 champion に勝つ版だけ昇格・負け/同点版は相対関門で ValueError。
  - `champion` が最新昇格版を返す・昇格記録の向きは AGENT_METRICS 由来（引数の思い違いに依らない）。
- save/load ラウンドトリップ（**unit**）：保存した spec/metrics が load で一致・`prompt_fingerprint` が system_prompt を変えると変わる（構成から）。
- 未登録 primary は ValueError（**unit**）。
- e2e（**e2e**）：spec→`run_agent_eval`→`save_agent`→`promote_agent`→`champion` が一巡（ネットワーク 0・dummy provider）。
- `agent experiments` が metrics_*.yaml を集約して表示（**integration**・合成 results ディレクトリ）。
- 期待値は metrics の構成から導く（金メッキ禁止）。`uv run verify` 全体緑。`verified_by` の名がテストに実在。

## 独立レビュー（maker≠checker・差分のみ・実測・変異）
実装は fable。レビューは別文脈・別モデル（Opus）が差分のみを実測・変異で確認（APPROVE）。
- **相対関門の向き（最重要）＝変異で確認**：`store.py` の相対判定を 2 通り変異（`>`→`>=`／`if direction` 反転）。
  どちらも `test_promote_agent_absolute_and_relative_gates` が RED（劣位版・同点版が昇格しないことをテストが実際に捕捉）。
  変異は毎回バイト同一に復元。向きは `AGENT_METRICS[primary].higher_is_better` 由来で引数に無い＝呼び手の思い違いで劣位版が昇格する事故を構造的に排除。
- **絶対関門＋fail-closed**：閾値未達（0.6<0.7）で相対比較前に ValueError。NaN・primary 欠落も不合格（passes は T-0089 で fail-closed 確認済み）。
- **save の atomic 性・版の非再利用**：実体ファイルは無く manifest（write_manifest＝tmp→replace）が唯一かつ最後の書き込み＝存在が完了の印。同版は `exist_ok=False` で拒否（`test_same_version_is_rejected`）。時刻は `_utcnow` を monkeypatch で固定（グローバル種・実時刻レースに依らない）。
- **prompt_fingerprint**：`sha256(system_prompt)` の定義から導出（写経でない）。prompt を変えると必ず変わることを構成から確認。
- **プロファイル境界**：`store.py` に `harness.ds` の実行時 import なし（docstring 言及のみ）。ds 再利用は `agent experiments` CLI 内の遅延 import 1 箇所だけ。`import harness.agent.store` で anthropic/fastapi/uvicorn/polars/sklearn は未ロード（軽 import 維持）。
- **verify 全体緑**（`成功（すべて通過）`）。指摘なし。
