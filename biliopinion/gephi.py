# -*- coding: utf-8 -*-
"""
Gephi 导出套件
================================================================
复现课程作业中的 Gephi 动态网络工作流，产出可直接拖进 Gephi 的文件：

1. gephi_nodes.csv / gephi_edges.csv
   —— 带 Timestamp + Datetime + RGB 预染色的**动态网络**点边表
      （Gephi 中开启 Timeline 即可播放舆情演化动画）
2. keyword_nodes.csv / keyword_edges.csv
   —— 核心短语共现网络，带 Modularity Class / Size / RGB
3. networks/video_<BV>.gexf      —— 每个热门视频的独立子网络
4. networks/topic_bipartite.gexf —— 用户–主题二部网络
5. networks/sentiment_bipartite.gexf —— 用户–情感二部网络
6. networks/interaction_full.gexf —— 整体交互网络

节点 ID 约定与原作业保持一致：video_<BV> / up_<UP名> / user_<mid>
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import networkx as nx

from .utils import get_logger

log = get_logger()

# 与原作业一致的类型配色（R,G,B）
TYPE_COLOR = {
    "视频": (50, 120, 220),
    "UP主": (220, 50, 50),
    "用户": (150, 150, 150),
    "主题": (240, 160, 40),
    "情感": (60, 180, 120),
}

# Louvain 社群调色板
PALETTE = [
    (192, 57, 43), (36, 113, 163), (230, 126, 34), (125, 60, 152),
    (34, 153, 84), (212, 172, 13), (22, 160, 133), (136, 78, 160),
    (231, 76, 60), (52, 152, 219), (243, 156, 18), (155, 89, 182),
]

SENTI_COLOR = {"正面": (46, 160, 67), "负面": (200, 55, 55), "中性": (150, 150, 150)}


def _ts(dt) -> tuple:
    """返回 (unix秒, 中文可读时间)；无效时间返回 ('','')"""
    if pd.isna(dt):
        return "", ""
    try:
        t = pd.Timestamp(dt)
        return int(t.timestamp()), t.strftime("%Y年%m月%d日 %H:%M")
    except Exception:
        return "", ""


def _safe(name: str, limit: int = 60) -> str:
    """文件名安全化"""
    bad = '\\/:*?"<>|\n\r\t'
    s = "".join("_" if c in bad else c for c in str(name))
    return s.strip()[:limit] or "unnamed"


# --------------------------------------------------------------------------
# 1. 动态交互网络点边表
# --------------------------------------------------------------------------
def export_dynamic_edgelist(df: pd.DataFrame, vmap: dict, tmap: dict,
                            out: Path, comm_of: dict | None = None) -> list:
    """
    导出带时间戳与颜色的点边表，供 Gephi Timeline 动态演化使用。

    df   : comments_valid.csv（需含 bv/user_mid/username/level/parent_id/comment_id/created_at）
    vmap : bv -> UP主名
    tmap : bv -> 视频标题
    comm_of : 可选，节点 -> Louvain 社群号（用于按社群染色）
    """
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def touch(nid, label, ntype, dt):
        ts, dts = _ts(dt)
        if nid not in nodes:
            r, g, b = TYPE_COLOR.get(ntype, (150, 150, 150))
            nodes[nid] = {"Id": nid, "Label": str(label)[:80], "Type": ntype,
                          "Timestamp": ts, "Datetime": dts, "R": r, "G": g, "B": b}
        elif nodes[nid]["Timestamp"] == "" and ts != "":
            nodes[nid]["Timestamp"], nodes[nid]["Datetime"] = ts, dts

    # --- 视频首条评论时间近似为视频入场时间 ---
    first_seen = df.groupby("bv")["created_at"].min().to_dict()

    for bv in df["bv"].dropna().unique():
        up = vmap.get(bv, f"UP_{bv}")
        dt = first_seen.get(bv)
        touch(f"video_{bv}", tmap.get(bv, bv), "视频", dt)
        touch(f"up_{up}", up, "UP主", dt)
        ts, dts = _ts(dt)
        edges.append({"Source": f"video_{bv}", "Target": f"up_{up}",
                      "Type": "belongs_to", "Weight": 1,
                      "Timestamp": ts, "Datetime": dts})

    # --- 用户 -> 视频（一级评论）---
    lv1 = df[df["level"] == 1]
    agg1: dict[tuple, dict] = {}
    for uid, uname, bv, dt in zip(lv1["user_mid"], lv1.get("username", lv1["user_mid"]),
                                  lv1["bv"], lv1["created_at"]):
        nid = f"user_{uid}"
        touch(nid, uname, "用户", dt)
        key = (nid, f"video_{bv}")
        ts, dts = _ts(dt)
        if key in agg1:
            agg1[key]["Weight"] += 1
        else:
            agg1[key] = {"Source": key[0], "Target": key[1], "Type": "comment",
                         "Weight": 1, "Timestamp": ts, "Datetime": dts}
    edges.extend(agg1.values())

    # --- 用户 -> 用户（二级回复）---
    id2user = dict(zip(df["comment_id"].astype(str), df["user_mid"].astype(str)))
    lv2 = df[df["level"] == 2]
    agg2: dict[tuple, dict] = {}
    for uid, uname, pid, dt in zip(lv2["user_mid"].astype(str),
                                   lv2.get("username", lv2["user_mid"]),
                                   lv2["parent_id"].astype(str), lv2["created_at"]):
        tgt = id2user.get(pid)
        if tgt is None or tgt == uid:
            continue
        touch(f"user_{uid}", uname, "用户", dt)
        touch(f"user_{tgt}", tgt, "用户", dt)
        key = (f"user_{uid}", f"user_{tgt}")
        ts, dts = _ts(dt)
        if key in agg2:
            agg2[key]["Weight"] += 1
        else:
            agg2[key] = {"Source": key[0], "Target": key[1], "Type": "reply",
                         "Weight": 1, "Timestamp": ts, "Datetime": dts}
    edges.extend(agg2.values())

    # --- 若提供社群划分，按社群覆盖用户节点颜色 ---
    if comm_of:
        for nid, nd in nodes.items():
            c = comm_of.get(nid)
            if c is not None:
                nd["R"], nd["G"], nd["B"] = PALETTE[c % len(PALETTE)]

    ndf = pd.DataFrame(nodes.values())
    edf = pd.DataFrame(edges)
    ndf.to_csv(out / "gephi_nodes.csv", index=False, encoding="utf-8-sig")
    edf.to_csv(out / "gephi_edges.csv", index=False, encoding="utf-8-sig")
    log.info("动态网络点边表: %d 节点 / %d 边 -> gephi_nodes.csv, gephi_edges.csv",
             len(ndf), len(edf))
    return ["gephi_nodes.csv", "gephi_edges.csv"]


# --------------------------------------------------------------------------
# 2. 关键词共现网络点边表
# --------------------------------------------------------------------------
def export_keyword_network(Gw: nx.Graph, out: Path) -> list:
    """导出核心短语共现网络（含 Modularity Class / Size / RGB）"""
    if Gw.number_of_nodes() == 0:
        log.warning("词共现网络为空，跳过 Gephi 导出")
        return []

    try:
        comms = nx.community.louvain_communities(Gw, seed=42)
    except Exception:
        comms = [set(Gw.nodes())]
    comm_of = {v: i for i, c in enumerate(comms) for v in c}

    freqs = {w: Gw.nodes[w].get("freq", 1) for w in Gw.nodes()}
    fmax = max(freqs.values()) or 1

    rows = []
    for w in Gw.nodes():
        c = comm_of.get(w, 0)
        r, g, b = PALETTE[c % len(PALETTE)]
        rows.append({"Id": w, "Label": w, "Weight": freqs[w],
                     "Modularity Class": c, "R": r, "G": g, "B": b,
                     "Size": round(10 + 40 * freqs[w] / fmax, 1)})
    pd.DataFrame(rows).to_csv(out / "keyword_nodes.csv", index=False, encoding="utf-8-sig")

    erows = [{"Source": u, "Target": v, "Type": "Undirected",
              "Weight": d.get("weight", 1)} for u, v, d in Gw.edges(data=True)]
    pd.DataFrame(erows).to_csv(out / "keyword_edges.csv", index=False, encoding="utf-8-sig")

    log.info("关键词共现网络: %d 节点 / %d 边 / %d 社群 -> keyword_nodes.csv, keyword_edges.csv",
             Gw.number_of_nodes(), Gw.number_of_edges(), len(comms))
    return ["keyword_nodes.csv", "keyword_edges.csv"]


# --------------------------------------------------------------------------
# 3. 每视频子网络 GEXF
# --------------------------------------------------------------------------
def export_per_video_gexf(df: pd.DataFrame, vmap: dict, tmap: dict,
                          netdir: Path, top_n: int = 10) -> list:
    """为评论量最高的 top_n 个视频各导出一个 GEXF"""
    netdir.mkdir(parents=True, exist_ok=True)
    top = df["bv"].value_counts().head(top_n).index.tolist()
    written = []

    for bv in top:
        sub = df[df["bv"] == bv]
        up = vmap.get(bv, f"UP_{bv}")
        title = tmap.get(bv, bv)
        g = nx.Graph()
        g.add_node(f"video_{bv}", label=str(title)[:60], ntype="视频")
        g.add_node(f"up_{up}", label=str(up), ntype="UP主")
        g.add_edge(f"video_{bv}", f"up_{up}", etype="belongs_to", weight=1)

        for uid in sub[sub["level"] == 1]["user_mid"]:
            nid = f"user_{uid}"
            if not g.has_node(nid):
                g.add_node(nid, label=str(uid), ntype="用户")
            if g.has_edge(nid, f"video_{bv}"):
                g[nid][f"video_{bv}"]["weight"] += 1
            else:
                g.add_edge(nid, f"video_{bv}", etype="comment", weight=1)

        id2user = dict(zip(sub["comment_id"].astype(str), sub["user_mid"].astype(str)))
        for uid, pid in zip(sub[sub["level"] == 2]["user_mid"].astype(str),
                            sub[sub["level"] == 2]["parent_id"].astype(str)):
            tgt = id2user.get(pid)
            if tgt is None or tgt == uid:
                continue
            for x in (f"user_{uid}", f"user_{tgt}"):
                if not g.has_node(x):
                    g.add_node(x, label=x.replace("user_", ""), ntype="用户")
            if g.has_edge(f"user_{uid}", f"user_{tgt}"):
                g[f"user_{uid}"][f"user_{tgt}"]["weight"] += 1
            else:
                g.add_edge(f"user_{uid}", f"user_{tgt}", etype="reply", weight=1)

        fn = netdir / f"video_{bv}_{_safe(title, 40)}.gexf"
        nx.write_gexf(g, str(fn))
        written.append(fn.name)

    log.info("每视频子网络 GEXF: %d 个 -> %s", len(written), netdir.name)
    return written


# --------------------------------------------------------------------------
# 4. 二部网络（用户–主题 / 用户–情感）
# --------------------------------------------------------------------------
def export_bipartite_gexf(df: pd.DataFrame, col: str, netdir: Path,
                          fname: str, cat_color: dict | None = None,
                          min_user_edges: int = 1) -> str | None:
    """
    用户–<col> 二部网络。col 可为 topic_name / sentiment 等。
    """
    if col not in df.columns:
        log.warning("列 %s 不存在，跳过 %s", col, fname)
        return None

    netdir.mkdir(parents=True, exist_ok=True)
    g = nx.Graph()
    pair = df.groupby(["user_mid", col]).size().reset_index(name="w")
    pair = pair[pair["w"] >= min_user_edges]

    for cat in df[col].dropna().unique():
        r, g_, b = (cat_color or {}).get(cat, TYPE_COLOR["主题"])
        g.add_node(f"cat_{cat}", label=str(cat), ntype="类别", r=r, g=g_, b=b)

    for uid, cat, w in zip(pair["user_mid"], pair[col], pair["w"]):
        nid = f"user_{uid}"
        if not g.has_node(nid):
            g.add_node(nid, label=str(uid), ntype="用户")
        g.add_edge(nid, f"cat_{cat}", weight=int(w))

    fn = netdir / fname
    nx.write_gexf(g, str(fn))
    log.info("二部网络 %s: %d 节点 / %d 边", fname, g.number_of_nodes(), g.number_of_edges())
    return fn.name


# --------------------------------------------------------------------------
# 总入口
# --------------------------------------------------------------------------
def export_all(cfg, df: pd.DataFrame, G: nx.Graph, Gw: nx.Graph,
               vmap: dict, tmap: dict, comm_of: dict | None = None) -> list:
    """在 step5 末尾统一调用，产出全部 Gephi 资产"""
    out = cfg.dir_data
    netdir = out / "networks"
    netdir.mkdir(parents=True, exist_ok=True)
    files: list[str] = []

    gcfg = cfg["network"]

    # 整体网络 GEXF
    full = netdir / "interaction_full.gexf"
    nx.write_gexf(G, str(full))
    files.append(f"networks/{full.name}")

    # 动态点边表
    try:
        files += export_dynamic_edgelist(df, vmap, tmap, out, comm_of)
    except Exception as e:
        log.warning("动态点边表导出失败: %s", e)

    # 关键词共现
    try:
        files += export_keyword_network(Gw, out)
    except Exception as e:
        log.warning("关键词网络导出失败: %s", e)

    # 每视频子网络
    if gcfg.get("export_per_video", True):
        try:
            files += [f"networks/{x}" for x in
                      export_per_video_gexf(df, vmap, tmap, netdir,
                                            gcfg.get("per_video_top_n", 10))]
        except Exception as e:
            log.warning("每视频网络导出失败: %s", e)

    # 主题 / 情感二部网络
    for col, fname, colors in (("topic_name", "topic_bipartite.gexf", None),
                               ("sentiment", "sentiment_bipartite.gexf", SENTI_COLOR),
                               ("stance", "stance_bipartite.gexf", None)):
        try:
            r = export_bipartite_gexf(df, col, netdir, fname, colors)
            if r:
                files.append(f"networks/{r}")
        except Exception as e:
            log.warning("二部网络 %s 导出失败: %s", fname, e)

    log.info("Gephi 资产共 %d 个文件，位于 %s", len(files), out)
    return files
