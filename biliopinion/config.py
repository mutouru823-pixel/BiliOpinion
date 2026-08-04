# -*- coding: utf-8 -*-
"""配置加载：YAML → 深度合并默认值 → 校验 → 路径与 Cookie 解析。"""
import os
import copy
from pathlib import Path

import yaml

from .defaults import DEFAULTS

REPO_ROOT = Path(__file__).resolve().parent.parent


def _writable_base() -> Path:
    """返回可写的根目录。

    Streamlit Cloud 上 /mount/src 是只读的，持久存储在 /mount/data。
    本地环境直接用 REPO_ROOT。
    """
    import os
    cloud_data = Path("/mount/data")
    if cloud_data.exists() and os.access(cloud_data, os.W_OK):
        return cloud_data / "biliopinion"
    return REPO_ROOT


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并；override 中的 None 视为未设置。"""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load_dotenv(path: Path) -> None:
    """极简 .env 解析，不引入额外依赖。已存在的环境变量优先。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


class Config(dict):
    """点号访问的配置容器。cfg['crawl']['max_videos'] 与 cfg.crawl['max_videos'] 等价。"""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e

    # ---- 常用派生路径 ----
    @property
    def out_root(self) -> Path:
        return Path(self["_paths"]["out_root"])

    @property
    def dir_data(self) -> Path:
        return Path(self["_paths"]["data"])

    @property
    def dir_fig(self) -> Path:
        return Path(self["_paths"]["figures"])

    @property
    def dir_raw(self) -> Path:
        return Path(self["_paths"]["raw"])

    @property
    def topic(self) -> str:
        return self["project"]["topic"]


def load_config(path: str | os.PathLike) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    user_cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = _deep_merge(DEFAULTS, user_cfg)

    # ---- topic / keywords 互相兜底 ----
    proj = cfg["project"]
    crawl = cfg["crawl"]
    if not proj.get("topic"):
        if crawl.get("keywords"):
            proj["topic"] = str(crawl["keywords"][0])
        else:
            raise ValueError("请在配置中至少填写 project.topic 或 crawl.keywords")
    if not crawl.get("keywords"):
        crawl["keywords"] = [proj["topic"]]
    if isinstance(crawl["keywords"], str):
        crawl["keywords"] = [crawl["keywords"]]

    if not proj.get("name"):
        proj["name"] = "event"

    # ---- Cookie：配置 > 环境变量 > .env ----
    _load_dotenv(REPO_ROOT / ".env")
    if not crawl.get("cookie"):
        crawl["cookie"] = os.environ.get("BILI_COOKIE", "").strip()

    # ---- 路径 ----
    out_dir = Path(proj["output_dir"])
    if not out_dir.is_absolute():
        out_dir = _writable_base() / out_dir
    out_root = out_dir / proj["name"]
    paths = {
        "repo": str(REPO_ROOT),
        "out_root": str(out_root),
        "raw": str(out_root / "raw"),
        "data": str(out_root / "data"),
        "figures": str(out_root / "figures"),
        "config_file": str(path.resolve()),
    }
    for key in ("out_root", "raw", "data", "figures"):
        Path(paths[key]).mkdir(parents=True, exist_ok=True)
    cfg["_paths"] = paths

    # ---- 轻量校验 ----
    tp = cfg["topics"]
    if tp["mode"] == "codebook":
        cats = tp["codebook"]["categories"]
        if not cats:
            raise ValueError("topics.mode=codebook 时必须提供 topics.codebook.categories")
        order = tp["codebook"]["order"] or list(cats.keys())
        unknown = [c for c in order if c not in cats]
        if unknown:
            raise ValueError(f"topics.codebook.order 中存在未定义的类别: {unknown}")
        tp["codebook"]["order"] = order

    if cfg["phases"]["mode"] == "manual" and not cfg["phases"]["manual"]:
        raise ValueError("phases.mode=manual 时必须提供 phases.manual 列表")

    return Config(cfg)


def dump_effective_config(cfg: Config) -> None:
    """把实际生效的完整配置写入输出目录，保证分析可复现。"""
    plain = {k: v for k, v in cfg.items() if k != "_paths"}
    target = cfg.out_root / "effective_config.yaml"
    target.write_text(
        yaml.safe_dump(plain, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
