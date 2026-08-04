# -*- coding: utf-8 -*-
"""可写目录检测 — 独立模块，不依赖 biliopinion 包，避免循环导入。

Streamlit Cloud 上 /mount/src 只读，持久存储在 /mount/data。
"""
from __future__ import annotations

import os
from pathlib import Path


def writable_base() -> Path:
    """返回可写的根目录。"""
    # Streamlit Cloud 持久存储
    cloud_data = Path("/mount/data")
    if cloud_data.exists() and os.access(cloud_data, os.W_OK):
        return cloud_data / "biliopinion"
    # 本地开发
    return Path(__file__).resolve().parent.parent
