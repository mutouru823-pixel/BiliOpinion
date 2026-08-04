# -*- coding: utf-8 -*-
"""
Step2 时间演化 + 核心语义短语词云 + 每日核心短语热力图（对应论文 4.1）
 - 每日评论量柱状图 + 3 日移动平均线，自动叠加识别出的传播阶段边界
 - 核心语义短语词典（评论级计数：一条评论中出现多次只计 1 次）
 - 阶段词云 + 每千条有效评论标准化的每日核心短语热力图
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from wordcloud import WordCloud

from ..utils import (robust_read_csv, get_logger, banner, setup_matplotlib,
                     compute_phases, resolve_phrases, phrase_hit_matrix,
                     savefig, font_path, dump_json)

log = get_logger()


def _draw_wc(freq, title, path, fp):
    freq = {k: v for k, v in freq.items() if v > 0}
    if not freq:
        return False
    wc = WordCloud(font_path=fp, width=800, height=480, background_color="white",
                   colormap="tab10", max_words=60, prefer_horizontal=0.9)
    wc.generate_from_frequencies(freq)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.imshow(wc, interpolation="bilinear"); ax.axis("off")
    ax.set_title(title, fontsize=13)
    savefig(fig, path)
    return True


def run(cfg) -> dict:
    out, fig = cfg.dir_data, cfg.dir_fig
    fp = setup_matplotlib(cfg)
    df = robust_read_csv(out / "comments_valid.csv", parse_dates=["created_at"], low_memory=False)
    df["date"] = df["created_at"].dt.date

    banner(f"Step2 时间演化 · {cfg.topic}")
    phases_def, df = compute_phases(cfg, df)
    df.to_csv(out / "comments_valid.csv", index=False, encoding="utf-8-sig")  # 回写 phase
    phase_names = [p["name"] for p in phases_def]
    log.info("传播阶段: %s", " → ".join(phase_names))

    # ---------- 每日评论量 + 3 日移动平均 ----------
    daily = df.groupby("date").size()
    d0, d1 = daily.index.min(), daily.index.max()
    idx = pd.date_range(d0, d1)
    daily_core = daily.reindex(idx.date, fill_value=0)
    ma3 = pd.Series(daily_core.values, index=idx).rolling(3, center=True).mean()

    peak_d = daily.idxmax()
    peak_v = int(daily.max())

    fig1 = fig / "fig01_daily_volume.png"
    fig_, ax = plt.subplots(figsize=(13, 5))
    ax.bar(idx, daily_core.values, color="#5B8DB8", alpha=0.85, label="每日评论量")
    ax.plot(idx, ma3.values, color="#D9534F", lw=2.2, label="3日移动平均")
    for p in phases_def:
        bnd = pd.Timestamp(p["start"])
        ax.axvline(bnd, color="gray", ls="--", lw=0.8, alpha=0.6)
        ax.text(bnd, ax.get_ylim()[1] * 0.02, p["name"], fontsize=8, color="dimgray",
                rotation=90, va="bottom")
    ax.annotate(f"峰值 {peak_v:,} 条 ({peak_d.strftime('%m-%d')})",
                xy=(pd.Timestamp(peak_d), peak_v),
                xytext=(pd.Timestamp(peak_d) + pd.Timedelta(days=6), peak_v * 0.95),
                arrowprops=dict(arrowstyle="->", color="black"), fontsize=10)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(idx) // 20)))
    ax.set_ylabel("评论数")
    ax.set_title(f"图1 每日评论量变化（{d0.strftime('%Y-%m-%d')}—{d1.strftime('%Y-%m-%d')}，柱状图+3日移动平均）")
    ax.legend(); plt.xticks(rotation=45); plt.tight_layout()
    savefig(fig_, fig1)

    # 月度全貌
    monthly = df.groupby(df["created_at"].dt.to_period("M")).size()
    fig1b = fig / "fig01b_monthly_volume.png"
    fig_, ax = plt.subplots(figsize=(13, 4))
    ax.bar([str(p) for p in monthly.index], monthly.values, color="#5B8DB8")
    ax.set_title("图1b 月度评论量全貌")
    ax.set_ylabel("评论数")
    plt.xticks(rotation=60, fontsize=8); plt.tight_layout()
    savefig(fig_, fig1b)

    # ---------- 核心语义短语词典（评论级计数）----------
    phrases = resolve_phrases(cfg, df["text_clean"].astype(str))
    texts = df["text_clean"].astype(str).to_numpy(dtype="U")
    hits = phrase_hit_matrix(texts, phrases)
    phase_freq = {ph: {name: int(hits[name][(df["phase"] == ph).values].sum())
                       for name in phrases}
                  for ph in phase_names}

    # 阶段词云
    wc_files = []
    for ph in phase_names:
        p_ = fig / f"fig07_wc_{ph}.png"
        if _draw_wc(phase_freq[ph], f"核心语义短语词云 — {ph}", p_, fp):
            wc_files.append((str(p_), f"核心语义短语词云 — {ph}",
                             f"{ph} 阶段评论级短语提及频次"))

    # ---------- 每日核心短语热力图（每千条有效评论标准化）----------
    day_totals = df.groupby("date").size()
    top_phrases = sorted(phrases.keys(), key=lambda n: -sum(hits[n]))[: cfg["phrases"].get("heatmap_top", 22)]
    peak_val = daily_core.max()
    decay_r = cfg["phases"]["auto"].get("decay_ratio", 0.10)
    act = daily_core[daily_core >= peak_val * decay_r]
    if len(act) >= 2:
        hm_start, hm_end = act.index.min(), act.index.max()
    else:
        hm_start, hm_end = idx.min(), idx.max()
    hm_days = pd.date_range(hm_start, hm_end).date
    date_arr = df["date"].values
    mat = np.zeros((len(top_phrases), len(hm_days)))
    for j, d in enumerate(hm_days):
        dmask = date_arr == d
        total = max(int(day_totals.get(d, 0)), 1)
        for i, name in enumerate(top_phrases):
            mat[i, j] = hits[name][dmask].sum() / total * 1000

    fig2 = fig / "fig02_phrase_heatmap.png"
    fig_, ax = plt.subplots(figsize=(15, 8))
    im = ax.imshow(mat, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(len(hm_days)))
    ax.set_xticklabels([d.strftime("%m-%d") for d in hm_days], rotation=90, fontsize=7)
    ax.set_yticks(range(len(top_phrases))); ax.set_yticklabels(top_phrases, fontsize=9)
    plt.colorbar(im, label="每千条有效评论提及数")
    ax.set_title(f"图2 每日核心短语热力图（{hm_start.strftime('%m-%d')} 至 {hm_end.strftime('%m-%d')}，每千条评论标准化）")
    plt.tight_layout(); savefig(fig_, fig2)

    # 阶段统计
    phase_stat = df.groupby("phase").agg(评论量=("comment_id", "count"),
                                         日均赞数=("likes", "mean"),
                                         最高赞=("likes", "max")).reindex(phase_names)
    phase_stat.to_csv(out / "phase_stats.csv", encoding="utf-8-sig")

    dump_json({"phases": phases_def, "phase_freq": phase_freq,
               "phrases": phrases,
               "daily": {str(k): int(v) for k, v in daily.items()}},
              out / "phase_phrase_freq.json")

    figures = [
        (str(fig1), "图1 每日评论量变化", "柱状图为每日评论量，红线为 3 日移动平均；竖虚线为自动识别的传播阶段边界。"),
        (str(fig1b), "图1b 月度评论量全貌", "展现事件从潜伏、爆发到长尾的全时段月度分布。"),
        (str(fig2), "图2 每日核心短语热力图", "每千条有效评论标准化的核心短语逐日提及强度，反映议题焦点的时序迁移。"),
    ] + wc_files

    return {
        "stats": {
            "phases": phase_names,
            "peak_date": str(peak_d),
            "peak_count": peak_v,
            "n_phrases": len(phrases),
        },
        "figures": figures,
        "data_files": ["phase_stats.csv", "phase_phrase_freq.json"],
    }
