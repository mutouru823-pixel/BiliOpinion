# -*- coding: utf-8 -*-
"""
Step1 数据清洗与预处理 —— 复现论文 3.1 节标准
 1) 字段统一命名: comment_id / bv / parent_id / level / user_mid / user_name /
                  reply_to / text / likes / reply_count / created_at / crawl_time
 2) 时间标准化、提取 date；剔除时间或文本为空的记录
 3) 去除「回复 @xxx :」前缀、链接、B 站表情 [xxx]、无意义标点与多余空格
 4) 清洗后空文本 / 乱码剔除
 5) 输出全量有效集（网络/互动/时间序列）与去重集（词频/主题统计）
"""
from __future__ import annotations

import re
import numpy as np
import pandas as pd

from ..utils import robust_read_csv, get_logger, banner

log = get_logger()

COLS = ["comment_id", "bv", "parent_id", "level", "user_mid", "user_name",
        "reply_to", "text", "likes", "reply_count", "created_at", "crawl_time"]


def _clean_text(t: str, cfg: dict) -> str:
    cl = cfg["clean"]
    t = str(t)
    if cl.get("strip_reply_prefix", True):
        t = re.sub(r"^回复\s*@[^:：\s]+\s*[:：]\s*", "", t)
    if cl.get("strip_url", True):
        t = re.sub(r"https?://\S+|b23\.tv/\S+|www\.\S+", "", t)
    if cl.get("strip_emote", True):
        t = re.sub(r"\[[^\[\]]{1,12}\]", "", t)          # B 站表情 [doge] [笑哭]
    t = re.sub(r"@[\w\-\u4e00-\u9fff]+", "", t)
    t = re.sub(r"([!！?？。.,，~～\-—…]){3,}", r"\1\1", t)  # 压缩重复标点
    t = re.sub(r"\s+", " ", t).strip()
    return t


def run(cfg) -> dict:
    raw = cfg.dir_raw
    out = cfg.dir_data
    comments_file = raw / "comments.csv"
    if not comments_file.exists():
        raise FileNotFoundError(f"未找到原始评论 {comments_file}。请先运行 Step0 采集。")

    banner(f"Step1 清洗 · {cfg.topic}")
    df = robust_read_csv(comments_file, dtype=str)
    n_raw = len(df)

    # 归一化列名（兼容爬虫输出 schema：bvid/user_id/username/.../collected_at）
    rename = {"bvid": "bv", "user_id": "user_mid", "username": "user_name",
              "target_username": "reply_to", "content": "text",
              "like_count": "likes", "collected_at": "crawl_time"}
    df = df.rename(columns=rename)
    for c in COLS:
        if c not in df.columns:
            df[c] = ""
    df = df[COLS]

    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", format="mixed")
    df["likes"] = pd.to_numeric(df["likes"], errors="coerce").fillna(0).astype(int)
    df["reply_count"] = pd.to_numeric(df["reply_count"], errors="coerce").fillna(0).astype(int)
    df["level"] = pd.to_numeric(df["level"], errors="coerce")

    n_before = len(df)
    df = df.dropna(subset=["created_at", "text"])
    df = df[df["text"].str.strip() != ""]
    log.info("剔除时间/文本为空: %d 条（剩 %d）", n_before - len(df), len(df))

    df["text_clean"] = df["text"].apply(lambda t: _clean_text(t, cfg))
    min_len = cfg["clean"].get("min_length", 1)
    n_before = len(df)
    df = df[df["text_clean"].str.len() >= min_len]
    log.info("清洗后短文本剔除(<%d 字): %d 条", min_len, n_before - len(df))

    if cfg["clean"].get("drop_mojibake", True):
        n_before = len(df)
        df = df[~df["text_clean"].str.contains("\ufffd", na=False)]
        log.info("乱码评论剔除: %d 条", n_before - len(df))

    df["date"] = df["created_at"].dt.date

    df.to_csv(out / "comments_valid.csv", index=False, encoding="utf-8-sig")
    log.info("全量有效评论: %d 条 -> data/comments_valid.csv", len(df))

    df_dedup = df.drop_duplicates(subset=["text_clean"])
    df_dedup.to_csv(out / "comments_dedup.csv", index=False, encoding="utf-8-sig")
    log.info("去重后评论: %d 条 -> data/comments_dedup.csv", len(df_dedup))

    log.info("时间范围: %s ~ %s", df["created_at"].min(), df["created_at"].max())
    log.info("层级分布:\n%s", df["level"].value_counts().to_string())

    return {
        "stats": {
            "raw_comments": int(n_raw),
            "valid_comments": int(len(df)),
            "dedup_comments": int(len(df_dedup)),
            "date_min": str(df["created_at"].min()),
            "date_max": str(df["created_at"].max()),
            "level_dist": {str(k): int(v) for k, v in df["level"].value_counts().items()},
        },
        "figures": [],
        "data_files": ["comments_valid.csv", "comments_dedup.csv"],
    }
