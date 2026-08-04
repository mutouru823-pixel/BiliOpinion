# -*- coding: utf-8 -*-
"""
Step7 BERT 主题聚类（可选，默认关闭）

在 Step6 的句向量上做 PCA 降维 + KMeans 聚类，用 c-TF-IDF 抽取每类关键词
（BERTopic 式流程）。产出 comments_with_topics.csv 与 2D 投影散点图。
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
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

from ..utils import robust_read_csv, get_logger, banner, setup_matplotlib, savefig, dump_json

log = get_logger()
STOP = set("的了是我你他她它们in在有和就不人都一个上也很到说要去会着没有看好这那还把被与及呢吧啊吗么什么怎么这个那个如果因为所以但是然后不是就是可以自己现在知道觉得真的应该已经只是还是其实而且或者虽然于对啥又太再most".split())


def run(cfg) -> dict:
    bcfg = cfg["bert"]
    if not (bcfg.get("enabled") and bcfg.get("topic", {}).get("enabled", True)):
        log.info("BERT 主题未启用，跳过 Step7。")
        return {"stats": {"skipped": True}, "figures": [], "data_files": []}

    out, fig = cfg.dir_data, cfg.dir_fig
    setup_matplotlib(cfg)
    banner(f"Step7 BERT 主题聚类 · {cfg.topic}")

    emb = np.load(out / "bert_comment_embeddings.npy")
    meta = robust_read_csv(out / "bert_embed_map.csv", dtype=str)
    tc = bcfg["topic"]
    seed = cfg["runtime"].get("random_seed", 42)
    rng = np.random.RandomState(seed)

    Xr = normalize(emb)
    pca = PCA(n_components=tc.get("pca_components", 48), random_state=seed)
    Xp = pca.fit_transform(Xr)
    log.info("PCA 解释方差比累计: %.3f", float(np.cumsum(pca.explained_variance_ratio_)[-1]))

    sil = {}
    for k in range(*tc.get("k_range", [5, 13])):
        km = KMeans(n_clusters=k, random_state=seed, n_init=5)
        lab = km.fit_predict(Xp)
        idxs = rng.choice(len(lab), min(tc.get("silhouette_sample", 20000), len(lab)), replace=False)
        sil[k] = float(silhouette_score(Xp[idxs], lab[idxs]))
        log.info("K=%d silhouette=%.4f", k, sil[k])
    best_k = max(sil, key=sil.get)
    km = KMeans(n_clusters=best_k, random_state=seed, n_init=10).fit(Xp)
    labels = km.labels_

    # c-TF-IDF 关键词
    cv = CountVectorizer(tokenizer=lambda t: [w for w in list(jieba.cut(t))
                                               if len(w) > 1 and w not in STOP
                                               and not re.match(r"^[\d\W]+$", w)],
                         min_df=2, max_features=20000)
    try:
        Xc = cv.fit_transform(meta["text_clean"].astype(str))
    except ValueError:
        Xc = cv.fit_transform(["占位 文本"] * len(meta))
    vocab = np.array(cv.get_feature_names_out())
    counts = np.asarray(Xc.sum(axis=0)).ravel()
    df_t = np.asarray((Xc > 0).sum(axis=0)).ravel() + 1
    N = Xc.shape[0] + 1
    cluster_kw = {}
    for c in range(best_k):
        mask = labels == c
        if mask.sum() == 0:
            cluster_kw[c] = {"size": 0, "keywords": []}
            continue
        tf = np.asarray(Xc[mask].sum(axis=0)).ravel()
        idf = np.log((1 + N) / df_t)
        scores = tf * idf
        top = vocab[np.argsort(-scores)[:12]]
        cluster_kw[c] = {"size": int(mask.sum()), "keywords": top.tolist()}

    name_of = {c: f"BERT主题{c}({','.join(cluster_kw[c]['keywords'][:3])})"
               for c in range(best_k)}
    meta["bert_topic"] = labels
    meta["bert_topic_name"] = meta["bert_topic"].map(name_of)
    meta[["comment_id", "text_clean", "bert_topic", "bert_topic_name"]].to_csv(
        out / "comments_with_topics.csv", index=False, encoding="utf-8-sig")
    dump_json({"silhouette": sil, "best_k": best_k, "clusters": cluster_kw},
              out / "bert_topic_clusters.json")
    log.info("BERT 主题:\n%s", meta["bert_topic_name"].value_counts().to_string())

    # 图：簇规模 + 2D 投影（子采样）
    order = [name_of[c] for c in range(best_k)]
    counts = [int((meta["bert_topic_name"] == n).sum()) for n in order]
    fig3 = fig / "fig15_bert_topic_dist.png"
    fig_, ax = plt.subplots(figsize=(10, 5))
    ax.bar(range(len(order)), counts, color=plt.cm.tab10(np.linspace(0, 1, max(best_k, 3))))
    ax.set_xticks(range(len(order))); ax.set_xticklabels(order, rotation=20, fontsize=8, ha="right")
    ax.set_title(f"图15 BERT 主题分布（K={best_k}）"); ax.set_ylabel("评论数")
    plt.tight_layout(); savefig(fig_, fig3)

    samp = rng.choice(len(Xp), min(8000, len(Xp)), replace=False)
    coords = PCA(n_components=2, random_state=seed).fit_transform(Xr[samp])
    fig4 = fig / "fig16_bert_scatter.png"
    fig_, ax = plt.subplots(figsize=(10, 8))
    sc = ax.scatter(coords[:, 0], coords[:, 1], c=labels[samp], cmap="tab10",
                    s=4, alpha=0.5)
    ax.set_title("图16 BERT 句向量 2D 投影（颜色=主题簇）")
    plt.colorbar(sc); plt.tight_layout(); savefig(fig_, fig4)

    return {
        "stats": {"best_k": best_k, "silhouette": {str(k): round(v, 4) for k, v in sil.items()}},
        "figures": [
            (str(fig3), "图15 BERT 主题分布", "基于句向量 KMeans 聚类的主题规模。"),
            (str(fig4), "图16 BERT 句向量 2D 投影", "PCA 降至 2 维的可视化，颜色区分主题簇。"),
        ],
        "data_files": ["comments_with_topics.csv", "bert_topic_clusters.json"],
    }
