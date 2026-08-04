# -*- coding: utf-8 -*-
"""
将旧版爬虫产出的数据（含中文表头 / 旧列名）转换为 BiliOpinion 新 schema。

旧 comments.csv（无表头）:
  comment_id, bv, parent_id, level, user_mid, user_name, reply_to,
  text, likes, reply_count, created_at, crawl_time
旧 videos.csv（中文表头）:
  视频bvd, 视频标题, 说明, 用户昵称, 播放量, 评论量, 发布时间, ...

新 schema（与 crawler.py 输出一致，带英文表头）:
  comments: comment_id, bvid, parent_id, level, user_id, username,
            target_username, content, like_count, reply_count, created_at, collected_at
  videos:   bvid, title, desc, author, view_count, reply_count, pubdate, collected_at

用法: python tools/convert_legacy.py <旧bilibili_data目录> <输出raw目录>
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd

COMMENT_OLD = ["comment_id", "bv", "parent_id", "level", "user_mid", "user_name",
               "reply_to", "text", "likes", "reply_count", "created_at", "crawl_time"]
COMMENT_NEW = ["comment_id", "bvid", "parent_id", "level", "user_id", "username",
               "target_username", "content", "like_count", "reply_count",
               "created_at", "collected_at"]
COMMENT_MAP = {"bv": "bvid", "user_mid": "user_id", "user_name": "username",
               "reply_to": "target_username", "text": "content",
               "likes": "like_count", "crawl_time": "collected_at"}

VIDEO_OLD = ["视频bvd", "视频标题", "说明", "用户昵称", "播放量", "评论量", "发布时间", ""]
VIDEO_NEW = ["bvid", "title", "desc", "author", "view_count", "reply_count", "pubdate", "collected_at"]
VIDEO_MAP = {"视频bvd": "bvid", "视频标题": "title", "说明": "desc", "用户昵称": "author",
             "播放量": "view_count", "评论量": "reply_count", "发布时间": "pubdate"}


def _read_mixed(path: Path):
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        lines, n = [], 0
        for ln in raw.split(b"\n"):
            try:
                lines.append(ln.decode("utf-8"))
            except UnicodeDecodeError:
                try:
                    lines.append(ln.decode("gbk")); n += 1
                except UnicodeDecodeError:
                    lines.append(ln.decode("utf-8", errors="replace"))
        if n:
            print(f"  注：{path.name} 有 {n} 行按 GBK 解码")
        return "\n".join(lines).lstrip("\ufeff")


def _buf(path: Path) -> io.StringIO:
    """把容错解码后的文本包成 file-like，供 pandas 读取"""
    return io.StringIO(_read_mixed(path))


def main():
    if len(sys.argv) < 3:
        print("用法: python tools/convert_legacy.py <旧数据目录> <输出raw目录>")
        return 2
    src = Path(sys.argv[1]); dst = Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)

    # comments（无表头）
    c = pd.read_csv(_buf(src / "comments.csv"), header=None,
                    names=COMMENT_OLD, dtype=str, engine="python", on_bad_lines="skip")
    c = c.rename(columns=COMMENT_MAP)[COMMENT_NEW]
    c.to_csv(dst / "comments.csv", index=False, encoding="utf-8-sig")
    print(f"comments.csv: {len(c)} 行 -> {dst / 'comments.csv'}")

    # videos（中文表头）
    v = pd.read_csv(_buf(src / "videos.csv"), dtype=str, engine="python",
                    on_bad_lines="skip")
    v.columns = [str(col).strip() for col in v.columns]
    v = v.rename(columns=VIDEO_MAP)
    for col in VIDEO_NEW:
        if col not in v.columns:
            v[col] = ""
    v = v[VIDEO_NEW]
    v.to_csv(dst / "videos.csv", index=False, encoding="utf-8-sig")
    print(f"videos.csv: {len(v)} 行 -> {dst / 'videos.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
