# -*- coding: utf-8 -*-
"""状态管理：session_state + 状态文件（落盘，跨刷新/跨进程保持）。

状态文件位于 outputs/<name>/.state/：
  - <step>.json  : {status, started_at, finished_at, error, pid}
  - <step>.log   : 该 step 的 stdout+stderr 尾部日志
  - _last.json   : 最近一次活跃的 step 名（用于 UI 焦点）
status 取值: pending | running | done | error
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import streamlit as st

# 9 个 step 元数据（顺序即依赖顺序）
STEPS: list[dict[str, str]] = [
    {"key": "step0_crawl",     "name": "Step0 采集",         "desc": "B 站视频搜索 + 一/二级评论抓取"},
    {"key": "step1_clean",      "name": "Step1 清洗",         "desc": "字段统一、时间标准化、文本清洗、去重"},
    {"key": "step2_timeline",   "name": "Step2 时间演化",     "desc": "每日评论量、阶段断点、词云、热力图"},
    {"key": "step3_topic",      "name": "Step3 主题分析",     "desc": "TF-IDF+SVD+KMeans 无监督主题"},
    {"key": "step4_sentiment", "name": "Step4 情感与立场",   "desc": "SnowNLP 三分类 + 可选立场分析"},
    {"key": "step5_network",    "name": "Step5 社会网络",     "desc": "Louvain 社群、词共现、Gephi 导出"},
    {"key": "step6_bert_embed", "name": "Step6 BERT 向量化",  "desc": "可选：BERT 句向量（需 torch）"},
    {"key": "step7_bert_topic", "name": "Step7 BERT 主题",    "desc": "可选：c-TF-IDF 主题"},
    {"key": "step8_bert_senti", "name": "Step8 BERT 情感",    "desc": "可选：弱监督情感"},
    {"key": "step9_report",     "name": "Step9 报告",         "desc": "自包含 HTML 报告（+可选 docx）"},
]

# step 依赖：key -> 必须先完成的 step keys
DEPENDS: dict[str, list[str]] = {
    "step0_crawl":     [],
    "step1_clean":     ["step0_crawl"],
    "step2_timeline":   ["step1_clean"],
    "step3_topic":      ["step1_clean"],
    "step4_sentiment":  ["step1_clean"],
    "step5_network":    ["step1_clean"],
    "step6_bert_embed": ["step1_clean"],
    "step7_bert_topic": ["step6_bert_embed"],
    "step8_bert_senti": ["step6_bert_embed"],
    "step9_report":     ["step2_timeline", "step3_topic"],
}


# ----------------------------------------------------------------------
# 当前项目
# ----------------------------------------------------------------------
def get_current_project() -> str:
    return st.session_state.get("current_project", "")


def set_current_project(name: str) -> None:
    st.session_state["current_project"] = name


def project_root(name: str) -> Path:
    """项目输出根目录 outputs/<name>。"""
    from app.paths import writable_base
    return (writable_base() / "outputs" / name).resolve()


def state_dir(name: str) -> Path:
    d = project_root(name) / ".state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path(name: str) -> Path:
    """项目专属 config.yaml 路径。"""
    return state_dir(name) / "config.yaml"


# ----------------------------------------------------------------------
# Step 状态文件读写
# ----------------------------------------------------------------------
def _step_state_file(name: str, step_key: str) -> Path:
    return state_dir(name) / f"{step_key}.json"


def _step_log_file(name: str, step_key: str) -> Path:
    return state_dir(name) / f"{step_key}.log"


def read_step_state(name: str, step_key: str) -> dict[str, Any]:
    f = _step_state_file(name, step_key)
    if not f.exists():
        return {"status": "pending", "started_at": None, "finished_at": None,
                "error": None, "pid": None}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "pending", "started_at": None, "finished_at": None,
                "error": None, "pid": None}


def write_step_state(name: str, step_key: str, data: dict[str, Any]) -> None:
    f = _step_state_file(name, step_key)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_step_log(name: str, step_key: str, tail: int = 50) -> str:
    f = _step_log_file(name, step_key)
    if not f.exists():
        return ""
    try:
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        return "\n".join(lines[-tail:]) if lines else ""
    except Exception:
        return ""


def all_step_states(name: str) -> dict[str, dict[str, Any]]:
    return {s["key"]: read_step_state(name, s["key"]) for s in STEPS}


def is_step_done(name: str, step_key: str) -> bool:
    return read_step_state(name, step_key).get("status") == "done"


def can_run(name: str, step_key: str) -> bool:
    """依赖是否就绪。允许 step 依赖项任意一个完成即可（与 run_pipeline 行为一致）。"""
    deps = DEPENDS.get(step_key, [])
    if not deps:
        return True
    return any(is_step_done(name, d) for d in deps)


# ----------------------------------------------------------------------
# 项目列表
# ----------------------------------------------------------------------
def list_projects() -> list[str]:
    """扫描 outputs/ 下所有项目目录。"""
    from app.paths import writable_base
    out_dir = (writable_base() / "outputs").resolve()
    if not out_dir.exists():
        return []
    names = []
    for p in sorted(out_dir.iterdir()):
        if p.is_dir() and not p.name.startswith("."):
            names.append(p.name)
    return names


def project_summary(name: str) -> dict[str, Any]:
    """轻量项目摘要：评论数、step 完成情况、是否有报告。"""
    root = project_root(name)
    states = all_step_states(name)
    done = [k for k, v in states.items() if v.get("status") == "done"]
    running = [k for k, v in states.items() if v.get("status") == "running"]
    raw_comments = 0
    valid_comments = 0
    rc = root / "raw" / "comments.csv"
    if rc.exists():
        try:
            import pandas as pd
            raw_comments = sum(1 for _ in open(rc, encoding="utf-8-sig", errors="ignore")) - 1
            raw_comments = max(0, raw_comments)
        except Exception:
            pass
    vc = root / "data" / "comments_valid.csv"
    if vc.exists():
        try:
            import pandas as pd
            valid_comments = len(pd.read_csv(vc, usecols=[0]))
        except Exception:
            pass
    return {
        "name": name,
        "exists": root.exists(),
        "done_steps": done,
        "running_steps": running,
        "n_done": len(done),
        "n_total": len(STEPS),
        "has_report": (root / "report.html").exists(),
        "raw_comments": raw_comments,
        "valid_comments": valid_comments,
        "topic": _read_topic(name),
    }


def _read_topic(name: str) -> str:
    eff = project_root(name) / "effective_config.yaml"
    if not eff.exists():
        return ""
    try:
        import yaml
        cfg = yaml.safe_load(eff.read_text(encoding="utf-8")) or {}
        return cfg.get("project", {}).get("topic", "")
    except Exception:
        return ""


def delete_project(name: str) -> None:
    import shutil
    root = project_root(name)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


# ----------------------------------------------------------------------
# 时间格式化
# ----------------------------------------------------------------------
def fmt_time(ts: Any) -> str:
    if not ts:
        return ""
    try:
        if isinstance(ts, (int, float)):
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        return str(ts)
    except Exception:
        return str(ts)
