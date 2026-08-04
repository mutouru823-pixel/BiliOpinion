# -*- coding: utf-8 -*-
"""
Step3 主题分析 —— 复现论文 3.2/4.2 节流程
 1) 探索性无监督主题发现：TF-IDF 语义向量 + SVD + KMeans + 轮廓系数 + 簇关键词
    （算力受限时以 TF-IDF/LSA 替代 BERT-768 向量，流程与评估标准一致）
 2) 依据聚类发现构建自动命名，或按用户 codebook（优先级规则）进行全量分类
 3) 主题分布 / 时间演化（堆叠面积）/ 层级交叉热力图 / 文本长度 / 时段热力图
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
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

from ..utils import (robust_read_csv, get_logger, banner, setup_matplotlib,
                     savefig, dump_json, compute_phases)

log = get_logger()

STOP = set("的了是我你他她它们in在有和就不人都一个上也很到说要去会着没有看好这那还把被与及呢吧啊吗么什么怎么这个那个如果因为所以但是然后不是就是可以自己现在知道觉得真的应该已经只是还是其实而且或者虽然于对啥又太再most".split())


def _tok(t):
    return [w for w in list(jieba.cut(str(t)))
            if len(w) > 1 and w not in STOP and not re.match(r"^[\d\W]+$", w)]


def _core_window(df, daily):
    peak_v = daily.max()
    active = daily[daily >= peak_v * 0.10]
    if len(active) >= 2:
        return active.index.min(), active.index.max()
    return daily.index.min(), daily.index.max()


def run(cfg) -> dict:
    out, fig = cfg.dir_data, cfg.dir_fig
    setup_matplotlib(cfg)
    df = robust_read_csv(out / "comments_valid.csv", parse_dates=["created_at"], low_memory=False)
    df["date"] = df["created_at"].dt.date
    if "phase" not in df.columns:
        _, df = compute_phases(cfg, df)
    df["text_clean"] = df["text_clean"].astype(str)

    banner(f"Step3 主题分析 · {cfg.topic}")
    seed = cfg["runtime"].get("random_seed", 42)
    rng = np.random.RandomState(seed)

    # 去重集用于无监督探索与向量化
    dedup = df.drop_duplicates("text_clean").copy()
    docs = dedup["text_clean"].astype(str).tolist()

    tp = cfg["topics"]
    explore = tp["explore"]
    sample_size = min(explore.get("sample_size", 12000), len(docs)) or len(docs)
    sample_idx = rng.choice(len(docs), sample_size, replace=False)
    sample_docs = [docs[i] for i in sample_idx]

    vec = TfidfVectorizer(max_features=explore.get("max_features", 8000), min_df=3)
    Xs = vec.fit_transform([" ".join(_tok(t)) for t in sample_docs])
    svd = TruncatedSVD(n_components=explore.get("svd_components", 100), random_state=seed)
    Xs_r = normalize(svd.fit_transform(Xs))

    # 轮廓系数选 K
    sil = {}
    for k in range(*explore.get("k_range", [4, 9])):
        km = KMeans(n_clusters=k, random_state=seed, n_init=5)
        lab = km.fit_predict(Xs_r)
        idxs = rng.choice(len(lab), min(5000, len(lab)), replace=False)
        sil[k] = float(silhouette_score(Xs_r[idxs], lab[idxs]))
        log.info("K=%d silhouette=%.4f", k, sil[k])
    best_k = max(sil, key=sil.get)
    log.info("最优 K=%d", best_k)

    km = KMeans(n_clusters=best_k, random_state=seed, n_init=10).fit(Xs_r)
    terms = np.array(vec.get_feature_names_out())
    cluster_kw = {}
    for c in range(best_k):
        mask = km.labels_ == c
        centroid = np.asarray(Xs[mask].mean(axis=0)).ravel()
        cluster_kw[int(c)] = {"size": int(mask.sum()),
                              "keywords": terms[np.argsort(-centroid)[:12]].tolist()}
    dump_json({"silhouette": sil, "best_k": best_k, "clusters": cluster_kw},
              out / "cluster_explore.json")
    log.info("簇关键词: %s", {c: v["keywords"][:4] for c, v in cluster_kw.items()})

    # 全量去重集打主题标签（最近质心，余弦距离）
    centroids = normalize(km.cluster_centers_)
    Xall_r = normalize(svd.transform(vec.transform([" ".join(_tok(t)) for t in docs])))
    sims = Xall_r @ centroids.T
    labels_all = sims.argmax(axis=1)

    # 自动命名
    auto_names = {}
    for c in range(best_k):
        kws = cluster_kw[c]["keywords"][:3]
        auto_names[c] = f"主题{c}({','.join(kws)})"

    # 是否启用 codebook 优先级分类
    if tp["mode"] == "codebook":
        cb = tp["codebook"]
        cats = cb["categories"]
        order = cb["order"] or list(cats.keys())
        fallback = cb.get("fallback", "F")
        fallback_name = cb.get("fallback_name", "F无关信息")
        short_to = cb.get("short_to", "")
        short_maxlen = cb.get("short_maxlen", 15)

        texts = df["text_clean"].to_numpy(dtype="U")
        labels = np.full(len(texts), fallback, dtype="U1")
        assigned = np.zeros(len(texts), dtype=bool)
        for cat in order:
            info = cats[cat]
            kws = info.get("keywords", [])
            hit = np.zeros(len(texts), dtype=bool)
            for kw in kws:
                hit |= np.char.find(texts, kw) >= 0
            newly = hit & ~assigned
            labels[newly] = cat
            assigned |= hit
        # 极短纯互动归入 short_to（论文里归 C 类）
        if short_to:
            tlen_arr = df["text_clean"].str.len().to_numpy()
            short_interact = (labels == fallback) & (tlen_arr <= short_maxlen)
            labels[short_interact] = short_to
            log.info("纯互动短评论归入 %s 类: %d 条", short_to, int(short_interact.sum()))

        name_of = {cat: cats[cat].get("name", cat) for cat in cats}
        name_of[fallback] = fallback_name
        df["topic"] = labels
        df["topic_name"] = df["topic"].map(name_of)
        topic_order = [name_of[c] for c in (order + [fallback]) if name_of[c] in set(df["topic_name"])]
        if fallback_name not in topic_order:
            topic_order.append(fallback_name)
        colors = plt.cm.tab10(np.linspace(0, 1, max(len(topic_order), 3)))
    else:
        num_map = dict(zip(dedup["text_clean"], [int(l) for l in labels_all]))
        label_map = dict(zip(dedup["text_clean"], [auto_names[int(l)] for l in labels_all]))
        df["topic"] = df["text_clean"].map(num_map)
        df["topic_name"] = df["text_clean"].map(label_map)
        topic_order = [auto_names[c] for c in range(best_k)]
        colors = plt.cm.tab10(np.linspace(0, 1, max(best_k, 3)))

    df[["comment_id", "bv", "level", "likes", "created_at", "date", "topic", "topic_name", "text_clean"]] \
        .to_csv(out / "comments_topic.csv", index=False, encoding="utf-8-sig")
    log.info("主题分布:\n%s", df["topic_name"].value_counts().to_string())

    # ---------- 图3 主题分布 ----------
    counts = [int((df["topic_name"] == n).sum()) for n in topic_order]
    fig3 = fig / "fig03_topic_dist.png"
    fig_, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(topic_order, counts, color=colors)
    for b, c in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, c, f"{c:,}\n({c / len(df) * 100:.1f}%)",
                ha="center", va="bottom", fontsize=9)
    ax.set_title(f"图3 全量评论主题分布（N={len(df):,}）")
    ax.set_ylabel("评论数"); plt.xticks(rotation=15, fontsize=9); plt.tight_layout()
    savefig(fig_, fig3)

    # ---------- 图4 主题时间演化（堆叠面积，核心窗口）----------
    daily = df.groupby("date").size()
    cs, ce = _core_window(df, daily)
    core = df[(df["created_at"] >= pd.Timestamp(cs)) & (df["created_at"] <= pd.Timestamp(ce))]
    pv = core.pivot_table(index="date", columns="topic_name", values="comment_id", aggfunc="count").fillna(0)
    pv = pv.reindex(columns=topic_order).fillna(0)
    fig4 = fig / "fig04_topic_time.png"
    fig_, ax = plt.subplots(figsize=(13, 5.5))
    ax.stackplot(pv.index, [pv[c] for c in topic_order], labels=topic_order, colors=colors, alpha=0.88)
    ax.legend(loc="upper right", fontsize=9)
    ax.set_title(f"图4 主题类别逐日演化堆叠面积图（{cs.strftime('%Y-%m-%d')} 至 {ce.strftime('%Y-%m-%d')}）")
    ax.set_ylabel("评论数"); plt.xticks(rotation=45); plt.tight_layout()
    savefig(fig_, fig4)

    # ---------- 图5 主题 × 层级交叉热力图 ----------
    ct = pd.crosstab(df["topic_name"], df["level"])
    ct.columns = [f"层级{int(c)}" for c in ct.columns]
    ct = ct.reindex(topic_order)
    fig5 = fig / "fig05_topic_level.png"
    fig_, ax = plt.subplots(figsize=(7.5, 5))
    im = ax.imshow(ct.values, cmap="Blues", aspect="auto")
    ax.set_xticks(range(ct.shape[1])); ax.set_xticklabels(ct.columns)
    ax.set_yticks(range(ct.shape[0])); ax.set_yticklabels(ct.index, fontsize=9)
    for i in range(ct.shape[0]):
        for j in range(ct.shape[1]):
            v = ct.values[i, j]; tot = ct.values[i].sum()
            ax.text(j, i, f"{v:,}\n({v / tot * 100:.1f}%)", ha="center", va="center", fontsize=8.5,
                    color="white" if v > ct.values.max() * 0.55 else "black")
    plt.colorbar(im, label="评论数")
    ax.set_title("图5 主题类别 × 评论层级交叉分析热力图")
    plt.tight_layout(); savefig(fig_, fig5)
    ct.to_csv(out / "topic_level_crosstab.csv", encoding="utf-8-sig")

    # ---------- 图6 文本长度 ----------
    df["tlen"] = df["text_clean"].str.len()
    fig6 = fig / "fig06_topic_len.png"
    fig_, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    data = [df[df["topic_name"] == n]["tlen"].clip(upper=200) for n in topic_order]
    axes[0].boxplot(data, tick_labels=[n[:1] for n in topic_order], showfliers=False,
                    patch_artist=True, boxprops=dict(facecolor="#AED6F1"))
    axes[0].set_title("各类别评论文本长度分布（截断至200字）"); axes[0].set_ylabel("字数")
    means = [df[df["topic_name"] == n]["tlen"].mean() for n in topic_order]
    axes[1].bar([n[:1] for n in topic_order], means, color=colors)
    for i, m in enumerate(means):
        axes[1].text(i, m, f"{m:.1f}", ha="center", va="bottom", fontsize=9)
    axes[1].set_title("各类别平均文本长度（字）")
    fig_.suptitle("图6 各主题类别评论文本长度特征", y=1.02)
    plt.tight_layout(); savefig(fig_, fig6)

    # ---------- 图7 爆发期评论时段热力图（小时 × 日期）----------
    bs, be = _core_window(df, daily)
    sub = df[(df["created_at"] >= pd.Timestamp(bs)) & (df["created_at"] <= pd.Timestamp(be))].copy()
    sub["hour"] = sub["created_at"].dt.hour
    hm = sub.pivot_table(index="hour", columns="date", values="comment_id", aggfunc="count").fillna(0)
    fig7 = fig / "fig07_topic_hour.png"
    fig_, ax = plt.subplots(figsize=(12, 6))
    im = ax.imshow(hm.values, aspect="auto", cmap="YlOrRd")
    ax.set_xticks(range(hm.shape[1])); ax.set_xticklabels([d.strftime("%m-%d") for d in hm.columns], rotation=90, fontsize=8)
    ax.set_yticks(range(0, 24, 2)); ax.set_yticklabels([f"{h}时" for h in range(0, 24, 2)], fontsize=8)
    plt.colorbar(im, label="评论数")
    ax.set_title(f"图7 爆发期评论时段分布热力图（{bs.strftime('%m-%d')} 至 {be.strftime('%m-%d')}，小时 × 日期）")
    plt.tight_layout(); savefig(fig_, fig7)

    # 汇总
    summ = df.groupby("topic_name").agg(评论数=("comment_id", "count"),
                                        平均长度=("tlen", "mean"),
                                        平均赞数=("likes", "mean"),
                                        最高赞=("likes", "max")).reindex(topic_order)
    summ["层级2占比%"] = (df[df["level"] == 2].groupby("topic_name").size() /
                          df.groupby("topic_name").size() * 100).reindex(topic_order)
    summ.round(2).to_csv(out / "topic_summary.csv", encoding="utf-8-sig")

    return {
        "stats": {
            "best_k": best_k,
            "silhouette": {str(k): round(v, 4) for k, v in sil.items()},
            "n_topics": len(topic_order),
            "topic_dist": {n: int((df["topic_name"] == n).sum()) for n in topic_order},
        },
        "figures": [
            (str(fig3), "图3 全量评论主题分布", "基于 TF-IDF+SVD+KMeans 自动聚类（或用户 codebook）得到的主题占比。"),
            (str(fig4), "图4 主题逐日演化堆叠面积", "核心活动窗口内各主题类别的时序消长。"),
            (str(fig5), "图5 主题 × 层级交叉热力图", "主题类别在一/二级评论中的分布差异。"),
            (str(fig6), "图6 各主题文本长度特征", "箱线图与平均长度对比。"),
            (str(fig7), "图7 爆发期评论时段热力图", "小时 × 日期的评论密度，反映用户作息与热点时刻。"),
        ],
        "data_files": ["comments_topic.csv", "cluster_explore.json",
                       "topic_level_crosstab.csv", "topic_summary.csv"],
    }
