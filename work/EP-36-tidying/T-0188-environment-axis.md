---
id: T-0188
kind: investigation
status: done
title: 検査の環境を軸にできるか調べる（Python の版・extras を段階ごとに変えられるか）
created: 2026-07-10
depends_on: []
verified_by: []
---
## 結論（2026-07-11 実測。分ける価値は「無い」＝env-split はしない）

前提が変わっていた。「statsforecast は 3.14 の wheel が無い」は**部分的にしか正しくなかった**：

- **最新 statsforecast 2.0.3 は scipy<1.16 を固定**し、scipy 1.15 系に cp314 wheel が無いため sdist ビルドに
  落ちる。実測：`uv run --isolated --with statsforecast --python 3.14` は scipy 1.15.3 を Fortran コンパイラ
  （ifort/gfortran）でビルドしようとして失敗（コンパイラ不在）。ここまでは旧知見どおり。
- **しかし statsforecast 2.0.1＋scipy>=1.16 なら 3.14 で動く**（実測：`--with "statsforecast==2.0.1" --with
  "scipy>=1.16"` で `import statsforecast; from statsforecast.models import AutoARIMA` が成功。
  scipy 1.18・numba 0.66・numpy 2.4.6）。scipy は 1.16 以降に cp314 wheel があり、当リポの実 venv も既に scipy 1.18。
- **代償**：numba 0.66 が numpy を 2.4.x に頭打ちにする（当リポは現状 numpy 2.5.0）。`--all-extras` の verify では
  この cap が環境全体に及ぶ。

### 4 つの問いへの答え
1. 段階に環境の軸（版/extras）を持たせる形：`uv run --python 3.13 --extra … pytest -m …` は成立する（uv の機能で表現可能）。
   ただし今回は**使う必要がない**（下記）。
2. 「全部入りで監査」と「段階ごとに環境を変える」は両立する（監査＝全部入りのまま・実行だけ版を変える）。
   だが 3.14 で statsforecast が動くので、この複雑さを導入する動機が消えた。
3. CI での回し方（matrix / 二重 venv）：**保留**。分けないので不要。
4. **そもそも分ける価値があるか＝無い。** statsforecast は `scipy>=1.16` 制約（実質 `statsforecast>=2.0.1,<2.0.3` か
   scipy を明示）で 3.14 に載る。EP-30 の時系列は 3.14 に載る範囲で進める。「どの環境で緑か」を人が覚える必要
   （＝完了の定義が 1 本でなくなる）を負ってまで env-split する理由は無い。

### EP-30 への申し送り（実装タスクで決めること）
- 時系列は 3.14 単一環境で進める。`[timeseries]` extra に statsforecast を入れるなら `scipy>=1.16`（または
  `statsforecast>=2.0.1,<2.0.3`）を制約に付ける（2.0.3 を掴むと scipy<1.16 で 3.14 ビルドに落ちる）。
- **numpy の cap（numba 0.66→numpy 2.4.x）が `--all-extras` で環境全体に及ぶ点**を確認すること。当リポが
  numpy 2.5 固有挙動に依存していなければ受容可（cap を飲む）。受容できないなら statsforecast を諦め、
  既存の statsmodels 経路（`forecast.py` の `TS_MODELS`）に寄せる（これは既に 3.14 で動いている）。

# T-0188 環境の分離（調査）

## なぜ調べるか
EP-27 は「環境の分離」を掲げたが、どのタスクにも落ちていなかった。そして EP-30（時系列）が
**存在しないこの仕組みに依存している**：statsforecast は Python 3.14 の wheel が無く（実測。
`scipy<1.16` を固定していて、scipy 1.15 系に cp314 wheel が無いためビルドが要る）、3.13 なら動く。

現状 `checks.toml` は「段階 → argv の列」だけを持ち、環境の軸が無い。venv は単一で、
`ops/ci_lint.py` は `uv sync --all-extras`（全部入り）を要求する。「時系列だけ 3.13 で回す」は、
今の構造では実現できない。

## 何を答えるか（結論を `docs/` か本ファイルに記録して完了。verified_by は要らない）
1. `checks.toml` の段階に環境の軸（Python の版・extras）を持たせる形は、`uv` の機能でどう表現するか。
   `uv run --python 3.13 --extra timeseries pytest -m timeseries` は成立するか（実測する）。
2. 「全部入りで監査する」（L-016）と「段階ごとに環境を変える」は両立するか。監査は全部入りのまま、
   テストの実行だけ環境を分ける、で足りるか。
3. 分けた環境を CI でどう回すか（matrix にするのか、1 ジョブで 2 つの venv を作るのか）。
4. **そもそも分ける価値があるか**。statsforecast を諦める・別ライブラリで代替する方が安いのではないか。
   分けた瞬間に「どの環境で緑なのか」を人が覚える必要が出る（＝完了の定義が 1 本でなくなる）。
   4 の答えが「無い」なら、EP-30 の時系列は 3.14 に載る範囲に絞り、この投資はしない。

## 調べ方
実測を伴う調査にする（憶測で結論を書かない）。使い捨ての複製で `uv run --python 3.13` を試し、
`uv.lock` が壊れないか・`--all-extras` の監査と衝突しないかを確かめる。

## 完了条件
上の 4 つに、実測の証拠つきで答えが書かれていること。設計を決めるのはその後の別タスク。
