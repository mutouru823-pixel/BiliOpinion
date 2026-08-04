# -*- coding: utf-8 -*-
"""单步执行器。

两种调用方式：
1. 作为子进程 CLI（被 app.py 通过 subprocess 启动）：
   python -m app.runner <step_key> <config.yaml> [--cookie <cookie>]

2. 直接被前端 import 调用 run_step_in_background() 启动子进程。

runner 本身负责：
- 加载 config（与 biliopinion.config.load_config 等价）
- 注入 cookie（从命令行参数或环境变量）
- 调用对应 step 的 run(cfg)
- 在 .state/<step>.json 写 status / started_at / finished_at / error
- stdout+stderr 全量写入 .state/<step>.log
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

# 让 REPO_ROOT 在 sys.path 中（直接 python -m 时 cwd 可能不是仓库根）
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from biliopinion.config import load_config  # noqa: E402

from app import state  # noqa: E402


# ----------------------------------------------------------------------
# step_key -> 可调用对象
# ----------------------------------------------------------------------
def _resolve_step(step_key: str):
    """返回该 step 的 run(cfg) -> dict 函数。"""
    if step_key == "step0_crawl":
        from biliopinion import crawler
        return crawler.run
    if step_key == "step9_report":
        from biliopinion import report as report_mod
        # report.build_report 需要 (cfg, results)，results 我们从 .state 收集
        def _wrap(cfg):
            results = _collect_results(cfg)
            return {"path": report_mod.build_report(cfg, results)}
        return _wrap

    # step_key -> biliopinion.steps.<module>.run
    # 注意：step8 的 key 是 step8_bert_senti（简写），但模块名是 step8_bert_sentiment（全称）
    module_map = {
        "step1_clean":      "biliopinion.steps.step1_clean",
        "step2_timeline":   "biliopinion.steps.step2_timeline",
        "step3_topic":      "biliopinion.steps.step3_topic",
        "step4_sentiment":  "biliopinion.steps.step4_sentiment",
        "step5_network":    "biliopinion.steps.step5_network",
        "step6_bert_embed": "biliopinion.steps.step6_bert_embed",
        "step7_bert_topic": "biliopinion.steps.step7_bert_topic",
        "step8_bert_senti": "biliopinion.steps.step8_bert_sentiment",
    }
    mod_path = module_map.get(step_key)
    if mod_path is None:
        raise ValueError(f"未知 step_key: {step_key}")
    mod = __import__(mod_path, fromlist=["run"])
    return mod.run


def _collect_results(cfg) -> list[dict]:
    """Step9 报告需要前面各 step 的 figures 列表。

    我们的 step 函数返回 {figures, stats, data_files}。这里我们没有把
    之前的返回值持久化（只有数据落盘），所以重新从 figures/ 目录扫描图片，
    把它们做成 figures 列表传给 build_report。
    """
    fig_dir = cfg.dir_fig
    figs = []
    if fig_dir.exists():
        for p in sorted(fig_dir.glob("*.png")):
            title = p.stem
            figs.append((str(p), title, ""))
    return [{"figures": figs, "stats": {}, "data_files": []}]


# ----------------------------------------------------------------------
# CLI 入口（被 subprocess 调用）
# ----------------------------------------------------------------------
def main_cli() -> int:
    if len(sys.argv) < 3:
        print("用法: python -m app.runner <step_key> <config.yaml> [--cookie <cookie>]",
              file=sys.stderr)
        return 2
    step_key = sys.argv[1]
    config_file = sys.argv[2]
    cookie = ""
    if "--cookie" in sys.argv:
        i = sys.argv.index("--cookie")
        if i + 1 < len(sys.argv):
            cookie = sys.argv[i + 1]

    # 注入 cookie 到环境变量，load_config 会读取
    if cookie:
        os.environ["BILI_COOKIE"] = cookie

    # 找到项目名（从 config 文件路径推断）
    # config 文件位于 outputs/<name>/.state/config.yaml
    cfg_path = Path(config_file).resolve()
    project_name = cfg_path.parent.parent.name

    log_file = state._step_log_file(project_name, step_key)
    state_file = state._step_state_file(project_name, step_key)

    # 重置日志
    log_file.write_text("", encoding="utf-8")

    # 写 running 状态
    started_at = time.time()
    state.write_step_state(project_name, step_key, {
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "error": None,
        "pid": os.getpid(),
    })

    # 把 stdout/stderr 重定向到日志文件
    tee = _Tee(log_file)
    sys.stdout = tee
    sys.stderr = tee

    def _fail(msg: str) -> int:
        print(f"[runner] FAILED: {msg}", file=sys.stderr)
        state.write_step_state(project_name, step_key, {
            "status": "error",
            "started_at": started_at,
            "finished_at": time.time(),
            "error": msg[:500],
            "pid": os.getpid(),
        })
        return 1

    print(f"[runner] step={step_key} project={project_name} pid={os.getpid()}")
    print(f"[runner] config={cfg_path}")

    # 顶层 try：保证任何异常都标记为 error，不卡在 running
    try:
        cfg = load_config(str(cfg_path))
    except Exception as e:
        return _fail(f"配置加载失败: {e}\n{traceback.format_exc()}")

    # 跳过逻辑：step0_crawl 在 crawl.enabled=False 时也要标记完成
    # （main.run_pipeline 的逻辑：crawl.enabled=True 且不 skip 才跑）
    if step_key == "step0_crawl":
        if not cfg["crawl"].get("enabled", True):
            print("[runner] crawl.enabled=False，跳过采集，标记完成")
            state.write_step_state(project_name, step_key, {
                "status": "done", "started_at": started_at,
                "finished_at": time.time(), "error": None,
                "pid": os.getpid(), "skipped": True,
            })
            return 0

    try:
        fn = _resolve_step(step_key)
        ret = fn(cfg)
        # 把返回值中的 figures 落盘，供 step9 重用
        result_file = state.state_dir(project_name) / f"{step_key}.result.json"
        try:
            import json
            # figures 是 list of (path, title, caption) tuple，转 list of list
            serializable = {}
            if isinstance(ret, dict):
                if "figures" in ret:
                    serializable["figures"] = [list(f) for f in ret["figures"]]
                if "stats" in ret:
                    serializable["stats"] = ret["stats"]
                if "data_files" in ret:
                    serializable["data_files"] = ret["data_files"]
                if "path" in ret:
                    serializable["path"] = ret["path"]
            result_file.write_text(
                json.dumps(serializable, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            print(f"[runner] 写 result.json 失败（可忽略）: {e}")
        state.write_step_state(project_name, step_key, {
            "status": "done",
            "started_at": started_at,
            "finished_at": time.time(),
            "error": None,
            "pid": os.getpid(),
        })
        print(f"[runner] {step_key} 完成")
        return 0
    except Exception as e:
        return _fail(f"{step_key} 执行失败: {e}\n{traceback.format_exc()}")


class _Tee:
    """同时写文件和原 stdout/stderr 的简易 tee。"""

    def __init__(self, log_path: Path):
        self._f = open(log_path, "a", encoding="utf-8", buffering=1)
        self._stdout = sys.__stdout__
        self._stderr = sys.__stderr__

    def write(self, data):
        try:
            self._f.write(data)
        except Exception:
            pass
        # 不回显到原 stdout（子进程通常不需要 stdout），但保留以防调试
        try:
            self._stdout.write(data)
        except Exception:
            pass

    def flush(self):
        try:
            self._f.flush()
        except Exception:
            pass
        try:
            self._stdout.flush()
        except Exception:
            pass

    def isatty(self):
        return False

    def fileno(self):
        return self._f.fileno()


# ----------------------------------------------------------------------
# 后台启动接口（被 app.py 调用）
# ----------------------------------------------------------------------
def run_step_in_background(project_name: str, step_key: str, cookie: str = "") -> int:
    """启动一个子进程跑指定 step。立即返回 pid。"""
    import subprocess

    cfg_file = state.config_path(project_name)
    if not cfg_file.exists():
        raise FileNotFoundError(f"项目 config 不存在: {cfg_file}。请先在「配置」Tab 保存。")

    cmd = [sys.executable, "-m", "app.runner", step_key, str(cfg_file)]
    if cookie:
        cmd += ["--cookie", cookie]

    # 启动为独立进程（detached），stdout/stderr 由 runner 内部 tee 到日志文件
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    return proc.pid


def is_step_process_alive(project_name: str, step_key: str) -> bool:
    """检查 step 进程是否还在跑（best-effort）。"""
    st = state.read_step_state(project_name, step_key)
    if st.get("status") != "running":
        return False
    pid = st.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, 0)  # 0 = 探活，不发信号
        return True
    except (OSError, ProcessLookupError):
        return False
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main_cli())
