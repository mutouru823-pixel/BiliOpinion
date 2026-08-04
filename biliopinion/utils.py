# -*- coding: utf-8 -*-
"""通用工具：日志、中文字体、分词与停用词、自动阶段划分、自动核心短语抽取。"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# 日志
# --------------------------------------------------------------------------
_LOG_READY = False


def get_logger(name: str = "biliopinion") -> logging.Logger:
    global _LOG_READY
    logger = logging.getLogger(name)
    if not _LOG_READY:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%H:%M:%S"))
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        _LOG_READY = True
    return logger


log = get_logger()


def banner(text: str) -> None:
    log.info("=" * 62)
    log.info(text)
    log.info("=" * 62)


# --------------------------------------------------------------------------
# 中文字体
# --------------------------------------------------------------------------
FONT_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/ukai.ttc",
]

_FONT_PATH: str | None = None


def setup_matplotlib(cfg=None) -> str | None:
    """配置 matplotlib 中文显示，返回可用于 WordCloud 的字体文件路径。"""
    global _FONT_PATH
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    if _FONT_PATH:
        return _FONT_PATH

    cands = []
    if cfg is not None:
        custom = (cfg.get("runtime", {}) or {}).get("font", "")
        if custom:
            cands.append(custom)
    cands += FONT_CANDIDATES

    for p in cands:
        if p and os.path.exists(p):
            try:
                fm.fontManager.addfont(p)
                plt.rcParams["font.family"] = fm.FontProperties(fname=p).get_name()
                _FONT_PATH = p
                break
            except Exception:
                continue

    if _FONT_PATH is None:
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "PingFang SC",
                                           "Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
        log.warning("未找到中文字体文件，图表中文可能显示为方框。可在 runtime.font 中指定 .ttf/.ttc 路径")

    plt.rcParams["axes.unicode_minus"] = False
    return _FONT_PATH


def font_path() -> str | None:
    return _FONT_PATH


def savefig(fig, path, dpi=150, **kw):
    import matplotlib.pyplot as plt
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches=kw.pop("bbox_inches", "tight"), **kw)
    plt.close(fig)
    return str(path)


# --------------------------------------------------------------------------
# 分词与停用词
# --------------------------------------------------------------------------
STOPWORDS = set("""
的 了 是 我 你 他 她 它 们 在 和 就 不 也 都 还 这 那 有 个 上 下 中 大 小 人 时 年 月 日
啊 吧 呢 吗 嘛 哦 呀 哈 呵 嗯 唉 哇 咯 啦 么 之 与 及 或 者 而 但 却 又 很 太 更 最 极
要 会 能 可 没 无 把 被 给 让 对 到 从 向 于 以 为 比 跟 同 关于 对于 通过 因为 所以 如果
但是 就是 不是 还是 我们 你们 他们 自己 别人 大家 现在 当时 后来 其实 显然 当然 以及 并且
或者 而且 表示 这个 那个 哪个 什么 怎么 这样 那样 一些 这种 那种 一个 一直 已经 可以 应该
觉得 知道 真的 只是 虽然 然后 出来 进去 起来 下去 上去 回来 过去 时候 东西 事情 地方 问题
感觉 意思 样子 看到 听到 想到 说到 有点 有些 非常 特别 十分 不能 不会 不要 不用 别的
这些 那些 怎样 如何 为什么 是不是 有没有 能不能 就算 反正 毕竟 居然 竟然 确实 的确
估计 可能 也许 大概 肯定 一定 绝对 根本 完全 简直 直接 天天 总是 经常 有时 突然 立刻
马上 终于 最后 首先 其次 另外 而已 罢了 来说 而言 不过 只能 只有 只要 除非 甚至 何况
难道 究竟 到底 真是 算是 还有 还能 还会 还在 都是 也是 又是 才是 更是 不然 要不 要是
即使 即便 哪怕 无论 不管 任何 所有 一点 一下 一样 一般 比较 相当 更加 越来越 没有 知乎
""".split())

# B 站语境下高频但低信息量的词
STOPWORDS |= {"视频", "评论", "弹幕", "回复", "up", "UP", "UP主", "up主", "doge", "楼主", "前排"}

_RE_NONWORD = re.compile(r"^[\d\W_]+$")


def tokenize(text: str, extra_stop: set | None = None, min_len: int = 2) -> list[str]:
    import jieba
    stop = STOPWORDS if not extra_stop else (STOPWORDS | extra_stop)
    out = []
    for w in list(jieba.cut(str(text))):
        w = w.strip()
        if len(w) < min_len:
            continue
        if w in stop:
            continue
        if _RE_NONWORD.fullmatch(w):
            continue
        out.append(w)
    return out


# --------------------------------------------------------------------------
# 自动传播阶段划分
# --------------------------------------------------------------------------
PHASE_TEMPLATE = ["P0潜伏期", "P1启动期", "P2高峰期", "P3衰减期", "P4二次发酵期", "P5长尾期"]


def detect_phases(daily: pd.Series, params: dict) -> list[dict]:
    """
    基于每日评论量自动识别传播阶段断点。

    daily: index 为 datetime.date、值为当日评论数的 Series（须按时间升序）
    返回: [{"name": "P1启动期", "start": date, "end": date, "days": n}, ...]

    算法：以全局峰值为基准，用相对比例阈值切出
      潜伏期 → 启动期 → 高峰期 → 衰减期 →（若后段出现次级高峰）二次发酵期 → 长尾期
    这样无论事件规模大小、时间跨度长短，都能得到结构可比的阶段划分。
    """
    daily = daily.sort_index()
    if len(daily) < 3:
        d0, d1 = daily.index.min(), daily.index.max()
        return [{"name": "P0全时段", "start": d0, "end": d1, "days": len(daily)}]

    vals = daily.values.astype(float)
    dates = list(daily.index)
    peak_i = int(np.argmax(vals))
    peak_v = vals[peak_i]

    r_start = params.get("start_ratio", 0.10)
    r_peak = params.get("peak_ratio", 0.50)
    r_decay = params.get("decay_ratio", 0.10)
    r_res = params.get("resurge_ratio", 0.20)

    # 启动期起点：峰值前最后一次由低于阈值转为高于阈值的位置
    i = peak_i
    while i > 0 and vals[i - 1] >= peak_v * r_start:
        i -= 1
    start_i = i

    # 高峰期起点 / 终点
    i = peak_i
    while i > start_i and vals[i - 1] >= peak_v * r_peak:
        i -= 1
    peak_lo = i
    i = peak_i
    while i < len(vals) - 1 and vals[i + 1] >= peak_v * r_peak:
        i += 1
    peak_hi = i

    # 衰减期终点：跌破 decay_ratio
    i = peak_hi
    while i < len(vals) - 1 and vals[i + 1] >= peak_v * r_decay:
        i += 1
    decay_hi = i

    # 二次发酵：衰减后是否出现次级高峰
    resurge = None
    if decay_hi + 2 < len(vals):
        tail = vals[decay_hi + 1:]
        j = int(np.argmax(tail))
        if tail[j] >= peak_v * r_res:
            abs_j = decay_hi + 1 + j
            a = abs_j
            while a > decay_hi + 1 and vals[a - 1] >= peak_v * r_decay:
                a -= 1
            b = abs_j
            while b < len(vals) - 1 and vals[b + 1] >= peak_v * r_decay:
                b += 1
            resurge = (a, b)

    segs: list[tuple[str, int, int]] = []
    if start_i > 0:
        segs.append(("P0潜伏期", 0, start_i - 1))
    if peak_lo > start_i:
        segs.append(("P1启动期", start_i, peak_lo - 1))
    segs.append(("P2高峰期", peak_lo, peak_hi))
    if decay_hi > peak_hi:
        segs.append(("P3衰减期", peak_hi + 1, decay_hi))
    if resurge:
        a, b = resurge
        if a > decay_hi + 1:
            segs.append(("P3b回落期", decay_hi + 1, a - 1))
        segs.append(("P4二次发酵期", a, b))
        if b < len(vals) - 1:
            segs.append(("P5长尾期", b + 1, len(vals) - 1))
    elif decay_hi < len(vals) - 1:
        segs.append(("P5长尾期", decay_hi + 1, len(vals) - 1))

    out = []
    for name, a, b in segs:
        if b < a:
            continue
        out.append({
            "name": name,
            "start": dates[a],
            "end": dates[b],
            "days": b - a + 1,
            "comments": int(vals[a:b + 1].sum()),
        })
    return out


def phases_from_manual(manual: list, dmin, dmax) -> list[dict]:
    """把 phases.manual 的 [{name, end}] 转换成与 detect_phases 相同的结构。"""
    out, cursor = [], pd.Timestamp(dmin).date()
    for item in manual:
        end = pd.Timestamp(item["end"]).date()
        out.append({"name": item["name"], "start": cursor, "end": end,
                    "days": (end - cursor).days + 1})
        cursor = end + pd.Timedelta(days=1)
        cursor = cursor.date() if hasattr(cursor, "date") else cursor
    last_end = pd.Timestamp(dmax).date()
    if cursor <= last_end:
        name = manual[-1].get("tail_name", "P_长尾期") if manual else "P_全时段"
        out.append({"name": name, "start": cursor, "end": last_end,
                    "days": (last_end - cursor).days + 1})
    return out


def assign_phase(dates: pd.Series, phases: list[dict]) -> pd.Series:
    """按阶段区间给每条评论打阶段标签。"""
    bounds = [pd.Timestamp(p["start"]) for p in phases] + [pd.Timestamp(phases[-1]["end"]) + pd.Timedelta(days=1)]
    labels = [p["name"] for p in phases]
    dt = pd.to_datetime(dates)
    return pd.cut(dt, bins=bounds, labels=labels, right=False, ordered=False).astype(object)


# --------------------------------------------------------------------------
# 自动核心短语抽取
# --------------------------------------------------------------------------
def extract_core_phrases(texts, top_n=24, extra_stop=None, min_len=2,
                         must_include=None, sample=60000, seed=42) -> dict:
    """
    从语料中自动抽取「核心语义短语」词典。

    与自由分词词云的差别：这里输出的是 {短语: [变体...]} 结构，后续统计一律采用
    「评论级计数」（一条评论出现多次只计 1 次），避免个别刷屏评论放大权重。

    评分 = 文档频率 × log(平均词长)，偏好既高频又具体的名词性短语。
    """
    from collections import Counter

    texts = pd.Series(texts).astype(str)
    if sample and len(texts) > sample:
        texts = texts.sample(sample, random_state=seed)

    df_counter = Counter()   # 文档频率（评论级）
    for t in texts:
        ws = set(tokenize(t, extra_stop=extra_stop, min_len=min_len))
        df_counter.update(ws)

    n_doc = max(len(texts), 1)
    scored = []
    for w, c in df_counter.items():
        if c < 3:
            continue
        ratio = c / n_doc
        if ratio > 0.55:        # 几乎每条都出现 → 无区分度
            continue
        scored.append((w, c * (1.0 + 0.35 * (len(w) - 2))))
    scored.sort(key=lambda x: -x[1])

    picked = [w for w, _ in scored[:top_n]]
    for m in (must_include or []):
        if m and m not in picked:
            picked.insert(0, m)
    picked = picked[:max(top_n, len(must_include or []))]
    return {w: [w] for w in picked}


def phrase_hit_matrix(texts: np.ndarray, phrases: dict) -> dict:
    """短语 → 布尔命中数组（评论级计数）。"""
    hits = {}
    for name, variants in phrases.items():
        h = np.zeros(len(texts), dtype=bool)
        for v in variants:
            if not v:
                continue
            h |= np.char.find(texts, str(v)) >= 0
        hits[name] = h
    return hits


# --------------------------------------------------------------------------
# 阶段 / 短语解析（供各 step 统一调用，保证可复现 + 一致）
# --------------------------------------------------------------------------
def compute_phases(cfg: dict, df: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    """
    依据 cfg['phases'] 计算传播阶段，并把 phase 列写回 df（返回副本）。
    返回 (phases_def: list[dict], df_with_phase)。
    """
    daily = df.groupby(df["created_at"].dt.date).size()
    daily.index = pd.to_datetime(daily.index)
    pmode = cfg["phases"]["mode"]
    if pmode == "manual":
        phases_def = phases_from_manual(
            cfg["phases"]["manual"],
            df["created_at"].min(),
            df["created_at"].max(),
        )
    else:
        phases_def = detect_phases(daily, cfg["phases"]["auto"])
    out = df.copy()
    out["phase"] = assign_phase(out["created_at"], phases_def)
    return phases_def, out


def resolve_phrases(cfg: dict, texts) -> dict:
    """
    依据 cfg['phrases'] 解析核心短语词典 {name: [variants]}。
    mode: manual（手写词典）/ auto（自动抽取）/ hybrid（二者合并，manual 优先）。
    """
    pmode = cfg["phrases"]["mode"]
    man = cfg["phrases"].get("manual") or {}
    man = {k: (v if isinstance(v, list) else [v]) for k, v in man.items()}
    if pmode == "manual":
        return man
    auto = extract_core_phrases(
        texts,
        top_n=cfg["phrases"].get("top_n", 24),
        min_len=cfg["phrases"].get("min_len", 2),
    )
    if pmode == "auto":
        return auto
    merged = dict(auto)
    merged.update(man)  # manual 覆盖同名
    return merged


# --------------------------------------------------------------------------
# 杂项
# --------------------------------------------------------------------------
def dump_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    def _default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.ndarray,)):
            return o.tolist()
        return str(o)

    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=_default),
                          encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def robust_read_csv(path, **kw):
    """
    容错读取 CSV：多次追加写入可能混入 GBK 行，逐行探测解码后再交给 pandas。
    """
    import io
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        lines, n_gbk = [], 0
        for ln in raw.split(b"\n"):
            try:
                lines.append(ln.decode("utf-8"))
            except UnicodeDecodeError:
                try:
                    lines.append(ln.decode("gbk"))
                    n_gbk += 1
                except UnicodeDecodeError:
                    lines.append(ln.decode("utf-8", errors="replace"))
        log.warning("检测到混合编码，%d 行按 GBK 解码", n_gbk)
        text = "\n".join(lines).lstrip("\ufeff")
    # 文本已解码完毕，编码相关参数在此无意义，去掉以免报错
    for k in ("encoding", "encoding_errors"):
        kw.pop(k, None)
    kw.setdefault("on_bad_lines", "skip")

    # 优先用 C 引擎（快、支持 low_memory）；失败再退回 python 引擎
    if "engine" not in kw:
        try:
            return pd.read_csv(io.StringIO(text), engine="c", **kw)
        except Exception:
            pass
    kw.pop("low_memory", None)          # python 引擎不支持
    kw["engine"] = "python"
    return pd.read_csv(io.StringIO(text), **kw)
