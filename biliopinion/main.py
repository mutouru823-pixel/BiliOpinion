# -*- coding: utf-8 -*-
"""
BiliOpinion 管线编排器。

按依赖顺序运行各 step，收集产出，最后生成自包含 HTML 报告（可选 docx）。
用法见 README / CLI（biliopinion/cli.py）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from .config import load_config, dump_effective_config
from .utils import get_logger, banner

log = get_logger()

from . import crawler
from .steps import (step1_clean, step2_timeline, step3_topic, step4_sentiment,
                    step5_network, step6_bert_embed, step7_bert_topic, step8_bert_sentiment)
from . import report as report_mod


def _run_step(name, fn, cfg, results):
    banner(f"==> {name}")
    try:
        res = fn(cfg)
    except Exception as e:  # noqa: BLE001
        log.error("✗ %s 失败: %s", name, e)
        raise
    results.append(res)
    log.info("✓ %s 完成", name)
    return res


def run_pipeline(cfg) -> dict:
    results = []

    # Step0 采集
    if cfg["crawl"].get("enabled", True) and not cfg["crawl"].get("skip", False):
        _run_step("Step0 采集", lambda c: crawler.run(c), cfg, results)
    else:
        log.info("跳过 Step0 采集（crawl.enabled=False 或数据已存在）。")

    # Step1-5 核心分析
    _run_step("Step1 清洗", step1_clean.run, cfg, results)
    _run_step("Step2 时间演化", step2_timeline.run, cfg, results)
    _run_step("Step3 主题分析", step3_topic.run, cfg, results)

    if cfg["sentiment"].get("enabled", True):
        _run_step("Step4 情感与立场", step4_sentiment.run, cfg, results)
    else:
        log.info("跳过 Step4（sentiment.enabled=False）。")

    if cfg["network"].get("enabled", True):
        _run_step("Step5 社会网络", step5_network.run, cfg, results)
    else:
        log.info("跳过 Step5（network.enabled=False）。")

    # Step6-8 BERT（可选）
    if cfg["bert"].get("enabled", False):
        _run_step("Step6 BERT 向量化", step6_bert_embed.run, cfg, results)
        _run_step("Step7 BERT 主题", step7_bert_topic.run, cfg, results)
        _run_step("Step8 BERT 情感", step8_bert_sentiment.run, cfg, results)

    # Step9 报告
    report_path = None
    if cfg["report"].get("html", True):
        report_path = report_mod.build_report(cfg, results)
    if cfg["report"].get("docx", False):
        report_mod.build_docx(cfg, results)

    banner("全部完成")
    log.info("输出目录: %s", cfg.out_root)
    if report_path:
        log.info("报告: %s", report_path)
    return {"results": results, "report": report_path}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    config_path = "config.yaml"
    if argv:
        for a in argv:
            if a.endswith(".yaml") or a.endswith(".yml"):
                config_path = a
    if not Path(config_path).exists():
        log.error("未找到配置文件: %s", config_path)
        log.error("请复制 configs/example.yaml 为 config.yaml 并填写 project.topic 与 Cookie。")
        return 2

    cfg = load_config(config_path)
    dump_effective_config(cfg)
    run_pipeline(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
