---
id: T-0296
kind: task
status: done
closed: 2026-07-30
start: 2026-07-30
due: 2026-07-30
effort_days: 1
requirements: []
depends_on: [EP-50]
verified_by:
  - tests/test_headless.py::test_chrome_locator_covers_mac_and_windows
---
# T-0296 ブラウザ実測テストを Windows でも動く構成にする（ISS-0018）
依存ホバーの実測テストは Chrome を実ブラウザとして使う。ロケータ（`tests/_headless.py`）が macOS の場所しか
知らず、Windows では Chrome を見つけられず skip していた（ubuntu では PATH の `google-chrome` を拾えて既に実行・
pass）。ロケータに **Windows の既定パス**（`C:\Program Files\Google\Chrome\Application\chrome.exe` 等）を足し、
Mac・Windows・Linux のどこでも見つかる構成にする。CI ランナーは ubuntu も windows も Chrome を標準搭載なので、
「CI に Chrome を入れる」作業は不要（探し方を直すだけ）。Chrome の無い環境だけ skip にフォールバックする。

## 受け入れ基準
- [x] ロケータの既定パスに macOS（.app）と Windows（chrome.exe）の両方があり、Linux は PATH 名で拾う。
- [x] Chrome のある環境（Mac・CI の両 OS）では実測が走り、無い環境だけ skip。
