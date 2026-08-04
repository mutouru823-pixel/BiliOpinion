# -*- coding: utf-8 -*-
"""全局默认配置。用户 YAML 只需覆盖需要改动的字段，其余走这里的缺省值。"""

DEFAULTS = {
    "project": {
        "name": "my_event",          # 输出子目录名，建议英文/拼音
        "topic": "",                 # 事件主题，如 "鹅腿阿姨"；为空时取 crawl.keywords[0]
        "output_dir": "outputs",     # 相对仓库根目录
    },

    # ---------------- Step0 采集 ----------------
    "crawl": {
        "enabled": True,
        "keywords": [],              # 为空时自动用 project.topic
        "max_pages": 3,              # 每个关键词翻多少页搜索结果（每页约 20 个视频）
        "max_videos": 50,            # 总共最多爬多少个视频的评论
        "order": "click",            # click 播放量 / pubdate 最新 / dm 弹幕 / stow 收藏
        "max_reply_pages": 0,        # 二级评论最大页数，0 = 不限（穷尽）
        "request_delay": 0.5,        # 每页请求间隔秒
        "reply_delay": 0.3,
        "video_delay": 1.5,
        "pubtime_begin": "",         # 可选，"2023-01-01"，按视频发布时间过滤
        "pubtime_end": "",
        "cookie": "",                # 留空则读环境变量 BILI_COOKIE / .env
    },

    # ---------------- Step1 清洗 ----------------
    "clean": {
        "min_length": 1,             # 清洗后最短字符数
        "strip_reply_prefix": True,  # 去除 "回复 @xxx :" 前缀但保留正文
        "strip_emote": True,         # 去除 [doge] 类表情
        "strip_url": True,
        "drop_mojibake": True,       # 丢弃仍含替换符的乱码行
    },

    # ---------------- 传播阶段划分 ----------------
    "phases": {
        "mode": "auto",              # auto 自动断点检测 / manual 手工指定
        "manual": [],                # [{name: "P1启动期", end: "2025-11-06"}, ...]
        "auto": {
            "start_ratio": 0.10,     # 日评论量达到峰值该比例 → 进入启动期
            "peak_ratio": 0.50,      # 达到峰值该比例 → 高峰期
            "decay_ratio": 0.10,     # 跌破峰值该比例 → 衰减结束
            "resurge_ratio": 0.20,   # 后期再次超过峰值该比例 → 二次发酵
            "min_gap_days": 2,       # 相邻断点最小间隔
        },
    },

    # ---------------- Step2 核心短语 / 词云 ----------------
    "phrases": {
        "mode": "auto",              # auto 自动抽取 / manual 手工词典 / hybrid 两者合并
        "top_n": 24,                 # 自动模式抽取多少个核心短语
        "min_len": 2,
        "manual": {},                # {"鹅腿": ["鹅腿","烤鹅腿"], "鸭腿": ["鸭腿"]}
        "heatmap_top": 22,
    },

    # ---------------- Step3 主题 ----------------
    "topics": {
        "mode": "auto",              # auto 纯无监督命名 / codebook 词典优先级分类
        "explore": {
            "enabled": True,
            "sample_size": 12000,
            "k_range": [4, 9],
            "max_features": 8000,
            "svd_components": 100,
        },
        "codebook": {
            "order": [],             # 优先级，如 [A, D, E, B, C]
            "categories": {},        # {A: {name: "...", keywords: [...]}}
            "fallback": "F",         # 未命中的类别代码
            "fallback_name": "F无关信息",
            "short_to": "",          # 未命中且极短的评论归入哪一类（论文里归 C 纯互动）
            "short_maxlen": 15,
        },
    },

    # ---------------- Step4 情感与立场 ----------------
    "sentiment": {
        "enabled": True,
        "engine": "snownlp",
        "pos_threshold": 0.6,
        "neg_threshold": 0.4,
        "max_chars": 200,            # SnowNLP 截断长度
        "stance": {                  # 立场规则词典，留空则跳过立场分析
            "enabled": False,
            "pos_name": "支持/采信",
            "neg_name": "质疑/反对",
            "pos_words": [],
            "neg_words": [],
        },
    },

    # ---------------- Step5 社会网络 ----------------
    "network": {
        "enabled": True,
        "top_videos": 10,            # 子网络对比取前 N 个视频
        "viz_min_degree": 3,
        "viz_max_nodes": 8000,
        "path_sample": 300,          # 平均路径长度 BFS 采样源点数
        "cooccur_min": 30,           # 词共现最小共现评论数
        # --- Gephi 导出 ---
        "export_gexf": True,         # 总开关：动态点边表 + 关键词网络 + GEXF 套件
        "export_per_video": True,    # 每个热门视频单独导出一个 GEXF
        "per_video_top_n": 10,       # 导出前 N 个视频的子网络
    },

    # ---------------- Step6-8 BERT ----------------
    "bert": {
        "enabled": False,            # 需要 torch + transformers，默认关闭
        "model": "hfl/chinese-bert-wwm-ext",
        "max_len": 64,
        "batch_size": 64,
        "quantize": True,            # CPU 动态 INT8 量化提速
        "max_samples": 0,            # >0 时随机抽样这么多条做嵌入（省算力）
        "topic": {
            "enabled": True,
            "pca_components": 48,
            "k_range": [5, 13],
            "silhouette_sample": 20000,
            "min_term_freq": 30,
        },
        "sentiment": {
            "enabled": True,
            "pos_pseudo": 0.85,      # SnowNLP 伪标签阈值
            "neg_pseudo": 0.15,
            "neu_pseudo": [0.45, 0.55],
            "max_per_class": 12000,
        },
    },

    # ---------------- Step9 报告 ----------------
    "report": {
        "html": True,
        "docx": False,
        "title": "",                 # 留空自动生成
    },

    # ---------------- 运行环境 ----------------
    "runtime": {
        "font": "",                  # 中文字体路径，留空自动探测
        "random_seed": 42,
        "figure_dpi": 150,
    },
}
