---
id: T-0225
kind: investigation
status: done
title: statsforecast を要する時系列（パネル・conformal 区間）の扱いを T-0188 の結論で確定する
created: 2026-07-11
depends_on: [T-0188, T-0224]
verified_by: []
---
## 結論（2026-07-13・実測）
T-0188 の「環境を分ける価値なし」を受け、**パネル予測・conformal 区間は見送り**（実装しない）と決定。
根拠（再現手順つき）は EP-30 item.md「statsforecast（パネル予測・conformal 区間）の決定（T-0225）」に集約：
- statsforecast は 3.14 で依然不可（scipy<1.16 固定・再測定）。
- 代替 mlforecast 1.1.0／skforecast 0.23.0 は 3.14 で import 可だが、どちらもパネル（多系列）で
  現行 `ForecastLike`（単系列）と契約が違う。
- 消費者（多系列予測の実需要）が無く、載せると `ForecastLike` の多系列拡張という設計判断が要るため見送り。
  単系列の次数自動選択は auto_arima（T-0224）で賄えており当面の穴は無い。実需要が来たら別タスクで一体判断。

# T-0225 環境の軸の結論待ちの部分

## 何が問題か（実測 2026-07-11・PyPI JSON 直読）
statsforecast 2.0.3 は cp314 wheel も pure-python wheel も無く、`scipy < 1.16, >= 1.7.3` を固定している
（3.14 では scipy 1.15 系に cp314 wheel が無いのでビルドが要る）。「時系列だけ 3.13 で回す」は現構造では
できず、環境の軸は T-0188（調査）の結論待ち。一方 neuralforecast の「ray 依存で 3.14 不可」は既に古い：
ray 2.56.0 に cp314 wheel（macosx_arm64／manylinux x86_64・aarch64）が実在し、neuralforecast 3.2.0 は
pure-python（どちらも 2026-07-11 に PyPI で確認。import までは未確認）。

## やること（T-0188 の結論が出てから）
- **T-0188 が「環境を分ける価値あり」の場合**：statsforecast を分離環境の extra にし、パネル予測・
  conformal 区間・`cross_validation` を分離環境のテストで検証する（このとき本タスクを実装タスクに
  分割し直す）。
- **T-0188 が「価値なし」の場合**：3.14 に載る範囲で代替する（候補：mlforecast・skforecast・
  neuralforecast。**着手時に import と最小の学習まで実測**）か、パネル予測をやらないと決める。
  どちらでも、結論と根拠（何を諦め、何で代替したか）を EP-30 の item.md に日付つきで書く。

## やらないこと
- T-0188 の結論を先取りした実装（存在しない仕組みへの依存を増やさない）。
- 3.13 前提の コード・extra を今のリポジトリに入れること。

## 受け入れ基準
- どちらの分岐でも「決めた結論・根拠・日付」が item.md に残り、別の立場が根拠の実測
  （wheel の有無・import の可否）を同じ手順で再現できる。
- 実装まで進んだ場合は、住人が T-0224 と同じ契約（バックテストに載る・決定性・条件登録）を満たす。
- `uv run verify` 全成功。
