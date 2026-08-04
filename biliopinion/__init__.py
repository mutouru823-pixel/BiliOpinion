# -*- coding: utf-8 -*-
"""BiliOpinion —— 基于 B 站评论的舆情演化分析管线。

他人只需：① 填入想分析的舆情主题（如「鹅腿阿姨」）；② 填入自己的 B 站 Cookie，
即可在本地一键跑通：采集 → 清洗 → 时间演化 → 主题 → 情感立场 → 社会网络 → 报告。
"""
__version__ = "0.1.0"

from .config import load_config, Config  # noqa: F401
