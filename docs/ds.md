# ds — データサイエンス（表データの学習）のプロファイル

表形式のデータからモデルを学習し、評価して、採用版（champion）に選ぶまでを支える一式のプロファイル。
用意済みの部品（特徴量・モデル・評価指標・交差検証〔データを分けて繰り返し評価する方法〕など）を設定ファイル（config）で組み合わせて実験を回し、
学習コードそのものは書かない。この基盤で機械学習の実験・モデル作りをする人が、**何があり・どこを見ればよいか**を
つかむための地図（この 1 枚）。手順そのものや細かい契約は、ここからリンクする各正本に置く（ここには再掲しない）。

実装は `src/harness/ds/`（どのファイルが何を担い・どう組まれ・今後どう広がるかは `docs/ds-code.md`）。依存は `uv sync --extra ds` で入れる。設計の芯は「業界標準を再発明しない」：
評価指標・交差検証（データを分けて繰り返し評価する方法）・前処理は scikit-learn、数値計算は numpy を使い、
config で差し替えるのは**モデルの種類**と**保存形式**だけ。

## 学習の流れ（全体像→どこにあるか）

1. **テーブルを定義する** … 列・型・キーを YAML で書く。置き場は `docs/data/`。一覧 `uv run data list`、
   定義の検査 `uv run data lint`。
2. **データを見る（探索）** … 1 つの表の要約は `uv run data profile`、2 群の比較は `uv run data compare`。
   進め方は eda スキル（`.claude/skills/eda/`）。
3. **特徴量を組む** … 特徴量ブロックとエンコーダ（値の変換）を config で選ぶ。使えるものの一覧は
   `uv run data blocks` / `uv run data encoders`。新しく作るか既存を使うかの判断は features スキル。
4. **実験する** … 仮説ごとに config を 1 つ書き、実験の雛形（`templates/experiment/`）が
   「設定 → 学習 → 評価 → 保存」を一気に回す。config に書けるモデル・特徴選択・ハイパラ探索・評価指標の一覧は
   `uv run data models` / `data selectors` / `data tuners` / `data metrics`。データ源は `uv run data sources`。
   手順は experiment スキル。
5. **変種を比べて選ぶ** … 変種ごとの結果を集めた表（リーダーボード）は `uv run data experiments`。
   合否は config で宣言した閾値（合格ライン）で決める。
6. **保存して champion に採用する** … champion＝現在採用している版。採用は `value_threshold`（宣言した閾値を
   満たす）と `change_threshold`（今の champion より主要指標が良い）を両方満たしたときだけ。判定の一覧と
   名前の出典は `uv run gates`。採用は `uv run data promote --work <ID> --name <名> --version <版> --primary <指標>
   --threshold 名=値`（落ちたら非ゼロ終了・理由をメッセージに）。現 champion は `uv run data champion --work <ID>
   --name <名>`、保存済みの一覧は `uv run data saved`（champion に ★）。保存形式は既定が pickle、可搬な ONNX は
   `uv run data formats`。
   - **間違えたら戻す（切り戻し）** … champion が本番で劣化していたと後で分かったら
     `uv run data rollback --work <ID> --name <名> --reason "なぜ戻すか"` で前の champion へ戻す。切り戻しは昇格では
     ないので判定を通さない（劣る旧良版へ戻せる）。昇格・却下・切り戻しの記録は
     `uv run data promotions --work <ID> --name <名>` で古い順に辿れる（却下も監査のため残る）。
7. **配信する / まとめて予測する** … 実時間の予測 API は serve プロファイル（`docs/serve.md`）。
   保存済みテーブルへ一括で予測を出すバッチ推論は `uv run data predict`。
8. **監視する** … 配信後の分布のずれ（ドリフト）の監視は `uv run data monitor`。ずれの大きさは
   安定/要注意/大変化の 3 段で読む。再学習まで含む運用の閉ループは ops プロファイル（`docs/ops.md`）。

このほかの部品：教師なし学習（クラスタリング・埋め込み・異常検知）は
`uv run data unsupervised` / `cluster` / `embed` / `anomaly`。時系列予測は `src/harness/ds/forecast.py`。

## もっと知りたいとき（各正本への案内）

- **コードの役割・構成・今後の方向**（どのファイルが何を担うか・拡張ポイント）… `docs/ds-code.md`。
- **進め方・考え方**（端まで通る最小の実装を先に作る、実験の回し方の思想）… `docs/method.md`。
- **手順（How-to）** … experiment（実験の回し方）・eda（探索）・features（特徴量の足し方）の各スキル。
- **テーブル定義の書き方・置き場** … `docs/data/`（定義の YAML）と `uv run data lint`。
- **部品の一覧はコマンドから見る**（このページに書き写さない）… `uv run data --help` が窓口。一覧は機械が
  カタログから生成するので、常に実装と一致する。

配信・運用まで含めた位置づけ：ds で作った champion を serve が配信し（`docs/serve.md`）、ops が
CI・再学習・監視の閉ループでまわす（`docs/ops.md`）。ds はその最初の「モデルを作って選ぶ」ところを担う。
