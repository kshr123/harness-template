# SPEC E-0001 交互作用特徴量 x1*x2 で予測が改善するか

## 目的
仮説：baseline（x1, x2）に交互作用特徴量 x1*x2 を足すと、予測（ROC-AUC）が改善するか。
合成データは 1.5*x1 − 2*x2 + 雑音 の符号でラベルが決まる（線形）ので、交互作用は効かない見込み
＝「負の結果も記録で完了」の実地確認も兼ねる。

## 受け入れ基準
- baseline・interaction の 2 変種を同じ seed・同じ分割で回し、OOF の ROC-AUC を results に記録する。
- 判定：interaction の ROC-AUC が baseline を実質的に上回れば採択、そうでなければ棄却（どちらでも結論を記録して完了）。
- `--test` スモークが端から端まで通り、`uv run verify`（e2e）に含まれる。

## やらないこと
- 個別の標準変換（StandardScaler 等）の自作（sklearn を直接使う）。
- モデルのチューニング・複数モデルの比較（この実験は 1 仮説）。

## 最後の確認手順
- `python code/train.py --variant baseline --test` と `--variant interaction --test` が終了コード 0。
- 本規模（`--variant … `、--test なし）で results/metrics_*.yaml が両変種そろう。
- `uv run verify` にすべて成功する。
