"""置き場の切り替え設定（.harness/config.toml）を読む。

データ・課題・メタデータの保存先を URI で持ち、コードは置き場の違いを意識しない。
設定を変えるだけで手元と共有先を切り替える。この段階では設定の読み取りと既定値を提供し、
実際のアダプタ（ローカル／S3／DWH／GitHub Issues）は後続の段階で足す（インターフェースは固定）。
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

CONFIG_PATH = ".harness/config.toml"


class DataConfig(BaseModel):
    """データ実体の置き場。default_backend を既定にし、層ごとに上書きできる。"""

    model_config = ConfigDict(extra="forbid")

    default_backend: str = "local"
    # 名前付き backend の定義（例 {"local": {"uri": "file:data"}}）。
    backends: dict[str, dict[str, str]] = Field(default_factory=lambda: {"local": {"uri": "file:data"}})
    # 層ごとの backend 上書き（書いた層だけ。例 {"raw": "object"}）。
    layer: dict[str, str] = Field(default_factory=dict)

    def backend_for(self, layer: str) -> str:
        """その層に使う backend 名（層の上書きが無ければ既定）。"""
        return self.layer.get(layer, self.default_backend)

    def uri_for(self, layer: str) -> str:
        """その層の保存先 URI。backend 定義の uri を引く。"""
        name = self.backend_for(layer)
        return self.backends[name]["uri"]


class IssuesConfig(BaseModel):
    """課題の置き場。file:（ローカル）または github:owner/repo（GitHub Issues）。"""

    model_config = ConfigDict(extra="forbid")

    backend: str = "file:issues"


class MetadataConfig(BaseModel):
    """テーブル定義の正本の置き場。既定はリポジトリ内。"""

    model_config = ConfigDict(extra="forbid")

    uri: str = "file:docs/data"


class HarnessConfig(BaseModel):
    """.harness/config.toml 全体。無ければすべて既定。"""

    model_config = ConfigDict(extra="forbid")

    data: DataConfig = Field(default_factory=DataConfig)
    issues: IssuesConfig = Field(default_factory=IssuesConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)


def load_config(root: Path) -> HarnessConfig:
    """設定を読む。ファイルが無ければ既定を返す。壊れていれば pydantic が失敗にする。"""
    path = root / CONFIG_PATH
    if not path.is_file():
        return HarnessConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return HarnessConfig.model_validate(data)
