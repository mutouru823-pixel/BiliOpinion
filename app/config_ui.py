# -*- coding: utf-8 -*-
"""配置表单：dict <-> Streamlit widgets 双向转换。

表单只暴露 README 列的「常用开关」，高级字段折叠在 expander，
另提供 yaml 原文编辑模式。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st
import yaml

from biliopinion.defaults import DEFAULTS
from biliopinion.config import REPO_ROOT


# ----------------------------------------------------------------------
# dict <-> yaml
# ----------------------------------------------------------------------
def dict_to_yaml(cfg_dict: dict) -> str:
    return yaml.safe_dump(cfg_dict, allow_unicode=True, sort_keys=False)


def yaml_to_dict(text: str) -> dict:
    return yaml.safe_load(text) or {}


# ----------------------------------------------------------------------
# 默认配置（DEFAULTS 的浅拷贝，剥掉内部字段）
# ----------------------------------------------------------------------
def default_config() -> dict:
    import copy
    return copy.deepcopy(DEFAULTS)


def load_config_file(path: Path) -> dict:
    if not path.exists():
        return default_config()
    try:
        user = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return default_config()
    # 深合并 DEFAULTS + user
    base = default_config()
    return _deep_merge(base, user)


def _deep_merge(base: dict, override: dict) -> dict:
    import copy
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if v is None:
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


# ----------------------------------------------------------------------
# 表单渲染
# ----------------------------------------------------------------------
def render_config_form(initial: dict, cookie: str = "") -> dict:
    """渲染配置表单，返回用户编辑后的 dict。

    cookie 单独从参数传入（密码框），最终注入到 crawl.cookie，
    但不会落盘到 yaml（写入时清空）。
    """
    cfg = dict(initial)  # 浅拷贝顶层，子字段引用相同
    # 我们对每个字段单独建 widget，所以需要做深拷贝避免污染
    import copy
    cfg = copy.deepcopy(initial)

    # ===== project =====
    with st.expander("📁 项目", expanded=True):
        proj = cfg.setdefault("project", {})
        proj["name"] = st.text_input(
            "项目名 (输出子目录名，建议英文/拼音)",
            value=proj.get("name", "my_event"),
            help="最终产物在 outputs/<项目名>/")
        proj["topic"] = st.text_input(
            "舆情主题",
            value=proj.get("topic", ""),
            help="如「某热点事件」。留空则自动取 crawl.keywords[0]")
        proj["output_dir"] = st.text_input(
            "输出根目录",
            value=proj.get("output_dir", "outputs"),
            help="相对仓库根目录")

    # ===== crawl =====
    with st.expander("🕷️ 采集 (Step0)", expanded=True):
        cr = cfg.setdefault("crawl", {})
        cr["enabled"] = st.checkbox("启用采集（false=用已有 raw/ 跑后续分析）",
                                    value=cr.get("enabled", True))
        kw = cr.get("keywords") or []
        if isinstance(kw, str):
            kw = [kw]
        cr["keywords"] = st.text_input(
            "搜索关键词（逗号分隔，留空取 topic）",
            value=", ".join(kw),
        ).split(",")
        cr["keywords"] = [k.strip() for k in cr["keywords"] if k.strip()]
        col1, col2 = st.columns(2)
        with col1:
            cr["max_pages"] = st.number_input(
                "搜索结果页数", min_value=1, max_value=50,
                value=int(cr.get("max_pages", 3)),
                help="每页约 20 个视频")
            cr["max_videos"] = st.number_input(
                "最多抓视频数", min_value=1, max_value=500,
                value=int(cr.get("max_videos", 50)))
            cr["order"] = st.selectbox(
                "排序",
                options=["click", "pubdate", "dm", "stow"],
                index=["click", "pubdate", "dm", "stow"].index(cr.get("order", "click")),
                format_func=lambda x: {"click": "播放量", "pubdate": "最新",
                                       "dm": "弹幕", "stow": "收藏"}[x])
        with col2:
            cr["max_reply_pages"] = st.number_input(
                "二级评论最大页数 (0=穷尽)",
                min_value=0, max_value=200,
                value=int(cr.get("max_reply_pages", 0)))
            cr["request_delay"] = st.number_input(
                "请求间隔(秒)", min_value=0.0, max_value=10.0,
                value=float(cr.get("request_delay", 0.5)), step=0.1)
            cr["video_delay"] = st.number_input(
                "视频间隔(秒)", min_value=0.0, max_value=30.0,
                value=float(cr.get("video_delay", 1.5)), step=0.1)
        col1, col2 = st.columns(2)
        with col1:
            cr["pubtime_begin"] = st.text_input(
                "视频发布时间起 (可选, YYYY-MM-DD)",
                value=cr.get("pubtime_begin", ""))
        with col2:
            cr["pubtime_end"] = st.text_input(
                "视频发布时间止 (可选, YYYY-MM-DD)",
                value=cr.get("pubtime_end", ""))
        # cookie：不展示，由调用方注入
        cr["cookie"] = ""

    # ===== clean =====
    with st.expander("🧹 清洗 (Step1)"):
        cl = cfg.setdefault("clean", {})
        cl["min_length"] = st.number_input(
            "清洗后最短字符数", min_value=1, max_value=50,
            value=int(cl.get("min_length", 1)))
        cl["strip_reply_prefix"] = st.checkbox("去「回复 @xxx:」前缀",
                                                value=cl.get("strip_reply_prefix", True))
        cl["strip_emote"] = st.checkbox("去 [doge] 类表情",
                                        value=cl.get("strip_emote", True))
        cl["strip_url"] = st.checkbox("去 URL", value=cl.get("strip_url", True))
        cl["drop_mojibake"] = st.checkbox("丢乱码行", value=cl.get("drop_mojibake", True))

    # ===== phases =====
    with st.expander("📅 阶段划分 (Step2)"):
        ph = cfg.setdefault("phases", {})
        ph["mode"] = st.radio(
            "模式",
            options=["auto", "manual"],
            index=["auto", "manual"].index(ph.get("mode", "auto")),
            format_func=lambda x: {"auto": "auto 自动断点 (推荐)",
                                   "manual": "manual 手工指定"}[x])
        if ph["mode"] == "auto":
            au = ph.setdefault("auto", {})
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                au["start_ratio"] = st.slider("启动阈值", 0.0, 1.0,
                                              float(au.get("start_ratio", 0.10)), 0.05)
            with col2:
                au["peak_ratio"] = st.slider("高峰阈值", 0.0, 1.0,
                                              float(au.get("peak_ratio", 0.50)), 0.05)
            with col3:
                au["decay_ratio"] = st.slider("衰减阈值", 0.0, 1.0,
                                              float(au.get("decay_ratio", 0.10)), 0.05)
            with col4:
                au["resurge_ratio"] = st.slider("二次发酵阈值", 0.0, 1.0,
                                                 float(au.get("resurge_ratio", 0.20)), 0.05)
        else:
            manual_text = st.text_area(
                "manual 阶段列表（YAML 数组）",
                value=yaml.safe_dump(ph.get("manual", []),
                                    allow_unicode=True, sort_keys=False),
                help='格式: [{name: "P1启动期", end: "2025-11-06"}, ...]')
            try:
                ph["manual"] = yaml.safe_load(manual_text) or []
            except Exception as e:
                st.error(f"manual 解析失败: {e}")
                ph["manual"] = []

    # ===== phrases =====
    with st.expander("☁️ 核心短语 (Step2)"):
        pp = cfg.setdefault("phrases", {})
        pp["mode"] = st.radio(
            "模式",
            options=["auto", "manual", "hybrid"],
            index=["auto", "manual", "hybrid"].index(pp.get("mode", "auto")),
            format_func=lambda x: {"auto": "auto 自动抽取",
                                    "manual": "manual 手写词典",
                                    "hybrid": "hybrid 二者合并"}[x])
        col1, col2 = st.columns(2)
        with col1:
            pp["top_n"] = st.number_input("top_n 抽取数", 5, 100,
                                           int(pp.get("top_n", 24)))
            pp["min_len"] = st.number_input("min_len", 1, 10,
                                              int(pp.get("min_len", 2)))
        with col2:
            pp["heatmap_top"] = st.number_input("heatmap_top", 5, 100,
                                                 int(pp.get("heatmap_top", 22)))
        if pp["mode"] in ("manual", "hybrid"):
            mt = st.text_area(
                "手写词典 (YAML dict, {阶段名: [短语, ...]})",
                value=yaml.safe_dump(pp.get("manual", {}),
                                     allow_unicode=True, sort_keys=False))
            try:
                pp["manual"] = yaml.safe_load(mt) or {}
            except Exception as e:
                st.error(f"manual 解析失败: {e}")

    # ===== topics =====
    with st.expander("🏷️ 主题 (Step3)"):
        tp = cfg.setdefault("topics", {})
        tp["mode"] = st.radio(
            "模式",
            options=["auto", "codebook"],
            index=["auto", "codebook"].index(tp.get("mode", "auto")),
            format_func=lambda x: {"auto": "auto 无监督 TF-IDF+KMeans",
                                    "codebook": "codebook 编码手册优先级分类"}[x])
        ex = tp.setdefault("explore", {})
        col1, col2 = st.columns(2)
        with col1:
            ex["enabled"] = st.checkbox("explore.enabled", value=ex.get("enabled", True))
            ex["sample_size"] = st.number_input("sample_size", 1000, 100000,
                                                  int(ex.get("sample_size", 12000)), step=1000)
        with col2:
            ex["k_range"] = st.text_input(
                "k_range (逗号分隔)",
                value=", ".join(str(x) for x in ex.get("k_range", [4, 9])))
            try:
                ex["k_range"] = [int(x.strip()) for x in ex["k_range"].split(",")]
            except Exception:
                ex["k_range"] = [4, 9]
            ex["max_features"] = st.number_input("max_features", 1000, 50000,
                                                   int(ex.get("max_features", 8000)), step=1000)
        if tp["mode"] == "codebook":
            cb = tp.setdefault("codebook", {})
            cb["order"] = st.text_input(
                "order 优先级（逗号分隔，留空取全部）",
                value=", ".join(cb.get("order", [])))
            cb["order"] = [x.strip() for x in cb["order"].split(",") if x.strip()]
            cb["fallback"] = st.text_input("fallback 类别代码",
                                            value=cb.get("fallback", "F"))
            cb["fallback_name"] = st.text_input("fallback 名称",
                                                  value=cb.get("fallback_name", "F无关信息"))
            cb_text = st.text_area(
                "categories 编码手册 (YAML)",
                value=yaml.safe_dump(cb.get("categories", {}),
                                     allow_unicode=True, sort_keys=False),
                help='格式: {A: {name: "A事件核心", keywords: ["词1","词2"]}, ...}')
            try:
                cb["categories"] = yaml.safe_load(cb_text) or {}
            except Exception as e:
                st.error(f"categories 解析失败: {e}")

    # ===== sentiment =====
    with st.expander("😊 情感与立场 (Step4)"):
        sn = cfg.setdefault("sentiment", {})
        sn["enabled"] = st.checkbox("启用情感分析", value=sn.get("enabled", True))
        sn["engine"] = st.selectbox("引擎", options=["snownlp"],
                                     index=0)
        col1, col2 = st.columns(2)
        with col1:
            sn["pos_threshold"] = st.slider("正向阈值", 0.0, 1.0,
                                              float(sn.get("pos_threshold", 0.6)), 0.05)
            sn["max_chars"] = st.number_input("max_chars", 50, 1000,
                                                int(sn.get("max_chars", 200)))
        with col2:
            sn["neg_threshold"] = st.slider("负向阈值", 0.0, 1.0,
                                              float(sn.get("neg_threshold", 0.4)), 0.05)
        stc = sn.setdefault("stance", {})
        stc["enabled"] = st.checkbox("启用立场分析", value=stc.get("enabled", False))
        if stc["enabled"]:
            stc["pos_name"] = st.text_input("立场正向名称",
                                             value=stc.get("pos_name", "支持/采信"))
            stc["neg_name"] = st.text_input("立场负向名称",
                                             value=stc.get("neg_name", "质疑/反对"))
            stc["pos_words"] = st.text_input(
                "正向词 (逗号分隔)",
                value=", ".join(stc.get("pos_words", []))).split(",")
            stc["pos_words"] = [w.strip() for w in stc["pos_words"] if w.strip()]
            stc["neg_words"] = st.text_input(
                "负向词 (逗号分隔)",
                value=", ".join(stc.get("neg_words", []))).split(",")
            stc["neg_words"] = [w.strip() for w in stc["neg_words"] if w.strip()]

    # ===== network =====
    with st.expander("🕸️ 社会网络 (Step5)"):
        nw = cfg.setdefault("network", {})
        nw["enabled"] = st.checkbox("启用网络分析", value=nw.get("enabled", True))
        col1, col2 = st.columns(2)
        with col1:
            nw["top_videos"] = st.number_input("top_videos", 1, 50,
                                                  int(nw.get("top_videos", 10)))
            nw["cooccur_min"] = st.number_input("cooccur_min", 1, 1000,
                                                  int(nw.get("cooccur_min", 30)))
        with col2:
            nw["viz_max_nodes"] = st.number_input("viz_max_nodes", 100, 50000,
                                                    int(nw.get("viz_max_nodes", 8000)), step=500)
            nw["path_sample"] = st.number_input("path_sample", 10, 1000,
                                                  int(nw.get("path_sample", 300)))
        nw["export_gexf"] = st.checkbox("导出 Gephi 套件", value=nw.get("export_gexf", True))
        nw["export_per_video"] = st.checkbox("每视频导出子网络",
                                              value=nw.get("export_per_video", True))
        if nw["export_per_video"]:
            nw["per_video_top_n"] = st.number_input("per_video_top_n", 1, 50,
                                                      int(nw.get("per_video_top_n", 10)))

    # ===== bert =====
    with st.expander("🤖 BERT 深度分析 (Step6-8, 可选)"):
        bt = cfg.setdefault("bert", {})
        bt["enabled"] = st.checkbox("启用 BERT (需 torch + transformers)",
                                     value=bt.get("enabled", False))
        if bt["enabled"]:
            bt["model"] = st.text_input("model", value=bt.get("model", "hfl/chinese-bert-wwm-ext"))
            col1, col2 = st.columns(2)
            with col1:
                bt["max_len"] = st.number_input("max_len", 16, 512,
                                                  int(bt.get("max_len", 64)))
                bt["batch_size"] = st.number_input("batch_size", 1, 256,
                                                     int(bt.get("batch_size", 64)))
            with col2:
                bt["quantize"] = st.checkbox("quantize CPU INT8",
                                                value=bt.get("quantize", True))
                bt["max_samples"] = st.number_input("max_samples (0=全量)",
                                                      0, 1000000,
                                                      int(bt.get("max_samples", 0)), step=1000)
            btt = bt.setdefault("topic", {})
            btt["enabled"] = st.checkbox("topic.enabled", value=btt.get("enabled", True))
            bts = bt.setdefault("sentiment", {})
            bts["enabled"] = st.checkbox("sentiment.enabled", value=bts.get("enabled", True))

    # ===== report =====
    with st.expander("📊 报告 (Step9)"):
        rp = cfg.setdefault("report", {})
        rp["html"] = st.checkbox("生成 HTML 报告", value=rp.get("html", True))
        rp["docx"] = st.checkbox("生成 docx (需 python-docx)", value=rp.get("docx", False))
        rp["title"] = st.text_input("报告标题 (留空自动)", value=rp.get("title", ""))

    # ===== runtime =====
    with st.expander("⚙️ 运行环境"):
        rt = cfg.setdefault("runtime", {})
        rt["random_seed"] = st.number_input("random_seed", 0, 99999,
                                              int(rt.get("random_seed", 42)))
        rt["figure_dpi"] = st.number_input("figure_dpi", 72, 300,
                                             int(rt.get("figure_dpi", 150)))
        rt["font"] = st.text_input("中文字体路径 (留空自动探测)",
                                     value=rt.get("font", ""))

    return cfg


def save_config(cfg: dict, project_name: str, cookie: str = "") -> Path:
    """保存配置到 outputs/<name>/.state/config.yaml。

    cookie 不写入 yaml 文件（写入时清空 crawl.cookie），
    实际运行时通过 --cookie 参数从环境变量注入。
    """
    import copy
    from app.paths import writable_base
    out = copy.deepcopy(cfg)
    # 确保 project.name 一致
    out.setdefault("project", {})["name"] = project_name
    # 不持久化 cookie
    out.setdefault("crawl", {})["cookie"] = ""

    target = (writable_base() / "outputs" / project_name / ".state" / "config.yaml")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False),
                       encoding="utf-8")
    return target
