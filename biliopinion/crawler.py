# -*- coding: utf-8 -*-
"""
Step0 数据采集：按关键词搜索 B 站视频，穷尽抓取一级 + 二级评论。

相对原型脚本的改进：
  1. Cookie 从配置 / 环境变量注入，不再硬编码在源码里
  2. WBI 签名密钥进程内缓存，不再每次搜索都重新拉取
  3. bvid → aid 映射缓存，翻页时不再重复请求
  4. 统一 UTF-8-SIG 表头输出；断点续爬（视频级 + 评论 ID 级双重去重）
  5. 支持多关键词、发布时间过滤、可配置限速
"""
from __future__ import annotations

import csv
import os
import re
import time
import urllib.parse
from datetime import datetime
from functools import reduce
from hashlib import md5
from pathlib import Path

import requests

from .utils import get_logger

log = get_logger()

VIDEO_COLS = ["bvid", "title", "desc", "author", "view_count", "reply_count", "pubdate", "collected_at"]
COMMENT_COLS = ["comment_id", "bvid", "parent_id", "level", "user_id", "username",
                "target_username", "content", "like_count", "reply_count",
                "created_at", "collected_at"]

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

_RE_REPLY_AT = re.compile(r"^回复\s*@([^:：\s]+)\s*[:：]")


class BilibiliCrawler:
    def __init__(self, cfg):
        self.cfg = cfg
        c = cfg["crawl"]
        self.cookie = (c.get("cookie") or "").strip()
        if not self.cookie:
            raise RuntimeError(
                "未提供 B 站 Cookie。请在 .env 中设置 BILI_COOKIE=... "
                "或在配置文件 crawl.cookie 中填写。获取方式见 docs/GET_COOKIE.md"
            )

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
            "Referer": "https://www.bilibili.com",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Cookie": self.cookie,
        })

        raw = Path(cfg["_paths"]["raw"])
        self.videos_file = raw / "videos.csv"
        self.comments_file = raw / "comments.csv"
        self.completed_file = raw / "completed_videos.txt"

        self._init_files()
        self.completed = self._load_lines(self.completed_file)
        self.seen_videos = self._load_col(self.videos_file)
        self.seen_comments = self._load_col(self.comments_file)
        if self.seen_comments:
            log.info("断点续爬：已有 %d 个视频、%d 条评论", len(self.seen_videos), len(self.seen_comments))

        self._wbi_keys: tuple[str, str] | None = None
        self._aid_cache: dict[str, int] = {}
        self.video_buf: list[list] = []
        self.comment_buf: list[list] = []
        self.buffer_size = 1000

    # ------------------------------------------------------------------ IO
    def _init_files(self):
        self.videos_file.parent.mkdir(parents=True, exist_ok=True)
        for f, cols in ((self.videos_file, VIDEO_COLS), (self.comments_file, COMMENT_COLS)):
            if not f.exists():
                with open(f, "w", newline="", encoding="utf-8-sig") as fh:
                    csv.writer(fh).writerow(cols)

    @staticmethod
    def _load_lines(path: Path) -> set:
        if not path.exists():
            return set()
        return {ln.strip() for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines() if ln.strip()}

    @staticmethod
    def _load_col(path: Path, col: int = 0) -> set:
        out = set()
        if not path.exists():
            return out
        try:
            with open(path, "r", encoding="utf-8-sig", errors="ignore", newline="") as fh:
                r = csv.reader(fh)
                next(r, None)
                for row in r:
                    if row:
                        out.add(row[col].strip())
        except Exception as e:  # noqa: BLE001
            log.warning("读取历史记录失败 %s: %s", path.name, e)
        return out

    def flush(self, force=False):
        if self.video_buf and (force or len(self.video_buf) >= self.buffer_size):
            with open(self.videos_file, "a", newline="", encoding="utf-8-sig") as fh:
                csv.writer(fh).writerows(self.video_buf)
            self.video_buf.clear()
        if self.comment_buf and (force or len(self.comment_buf) >= self.buffer_size):
            with open(self.comments_file, "a", newline="", encoding="utf-8-sig") as fh:
                csv.writer(fh).writerows(self.comment_buf)
            log.info("  已落盘，累计评论 %d 条", len(self.seen_comments))
            self.comment_buf.clear()

    # ------------------------------------------------------------ WBI 签名
    def _get_wbi_keys(self):
        if self._wbi_keys:
            return self._wbi_keys
        try:
            r = self.session.get("https://api.bilibili.com/x/web-interface/nav", timeout=10)
            d = r.json()
            if d.get("code") == 0:
                img = d["data"]["wbi_img"]
                ik = img["img_url"].rsplit("/", 1)[-1].split(".")[0]
                sk = img["sub_url"].rsplit("/", 1)[-1].split(".")[0]
                self._wbi_keys = (ik, sk)
                if not d["data"].get("isLogin"):
                    log.warning("Cookie 未通过登录校验，评论抓取可能受限或数据不全")
                return self._wbi_keys
            log.warning("获取 WBI 密钥返回异常 code=%s", d.get("code"))
        except Exception as e:  # noqa: BLE001
            log.warning("获取 WBI 密钥失败: %s", e)
        return None

    def _sign(self, params: dict) -> dict:
        keys = self._get_wbi_keys()
        if not keys:
            return params
        raw = keys[0] + keys[1]
        mixin = reduce(lambda s, i: s + raw[i], MIXIN_KEY_ENC_TAB, "")[:32]
        params = dict(params)
        params["wts"] = round(time.time())
        params = dict(sorted(params.items()))
        filtered = {k: "".join(ch for ch in str(v) if ch not in "!*'()") for k, v in params.items()}
        query = urllib.parse.urlencode(filtered)
        filtered["w_rid"] = md5((query + mixin).encode()).hexdigest()
        return filtered

    # -------------------------------------------------------------- 搜索
    def search_videos(self, keyword: str, page: int) -> list[dict]:
        c = self.cfg["crawl"]
        params = {
            "search_type": "video",
            "keyword": keyword,
            "page": page,
            "order": c.get("order", "click"),
            "duration": 0,
            "tids_1": 0,
        }
        if c.get("pubtime_begin"):
            params["pubtime_begin_s"] = int(datetime.strptime(c["pubtime_begin"], "%Y-%m-%d").timestamp())
        if c.get("pubtime_end"):
            params["pubtime_end_s"] = int(datetime.strptime(c["pubtime_end"], "%Y-%m-%d").timestamp())

        try:
            r = self.session.get("https://api.bilibili.com/x/web-interface/wbi/search/type",
                                 params=self._sign(params), timeout=15)
            d = r.json()
        except Exception as e:  # noqa: BLE001
            log.error("搜索请求失败: %s", e)
            return []

        if d.get("code") != 0:
            log.error("搜索失败 code=%s msg=%s", d.get("code"), d.get("message"))
            return []

        out = []
        for item in (d.get("data", {}) or {}).get("result", []) or []:
            ts = item.get("pubdate", 0)
            out.append({
                "bvid": item["bvid"],
                "title": re.sub(r"</?em[^>]*>", "", item.get("title", "")),
                "desc": (item.get("description") or "").replace("\n", " ").strip(),
                "author": item.get("author", ""),
                "view": item.get("play", 0),
                "reply": item.get("review", 0),
                "pubdate": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "",
            })
        return out

    # -------------------------------------------------------------- 评论
    def bvid_to_aid(self, bvid: str):
        if bvid in self._aid_cache:
            return self._aid_cache[bvid]
        try:
            d = self.session.get("https://api.bilibili.com/x/web-interface/view",
                                 params={"bvid": bvid}, timeout=10).json()
            if d.get("code") == 0:
                aid = d["data"]["aid"]
                self._aid_cache[bvid] = aid
                return aid
            log.warning("  取 aid 失败 %s: code=%s", bvid, d.get("code"))
        except Exception as e:  # noqa: BLE001
            log.warning("  取 aid 异常 %s: %s", bvid, e)
        return None

    def _get_main_replies(self, aid: int, cursor: int) -> dict:
        # mode=2 时间排序：能拿到完整时间序列；mode=3 热度排序会截断
        try:
            d = self.session.get("https://api.bilibili.com/x/v2/reply/main",
                                 params={"type": 1, "oid": aid, "mode": 2,
                                         "next": cursor, "ps": 20}, timeout=15).json()
            return d.get("data") or {} if d.get("code") == 0 else {}
        except Exception as e:  # noqa: BLE001
            log.warning("  拉取一级评论失败: %s", e)
            return {}

    def _get_sub_replies(self, aid: int, root: int, pn: int) -> list:
        try:
            d = self.session.get("https://api.bilibili.com/x/v2/reply/reply",
                                 params={"type": 1, "oid": aid, "root": root,
                                         "pn": pn, "ps": 20}, timeout=15).json()
            return (d.get("data") or {}).get("replies") or [] if d.get("code") == 0 else []
        except Exception as e:  # noqa: BLE001
            log.warning("  拉取二级评论失败: %s", e)
            return []

    # -------------------------------------------------------------- 落库
    def save_video(self, v: dict):
        if v["bvid"] in self.seen_videos:
            return
        self.seen_videos.add(v["bvid"])
        self.video_buf.append([v["bvid"], v["title"], v.get("desc", ""), v["author"],
                               v.get("view", 0), v.get("reply", 0), v.get("pubdate", ""),
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        self.flush()

    def save_comment(self, c: dict, bvid: str, parent_id=0, level=1, parent_username=""):
        rpid = str(c.get("rpid", ""))
        if not rpid or rpid in self.seen_comments:
            return False
        try:
            msg = c["content"]["message"]
            target = ""
            if level == 2:
                m = _RE_REPLY_AT.match(msg)
                target = m.group(1).strip() if m else parent_username
            self.seen_comments.add(rpid)
            self.comment_buf.append([
                rpid, bvid, parent_id, level,
                str(c["member"]["mid"]), c["member"]["uname"], target, msg,
                c.get("like", 0), c.get("rcount", 0),
                datetime.fromtimestamp(c["ctime"]).strftime("%Y-%m-%d %H:%M:%S"),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ])
            self.flush()
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("  评论落库失败 rpid=%s: %s", rpid, e)
            return False

    # -------------------------------------------------------- 单视频抓取
    def scrape_video(self, bvid: str, title: str = "") -> int:
        aid = self.bvid_to_aid(bvid)
        if not aid:
            return 0

        c = self.cfg["crawl"]
        delay = c.get("request_delay", 0.5)
        rdelay = c.get("reply_delay", 0.3)
        max_rp = c.get("max_reply_pages", 0)

        total, page, cursor = 0, 0, 0
        while True:
            data = self._get_main_replies(aid, cursor)
            replies = data.get("replies") or []
            if not replies:
                break
            page += 1
            cur = data.get("cursor", {}) or {}

            for cm in replies:
                if self.save_comment(cm, bvid, 0, 1):
                    total += 1
                if cm.get("rcount", 0) > 0:
                    pn = 1
                    while True:
                        if max_rp and pn > max_rp:
                            break
                        subs = self._get_sub_replies(aid, cm["rpid"], pn)
                        if not subs:
                            break
                        for s in subs:
                            if self.save_comment(s, bvid, cm["rpid"], 2, cm["member"]["uname"]):
                                total += 1
                        pn += 1
                        time.sleep(rdelay)

            if cur.get("is_end"):
                break
            cursor = cur.get("next", 0)
            if not cursor:
                break
            time.sleep(delay)
            if page % 10 == 0:
                log.info("  ...第 %d 页，本视频累计新增 %d 条", page, total)

        self.flush(force=True)
        self.completed.add(bvid)
        with open(self.completed_file, "a", encoding="utf-8") as fh:
            fh.write(bvid + "\n")
        log.info("  ✓ %s 完成：%d 页 / 新增 %d 条", bvid, page, total)
        return total

    # ------------------------------------------------------------- 主流程
    def run(self) -> dict:
        c = self.cfg["crawl"]
        keywords = c["keywords"]
        log.info("搜索关键词: %s", " | ".join(keywords))

        found: dict[str, dict] = {}
        for kw in keywords:
            for p in range(1, c["max_pages"] + 1):
                vids = self.search_videos(kw, p)
                if not vids:
                    break
                for v in vids:
                    found.setdefault(v["bvid"], v)
                log.info("  「%s」第 %d 页 → %d 个视频（累计去重 %d）", kw, p, len(vids), len(found))
                time.sleep(c.get("request_delay", 0.5))

        if not found:
            raise RuntimeError("未搜索到任何视频。请检查关键词是否正确、Cookie 是否有效。")

        videos = sorted(found.values(), key=lambda x: -int(x.get("view") or 0))
        if c.get("max_videos"):
            videos = videos[:c["max_videos"]]

        log.info("待抓取视频 %d 个", len(videos))
        done, skipped, new_comments = 0, 0, 0
        for i, v in enumerate(videos, 1):
            self.save_video(v)
            if v["bvid"] in self.completed:
                skipped += 1
                continue
            log.info("[%d/%d] %s | %s | 播放 %s",
                     i, len(videos), v["bvid"], v["title"][:36], f"{v.get('view', 0):,}")
            new_comments += self.scrape_video(v["bvid"], v["title"])
            done += 1
            time.sleep(c.get("video_delay", 1.5))

        self.flush(force=True)
        stat = {"videos_found": len(found), "videos_scraped": done, "videos_skipped": skipped,
                "comments_total": len(self.seen_comments), "comments_new": new_comments}
        log.info("采集完成: %s", stat)
        return stat


def run(cfg) -> dict:
    return BilibiliCrawler(cfg).run()
