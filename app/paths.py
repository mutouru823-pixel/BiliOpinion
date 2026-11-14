# -*- coding: utf-8 -*-
"""可写目录检测 — 独立模块，不依赖 biliopinion 包，避免循环导入。

Streamlit Cloud 上 /mount/src 只读，持久存储在 /mount/data。
"""
from __future__ import annotations

import os
from pathlib import Path


CLOUD_DATA_DIR = Path("/mount/data")


def writable_base() -> Path:
    """返回可写的根目录。

    Streamlit Cloud 上 /mount/src 是只读的，持久存储在 /mount/data。
    本地环境直接用项目根目录。
    """
    if CLOUD_DATA_DIR.exists() and os.access(CLOUD_DATA_DIR, os.W_OK):
        return CLOUD_DATA_DIR / "biliopinion"
    return Path(__file__).resolve().parent.parent
