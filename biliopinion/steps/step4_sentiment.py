# -*- coding: utf-8 -*-
"""
Step4 情感与立场分析 —— 复现论文 3.5/4.3 节方法
 1) SnowNLP 词典法：正向(>=pos_threshold) / 中性 / 负向(<=neg_threshold) 三分类
 2) 事件规则立场词典（可选）：采信/传播 vs 质疑/辟谣，可配 pos/neg 词表
 3) 阶段情感比例、立场对比（数量/平均赞/最高赞/文本长度/TOP 关键词）、箱线图、情感词云
"""
from __future__ import annotations

import re
from collections import Counter

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import jieba
from snownlp import SnowNLP
from wordcloud import WordCloud

from ..utils import (robust_read_csv, get_logger, banner, setup_matplotlib,
                     savefig, font_path, dump_json, compute_phases)

log = get_logger()

STOP = set("的了是我你他她它们在有和就不人都一个上也很到说要去会着看好这那还把被与及呢吧啊吗么什么怎么这个那个如果因为所以但是然后不是就是可以自己现在知道觉得真的应该已经只是还是其实而且或者虽然于对啥又太再没有".split())


def _top_words(series, n=20, seed=42):
    c = Counter()
    for t in series.sample(min(len(series), 20000), random_state=seed):
        c.update(w for w in list(jieba.cut(str(t)))
                  if len(w) > 1 and w not in STOP and not re.match(r"^[\d\W]+$", w))
    return c.most_common(n)


def _hit_any(texts, words):
    h = np.zeros(len(texts), dtype=bool)
    for w in words:
        h |= np.char.find(texts, w) >= 0
    return h


def run(cfg) -> dict:
    out, fig = cfg.dir_data, cfg.dir_fig
    fp = setup_matplotlib(cfg)
    df = robust_read_csv(out / "comments_valid.csv", parse_dates=["created_at"], low_memory=False)
    df["date"] = df["created_at"].dt.date
    if "phase" not in df.columns:
        _, df = compute_phases(cfg, df)
    df["text_clean"] = df["text_clean"].astype(str)

    banner(f"Step4 情感与立场 · {cfg.topic}")
    snt = cfg["sentiment"]
    pos_t, neg_t = snt.get("pos_threshold", 0.6), snt.get("neg_threshold", 0.4)
    max_chars = snt.get("max_chars", 200)

    # ---------- 1. SnowNLP 情感极性 ----------
    log.info("SnowNLP 情感计算中（约 %d 条）...", len(df))
    def _senti(t):
        try:
            return SnowNLP(t[:max_chars]).sentiments
        except Exception:
            return 0.5
    df["senti_score"] = df["text_clean"].apply(_senti)
    df["polarity"] = pd.cut(df["senti_score"], bins=[-0.01, neg_t, pos_t, 1.01],
                            labels=["负向", "中性", "正向"])

    # ---------- 2. 事件规则立场 ----------
    stance = snt.get("stance", {})
    if stance.get("enabled") and (stance.get("pos_words") or stance.get("neg_words")):
        pos_w = stance.get("pos_words", [])
        neg_w = stance.get("neg_words", [])
        pos_name = stance.get("pos_name", "支持/采信")
        neg_name = stance.get("neg_name", "质疑/反对")
        texts = df["text_clean"].to_numpy(dtype="U")
        believe_hit = _hit_any(texts, pos_w)
        debunk_hit = _hit_any(texts, neg_w)
        df["stance"] = "中立/无明确立场"
        df.loc[believe_hit & ~debunk_hit, "stance"] = pos_name
        df.loc[debunk_hit & ~believe_hit, "stance"] = neg_name
        df.loc[believe_hit & debunk_hit, "stance"] = "混合/争论"
        do_stance = True
    else:
        df["stance"] = "中立/无明确立场"
        do_stance = False
        log.info("未配置立场词典，跳过立场分析。")

    df[["comment_id", "phase", "polarity", "senti_score", "stance",
        "likes", "level", "date"]].to_csv(out / "comments_sentiment.csv",
                                          index=False, encoding="utf-8-sig")

    figures = []
    phase_order = sorted(df["phase"].dropna().unique().tolist())
    # 阶段情感比例
    pol = pd.crosstab(df["phase"], df["polarity"], normalize="index").reindex(phase_order) * 100
    fig8 = fig / "fig08_phase_polarity.png"
    fig_, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(phase_order)); w = 0.26
    ax.bar(x - w, pol["正向"], w, label="正向", color="#E74C3C")
    ax.bar(x, pol["中性"], w, label="中性", color="#BDC3C7")
    ax.bar(x + w, pol["负向"], w, label="负向", color="#27AE60")
    for i in range(len(phase_order)):
        ax.text(x[i] - w, pol["正向"].iloc[i], f"{pol['正向'].iloc[i]:.1f}", ha="center", va="bottom", fontsize=8)
        ax.text(x[i] + w, pol["负向"].iloc[i], f"{pol['负向'].iloc[i]:.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(phase_order, fontsize=9)
    ax.set_ylabel("占比 (%)"); ax.legend()
    ax.set_title(f"图8 各传播阶段情感极性分布（SnowNLP，正向≥{pos_t} / 负向≤{neg_t}）")
    plt.tight_layout(); savefig(fig_, fig8)
    pol.to_csv(out / "phase_polarity.csv", encoding="utf-8-sig")
    figures.append((str(fig8), "图8 各传播阶段情感极性分布", "SnowNLP 词典法三分类在各阶段的占比变化。"))

    if do_stance:
        sup = df[df["stance"] == pos_name]; opp = df[df["stance"] == neg_name]
        n_s, n_o = len(sup), len(opp)
        cmp = pd.DataFrame({
            pos_name: [n_s, n_s / (n_s + n_o) * 100, sup["likes"].mean(), sup["likes"].max(), sup["text_clean"].str.len().mean()],
            neg_name: [n_o, n_o / (n_s + n_o) * 100, opp["likes"].mean(), opp["likes"].max(), opp["text_clean"].str.len().mean()],
        }, index=["评论数", "去中立后占比%", "平均赞数", "最高赞数", "平均文本长度(字)"]).round(2)
        cmp.to_csv(out / "stance_compare.csv", encoding="utf-8-sig")
        log.info("立场对比:\n%s", cmp.to_string())

        st_ph = df[df["stance"].isin([pos_name, neg_name])].pivot_table(
            index="phase", columns="stance", values="likes", aggfunc="mean").reindex(phase_order)
        fig9 = fig / "fig09_stance_likes.png"
        fig_, ax = plt.subplots(figsize=(10, 4.6))
        if pos_name in st_ph: ax.plot(x, st_ph[pos_name], "o-", color="#E67E22", label=pos_name)
        if neg_name in st_ph: ax.plot(x, st_ph[neg_name], "s-", color="#2471A3", label=neg_name)
        ax.set_xticks(x); ax.set_xticklabels(phase_order, fontsize=9)
        ax.set_ylabel("平均赞数"); ax.legend()
        ax.set_title("图9 两类立场评论平均赞数的阶段演化")
        plt.tight_layout(); savefig(fig_, fig9)
        st_ph.to_csv(out / "stance_phase_likes.csv", encoding="utf-8-sig")

        fig10 = fig / "fig10_stance_box.png"
        fig_, ax = plt.subplots(figsize=(8, 5))
        ax.boxplot([np.log10(sup["likes"] + 1), np.log10(opp["likes"] + 1)],
                   tick_labels=[f"{pos_name}\n(n={n_s:,})", f"{neg_name}\n(n={n_o:,})"],
                   showfliers=True, patch_artist=True, boxprops=dict(facecolor="#F9E79F"))
        ax.set_ylabel("log10(赞数+1)")
        ax.set_title("图10 两类立场评论赞数分布箱线图（对数刻度）")
        plt.tight_layout(); savefig(fig_, fig10)

        tw_s = _top_words(sup["text_clean"]); tw_o = _top_words(opp["text_clean"])
        dump_json({pos_name: tw_s, neg_name: tw_o}, out / "stance_topwords.json")
        fig11 = fig / "fig11_stance_words.png"
        fig_, axes = plt.subplots(1, 2, figsize=(13, 5.5))
        for axx, tw, title, color in [(axes[0], tw_s, f"{pos_name} TOP20 关键词", "#E67E22"),
                                      (axes[1], tw_o, f"{neg_name} TOP20 关键词", "#2471A3")]:
            words = [w for w, _ in tw][::-1]; vals = [v for _, v in tw][::-1]
            axx.barh(words, vals, color=color); axx.set_title(title, fontsize=11)
            axx.tick_params(labelsize=9)
        fig_.suptitle("图11 两类立场评论的 TOP 关键词对比", y=1.0)
        plt.tight_layout(); savefig(fig_, fig11)
        figures += [
            (str(fig9), "图9 立场平均赞数演化", "两类立场评论平均赞数随传播阶段的演化。"),
            (str(fig10), "图10 立场赞数箱线图", "对数刻度下两类立场评论的赞数分布。"),
            (str(fig11), "图11 立场 TOP 关键词", "采信与质疑两类评论的高频词对比，揭示话语焦点差异。"),
        ]

    # 三情感极性词云
    fig12 = fig / "fig12_polarity_wordcloud.png"
    fig_, axes = plt.subplots(1, 3, figsize=(16, 5))
    for axx, p, cmap in [(axes[0], "正向", "Reds"), (axes[1], "中性", "Greys"), (axes[2], "负向", "Greens")]:
        subtxt = df[df["polarity"] == p]["text_clean"]
        c = Counter()
        for t in subtxt.sample(min(len(subtxt), 15000), random_state=42):
            c.update(w for w in list(jieba.cut(str(t)))
                      if len(w) > 1 and w not in STOP and not re.match(r"^[\d\W]+$", w))
        wc = WordCloud(font_path=fp, width=520, height=380, background_color="white",
                       colormap=cmap, max_words=50).generate_from_frequencies(dict(c.most_common(80)))
        axx.imshow(wc, interpolation="bilinear"); axx.axis("off")
        axx.set_title(f"{p}评论 (n={(df['polarity'] == p).sum():,})")
    fig_.suptitle("图12 三类情感极性评论的关键词词云", y=1.0)
    plt.tight_layout(); savefig(fig_, fig12)
    figures.append((str(fig12), "图12 三类情感极性词云", "正向/中性/负向评论各自的高频词云。"))

    stance_dist = df["stance"].value_counts()
    stance_dist.to_csv(out / "stance_dist.csv", encoding="utf-8-sig")
    log.info("情感极性分布:\n%s", df["polarity"].value_counts().to_string())
    log.info("立场分布:\n%s", stance_dist.to_string())

    return {
        "stats": {
            "polarity_dist": {str(k): int(v) for k, v in df["polarity"].value_counts().items()},
            "stance_dist": {str(k): int(v) for k, v in stance_dist.items()},
            "mean_senti": round(float(df["senti_score"].mean()), 4),
        },
        "figures": figures,
        "data_files": ["comments_sentiment.csv", "phase_polarity.csv", "stance_dist.csv"],
    }
