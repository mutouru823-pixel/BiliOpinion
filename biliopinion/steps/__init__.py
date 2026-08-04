# -*- coding: utf-8 -*-
"""五步核心分析：清洗 / 时间演化 / 主题 / 情感 / 社会网络。

每个 step 暴露 run(cfg) -> dict，返回结构：
    {
        "stats":     {...标量指标...},
        "figures":   [(path, title, caption), ...],
        "data_files":[...中间产物文件名...],
    }
顶层编排器（main）收集所有 step 的返回，交给 Step9 生成自包含 HTML 报告。
"""
