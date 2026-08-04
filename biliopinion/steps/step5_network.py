# -*- coding: utf-8 -*-
"""
Step5 社会网络分析 —— 复现论文 3.6/4.4 节方法
 节点: 评论用户 / 视频 / UP 主
 边: belongs_to(视频→UP主) / comment(用户→视频) / reply(用户→用户)
 指标: 节点/边/类型边数/平均度/加权度/密度/平均路径长度/直径/模块化(Louvain)/
       平均聚类系数；十大视频子网络对比；核心短语共现网络
"""
from __future__ import annotations

import random
from collections import Counter

import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from ..utils import (robust_read_csv, get_logger, banner, setup_matplotlib,
                     resolve_phrases, phrase_hit_matrix, savefig, dump_json)

log = get_logger()


def run(cfg) -> dict:
    out, fig, raw = cfg.dir_data, cfg.dir_fig, cfg.dir_raw
    setup_matplotlib(cfg)
    font_family = plt.rcParams["font.family"]
    if isinstance(font_family, list):
        font_family = font_family[0]

    net = cfg["network"]
    seed = cfg["runtime"].get("random_seed", 42)
    random.seed(seed); np.random.seed(seed)

    banner(f"Step5 社会网络 · {cfg.topic}")
    df = robust_read_csv(out / "comments_valid.csv", parse_dates=["created_at"], low_memory=False)
    vids = robust_read_csv(raw / "videos.csv", encoding_errors="replace", engine="python")
    vids = vids.rename(columns={"bvid": "bv", "author": "up", "view_count": "views",
                                "reply_count": "comments", "pubdate": "pub",
                                "collected_at": "crawl"})
    vmap = dict(zip(vids["bv"], vids["up"]))
    tmap = dict(zip(vids["bv"], vids["title"]))

    # ---- 建图 ----
    G = nx.Graph()
    edge_type_count = Counter()

    for bv in df["bv"].unique():
        up = vmap.get(bv, f"UP_{bv}")
        G.add_edge(f"V:{bv}", f"U:{up}", etype="belongs_to")
        edge_type_count["belongs_to"] += 1

    lv1 = df[df["level"] == 1]
    for uid, bv in zip(lv1["user_mid"], lv1["bv"]):
        e = (f"user:{uid}", f"V:{bv}")
        if G.has_edge(*e):
            G[e[0]][e[1]]["w"] = G[e[0]][e[1]].get("w", 1) + 1
        else:
            G.add_edge(*e, etype="comment", w=1)
            edge_type_count["comment"] += 1

    id2user = dict(zip(df["comment_id"].astype(str), df["user_mid"].astype(str)))
    lv2 = df[df["level"] == 2]
    for uid, pid in zip(lv2["user_mid"].astype(str), lv2["parent_id"].astype(str)):
        target = id2user.get(pid)
        if target is None or target == uid:
            continue
        e = (f"user:{uid}", f"user:{target}")
        if G.has_edge(*e):
            G[e[0]][e[1]]["w"] = G[e[0]][e[1]].get("w", 1) + 1
        else:
            G.add_edge(*e, etype="reply", w=1)
            edge_type_count["reply"] += 1

    n, m = G.number_of_nodes(), G.number_of_edges()
    avg_deg = 2 * m / n
    avg_wdeg = sum(d.get("w", 1) for _, _, d in G.edges(data=True)) * 2 / n
    density = nx.density(G)
    avg_clu = nx.average_clustering(G)

    gc_nodes = max(nx.connected_components(G), key=len)
    GC = G.subgraph(gc_nodes)
    sources = random.sample(list(gc_nodes), min(net.get("path_sample", 300), len(gc_nodes)))
    tot, cnt, ecc = 0, 0, 0
    for s in sources:
        lengths = nx.single_source_shortest_path_length(GC, s)
        tot += sum(lengths.values()); cnt += len(lengths) - 1
        ecc = max(ecc, max(lengths.values()))
    avg_path = tot / cnt
    diameter = ecc

    comms = nx.community.louvain_communities(G, seed=seed)
    modularity = nx.community.modularity(G, comms)

    metrics = {
        "节点数": n, "边数": m,
        "reply边": edge_type_count["reply"], "comment边": edge_type_count["comment"],
        "belongs_to边": edge_type_count["belongs_to"],
        "平均度": round(avg_deg, 3), "平均加权度": round(avg_wdeg, 3),
        "图密度": f"{density:.2e}", "平均聚类系数": round(avg_clu, 4),
        "平均路径长度(最大连通分量采样)": round(avg_path, 3),
        "网络直径(采样估计)": diameter,
        "最大连通分量规模": len(gc_nodes),
        "模块化指数(Louvain)": round(modularity, 3),
        "社群数量": len(comms),
    }
    dump_json(metrics, out / "network_metrics.json")
    log.info("网络指标: %s", metrics)

    # ---- 十大视频子网络 ----
    top_n = net.get("top_videos", 10)
    top10 = df["bv"].value_counts().head(top_n).index.tolist()
    rows = []
    for bv in top10:
        sub = df[df["bv"] == bv]
        Gs = nx.Graph()
        up = vmap.get(bv, "UP")
        Gs.add_edge(f"V:{bv}", f"U:{up}")
        for uid in sub[sub["level"] == 1]["user_mid"]:
            Gs.add_edge(f"user:{uid}", f"V:{bv}")
        sid2u = dict(zip(sub["comment_id"].astype(str), sub["user_mid"].astype(str)))
        for uid, pid in zip(sub[sub["level"] == 2]["user_mid"].astype(str),
                            sub[sub["level"] == 2]["parent_id"].astype(str)):
            t = sid2u.get(pid)
            if t and t != uid:
                Gs.add_edge(f"user:{uid}", f"user:{t}")
        ns, ms = Gs.number_of_nodes(), Gs.number_of_edges()
        gcs = max(nx.connected_components(Gs), key=len)
        Gcs = Gs.subgraph(gcs)
        if len(gcs) > 2000:
            srcs = random.sample(list(gcs), 100)
            t_, c_, e_ = 0, 0, 0
            for s in srcs:
                L = nx.single_source_shortest_path_length(Gcs, s)
                t_ += sum(L.values()); c_ += len(L) - 1; e_ = max(e_, max(L.values()))
            ap, dia = t_ / c_, e_
        else:
            ap = nx.average_shortest_path_length(Gcs) if len(gcs) > 1 else 0
            dia = nx.diameter(Gcs) if len(gcs) > 1 else 0
        cs = nx.community.louvain_communities(Gs, seed=seed)
        mod = nx.community.modularity(Gs, cs)
        rows.append({"BV": bv, "视频": str(tmap.get(bv, ""))[:24], "UP主": vmap.get(bv, ""),
                     "节点数": ns, "边数": ms, "平均度": round(2 * ms / ns, 3),
                     "网络直径": dia, "平均路径长度": round(ap, 3), "模块化": round(mod, 3),
                     "评论数": len(sub)})
    sub_df = pd.DataFrame(rows)
    sub_df.to_csv(out / "subnetwork_metrics.csv", index=False, encoding="utf-8-sig")
    log.info("十大视频子网络:\n%s",
             sub_df[["BV", "节点数", "边数", "平均度", "网络直径", "平均路径长度", "模块化"]].to_string())

    # ---- 整体网络可视化（采样）----
    deg = dict(G.degree())
    keep = [v for v, d in deg.items() if d >= net.get("viz_min_degree", 3)]
    Gv = G.subgraph(keep)
    gcv = max(nx.connected_components(Gv), key=len)
    Gv = Gv.subgraph(list(gcv)[: net.get("viz_max_nodes", 8000)])
    log.info("可视化子图: %d 节点 / %d 边", Gv.number_of_nodes(), Gv.number_of_edges())
    pos = nx.spring_layout(Gv, k=0.06, iterations=30, seed=seed)
    node_comm = {}
    for i, c in enumerate(comms):
        for v in c:
            node_comm[v] = i
    top_comms = Counter(node_comm.get(v, -1) for v in Gv.nodes()).most_common(8)
    palette = ["#C0392B", "#2471A3", "#E67E22", "#7D3C98", "#229954", "#D4AC0D", "#16A085", "#884EA0"]
    cmap_comm = {c: [i] for i, (c, _) in enumerate(top_comms)}
    colors = [palette[cmap_comm[node_comm.get(v, -1)][0]] if node_comm.get(v, -1) in cmap_comm else "#CCCCCC"
              for v in Gv.nodes()]
    sizes = [min(deg[v], 150) * 0.6 + 1 for v in Gv.nodes()]
    fig13 = fig / "fig13_overall_network.png"
    fig_, ax = plt.subplots(figsize=(12, 10))
    nx.draw_networkx_edges(Gv, pos, alpha=0.06, width=0.3, ax=ax)
    nx.draw_networkx_nodes(Gv, pos, node_size=sizes, node_color=colors, alpha=0.75, linewidths=0, ax=ax)
    vlabels = {v: str(tmap.get(v[2:], v))[:10] for v in Gv.nodes() if v.startswith("V:")}
    nx.draw_networkx_labels(Gv, pos, labels=vlabels, font_size=7, font_family=font_family, ax=ax)
    ax.set_title("图13 整体互动网络骨架图（度≥3节点，颜色=Louvain社群，标签=视频节点）")
    ax.axis("off"); plt.tight_layout(); savefig(fig_, fig13)

    # ---- 核心短语共现网络 ----
    phrases = resolve_phrases(cfg, df["text_clean"].astype(str))
    texts = df["text_clean"].astype(str).to_numpy(dtype="U")
    hits = phrase_hit_matrix(texts, phrases)
    Gw = nx.Graph()
    names = list(phrases.keys())
    for i, w1 in enumerate(names):
        for w2 in names[i + 1:]:
            co = int((hits[w1] & hits[w2]).sum())
            if co >= net.get("cooccur_min", 30):
                Gw.add_edge(w1, w2, weight=co)
    for wd in names:
        if wd in Gw:
            Gw.nodes[wd]["freq"] = int(hits[wd].sum())
    bet = nx.betweenness_centrality(Gw, weight=None)
    degw = dict(Gw.degree())
    wstat = pd.DataFrame({"词": list(Gw.nodes()),
                          "提及评论数": [Gw.nodes[w]["freq"] for w in Gw.nodes()],
                          "度": [degw[w] for w in Gw.nodes()],
                          "介数中心性": [round(bet[w], 4) for w in Gw.nodes()]}).sort_values("介数中心性", ascending=False)
    wstat.to_csv(out / "word_cooccur_centrality.csv", index=False, encoding="utf-8-sig")
    log.info("词共现网络: %d 节点 / %d 边 / 密度 %.4f",
             Gw.number_of_nodes(), Gw.number_of_edges(), nx.density(Gw))
    dump_json({"nodes": Gw.number_of_nodes(), "edges": Gw.number_of_edges(),
               "density": round(nx.density(Gw), 4)}, out / "word_net_stats.json")

    if Gw.number_of_nodes() > 1:
        posw = nx.spring_layout(Gw, k=1.4, weight="weight", iterations=100, seed=seed)
        freqs = np.array([Gw.nodes[w]["freq"] for w in Gw.nodes()])
        sizesw = 200 + (freqs / freqs.max()) * 4200
        bets = np.array([bet[w] for w in Gw.nodes()])
        colw = plt.cm.YlOrRd(0.25 + 0.75 * bets / max(bets.max(), 1e-9))
        ews = np.array([d["weight"] for _, _, d in Gw.edges(data=True)])
        fig14 = fig / "fig14_word_cooccur.png"
        fig_, ax = plt.subplots(figsize=(13, 10))
        nx.draw_networkx_edges(Gw, posw, width=0.2 + 3.5 * ews / ews.max(), alpha=0.25, ax=ax)
        nx.draw_networkx_nodes(Gw, posw, node_size=sizesw, node_color=colw, alpha=0.9,
                               linewidths=0.5, edgecolors="gray", ax=ax)
        nx.draw_networkx_labels(Gw, posw, font_size=10, font_family=font_family, ax=ax)
        ax.set_title("图14 核心短语共现网络（节点大小=提及评论数，颜色=介数中心性，边粗细=共现强度）")
        ax.axis("off"); plt.tight_layout(); savefig(fig_, fig14)
        fig14_out = str(fig14)
    else:
        fig14_out = None

    # ---- Gephi 资产导出（动态点边表 / 关键词网络 / 每视频子网络 / 二部网络）----
    gephi_files: list = []
    if net.get("export_gexf", True):
        from .. import gephi as gx

        # 把主题 / 情感 / 立场列并回来，供二部网络使用
        for fn, cols in (("comments_topic.csv", ["comment_id", "topic_name"]),
                         ("comments_sentiment.csv", ["comment_id", "sentiment", "stance"])):
            p = out / fn
            if not p.exists():
                continue
            try:
                extra = robust_read_csv(p, low_memory=False)
                use = [c for c in cols if c in extra.columns]
                if len(use) > 1:
                    extra = extra[use].drop_duplicates("comment_id")
                    extra["comment_id"] = extra["comment_id"].astype(str)
                    df["comment_id"] = df["comment_id"].astype(str)
                    df = df.merge(extra, on="comment_id", how="left")
            except Exception as e:
                log.warning("合并 %s 失败: %s", fn, e)

        # Louvain 社群号映射到 Gephi 节点命名（V:/U:/user: -> video_/up_/user_）
        comm_of = {}
        for i, c in enumerate(comms):
            for v in c:
                if v.startswith("V:"):
                    comm_of[f"video_{v[2:]}"] = i
                elif v.startswith("U:"):
                    comm_of[f"up_{v[2:]}"] = i
                elif v.startswith("user:"):
                    comm_of[f"user_{v[5:]}"] = i

        try:
            gephi_files = gx.export_all(cfg, df, G, Gw, vmap, tmap, comm_of)
        except Exception as e:
            log.warning("Gephi 导出失败: %s", e)
            nx.write_gexf(G, str(out / "interaction_network.gexf"))
            gephi_files = ["interaction_network.gexf"]

    figures = [(str(fig13), "图13 整体互动网络骨架", "度≥3 节点采样，颜色为 Louvain 社群，标签为视频节点。")]
    if fig14_out:
        figures.append((fig14_out, "图14 核心短语共现网络", "节点大小=提及评论数，颜色=介数中心性，边=共现强度。"))

    return {
        "stats": {
            "nodes": n, "edges": m,
            "modularity": round(modularity, 3),
            "density": f"{density:.2e}",
            "avg_path": round(avg_path, 3),
            "communities": len(comms),
            "word_net_nodes": Gw.number_of_nodes(),
            "word_net_edges": Gw.number_of_edges(),
        },
        "figures": figures,
        "data_files": ["network_metrics.json", "subnetwork_metrics.csv",
                       "word_cooccur_centrality.csv", "word_net_stats.json"] + gephi_files,
    }
