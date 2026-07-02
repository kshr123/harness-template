# 実行環境を固定する（誰の手元でも・どのマシンでも同じ結果になるようにする）。
# 依存は uv.lock の通りに厳密にそろえる（再現性）。
FROM python:3.14-slim-bookworm

# uv（依存・環境管理ツール）を公式イメージから取り込む。
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# まず依存だけを同期する（ソースを変えても依存の層を再利用できる＝ビルドが速い）。
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# ソースを入れて、プロジェクト自身も同期する。
COPY . .
RUN uv sync --frozen

# 既定は共通の検証コマンド（完了＝すべて成功）。
CMD ["uv", "run", "verify"]
