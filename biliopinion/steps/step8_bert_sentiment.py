# -*- coding: utf-8 -*-
"""
Step8 弱监督情感分类（可选，默认关闭）

以 SnowNLP 伪标签（正向/负向/中性阈值）作弱监督信号，训练线性分类器（LogisticRegression）
对全量评论做情感三分类。产出 comments_with_bert_sentiment.csv 与分类评估。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix

from ..utils import robust_read_csv, get_logger, banner, setup_matplotlib, savefig, dump_json

log = get_logger()


def run(cfg) -> dict:
    bcfg = cfg["bert"]
    if not (bcfg.get("enabled") and bcfg.get("sentiment", {}).get("enabled", True)):
        log.info("BERT 情感未启用，跳过 Step8。")
        return {"stats": {"skipped": True}, "figures": [], "data_files": []}

    out, fig = cfg.dir_data, cfg.dir_fig
    setup_matplotlib(cfg)
    banner(f"Step8 弱监督情感分类 · {cfg.topic}")

    df = robust_read_csv(out / "comments_valid.csv", dtype=str)
    sc = bcfg["sentiment"]

    # 伪标签：优先复用 step4 的 senti_score，否则现场算
    if "senti_score" in df.columns:
        scores = df["senti_score"].astype(float)
    else:
        from snownlp import SnowNLP
        log.info("计算 SnowNLP 伪标签中...")
        scores = df["text_clean"].astype(str).map(
            lambda t: SnowNLP(str(t)[:sc.get("max_chars", 200)]).sentiments
            if len(str(t)) else 0.5)
    pos_p, neg_p = sc.get("pos_pseudo", 0.85), sc.get("neg_pseudo", 0.15)
    neu = sc.get("neu_pseudo", [0.45, 0.55])
    pseudo = np.where(scores >= pos_p, "pos",
              np.where(scores <= neg_p, "neg",
              np.where((scores >= neu[0]) & (scores <= neu[1]), "neu", "drop")))
    df["pseudo"] = pseudo
    log.info("伪标签分布:\n%s", pd.Series(pseudo).value_counts().to_string())

    train = df[df["pseudo"] != "drop"]
    max_per = sc.get("max_per_class", 12000)
    train_bal = []
    for lab in ["pos", "neg", "neu"]:
        sub = train[train["pseudo"] == lab]
        if len(sub) > max_per:
            sub = sub.sample(max_per, random_state=cfg["runtime"].get("random_seed", 42))
        train_bal.append(sub)
    train_bal = pd.concat(train_bal)

    vec = TfidfVectorizer(max_features=20000, min_df=3, ngram_range=(1, 2))
    Xtr = vec.fit_transform(train_bal["text_clean"].astype(str))
    ytr = train_bal["pseudo"].values
    clf = LogisticRegression(max_iter=1000, C=4.0, class_weight="balanced")
    clf.fit(Xtr, ytr)
    log.info("分类器训练完成（%d 条弱监督样本）", len(train_bal))

    Xall = vec.transform(df["text_clean"].astype(str))
    pred = clf.predict(Xall)
    df["bert_polarity"] = pred
    proba = clf.predict_proba(Xall)
    df["bert_polarity_score"] = proba.max(axis=1)
    df[["comment_id", "text_clean", "bert_polarity", "bert_polarity_score"]].to_csv(
        out / "comments_with_bert_sentiment.csv", index=False, encoding="utf-8-sig")

    rep = classification_report(ytr, clf.predict(Xtr), output_dict=True, zero_division=0)
    cm = confusion_matrix(ytr, clf.predict(Xtr), labels=["pos", "neg", "neu"])
    dump_json({"report": rep, "confusion": cm.tolist(), "labels": ["pos", "neg", "neu"]},
              out / "bert_sentiment_eval.json")
    log.info("训练集分类报告:\n%s", classification_report(ytr, clf.predict(Xtr), zero_division=0))

    # 图：全量预测分布
    dist = df["bert_polarity"].value_counts()
    fig8 = fig / "fig17_bert_sentiment_dist.png"
    fig_, ax = plt.subplots(figsize=(8, 5))
    ax.bar(dist.index, dist.values, color=["#27AE60", "#E74C3C", "#BDC3C7"][:len(dist)])
    for i, (k, v) in enumerate(dist.items()):
        ax.text(i, v, f"{v:,}\n({v/len(df)*100:.1f}%)", ha="center", va="bottom")
    ax.set_title(f"图17 弱监督情感分类分布（N={len(df):,}）")
    ax.set_ylabel("评论数"); plt.tight_layout(); savefig(fig_, fig8)

    return {
        "stats": {"dist": {str(k): int(v) for k, v in dist.items()},
                  "train_samples": int(len(train_bal))},
        "figures": [(str(fig8), "图17 弱监督情感分类分布",
                     "基于 SnowNLP 伪标签训练的线性分类器在全量评论上的预测分布。")],
        "data_files": ["comments_with_bert_sentiment.csv", "bert_sentiment_eval.json"],
    }
