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
    """Step9 报告需要前面各 step 的返回值 {figures, stats, data_files}。

    每个 step 跑完时 runner 已把返回值写到 .state/<step>.result.json，
    这里按 STEPS 顺序读回来，保留原始图注与统计指标。
    只有当 result.json 全部缺失（例如是旧版本产物）时，
    才退化为扫描 figures/ 目录。
    """
    import json as _json

    project_name = Path(cfg["_paths"]["out_root"]).name
    sdir = state.state_dir(project_name)

    results: list[dict] = []
    seen_figs: set[str] = set()
    for step in state.STEPS:
        if step["key"] == "step9_report":
            continue
        rf = sdir / f"{step['key']}.result.json"
        if not rf.exists():
            continue
        try:
            payload = _json.loads(rf.read_text(encoding="utf-8"))
        except Exception:
            continue
        figs = []
        for item in payload.get("figures") or []:
            if not item:
                continue
            path = str(item[0])
            if path in seen_figs or not Path(path).exists():
                continue
            seen_figs.add(path)
            title = str(item[1]) if len(item) > 1 else Path(path).stem
            caption = str(item[2]) if len(item) > 2 else ""
            figs.append((path, title, caption))
        results.append({
            "figures": figs,
            "stats": payload.get("stats") or {},
            "data_files": payload.get("data_files") or [],
        })

    if results:
        return results

    # 回退：没有任何 result.json（旧产物），扫描 figures/ 目录
    fig_dir = cfg.dir_fig
    figs = []
    if fig_dir.exists():
        for p in sorted(fig_dir.glob("*.png")):
            figs.append((str(p), p.stem, ""))
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
    """启动一个子进程跑指定 step。立即返回 pid。

    子进程与 Streamlit 主进程解耦：关掉页面、甚至重启 Streamlit，
    正在跑的采集/分析都不会被带走。
    """
    import subprocess

    cfg_file = state.config_path(project_name)
    if not cfg_file.exists():
        raise FileNotFoundError(f"项目 config 不存在: {cfg_file}。请先在「配置」Tab 保存。")

    cmd = [sys.executable, "-m", "app.runner", step_key, str(cfg_file)]
    if cookie:
        cmd += ["--cookie", cookie]

    kwargs: dict = {
        "cwd": str(REPO_ROOT),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        # start_new_session 在 Windows 上是空操作，必须用 creationflags
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        )
    else:
        kwargs["start_new_session"] = True

    # 先占位写入 running，避免"点了按钮但状态还没变"的空窗期
    proc = subprocess.Popen(cmd, **kwargs)
    state.write_step_state(project_name, step_key, {
        "status": "running",
        "started_at": time.time(),
        "finished_at": None,
        "error": None,
        "pid": proc.pid,
    })
    return proc.pid


# ----------------------------------------------------------------------
# 进程探活（跨平台）
# ----------------------------------------------------------------------
def pid_alive(pid: int) -> bool:
    """判断 pid 是否仍然存活。Windows 走 Win32 API，POSIX 走 signal 0。"""
    if not pid or pid <= 0:
        return False
    try:
        import psutil  # 有就用，最可靠
        return psutil.pid_exists(int(pid))
    except ImportError:
        pass

    if os.name == "nt":
        # 不用 os.kill：Windows 上非 CTRL_* 信号会走 TerminateProcess，
        # 探活反而可能把进程杀掉。改用 OpenProcess + GetExitCodeProcess。
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)

    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def is_step_process_alive(project_name: str, step_key: str) -> bool:
    """检查 step 进程是否还在跑（best-effort）。"""
    st = state.read_step_state(project_name, step_key)
    if st.get("status") != "running":
        return False
    return pid_alive(st.get("pid"))


def stop_step(project_name: str, step_key: str) -> bool:
    """终止正在运行的 step 进程，并把状态标记为 error。"""
    st = state.read_step_state(project_name, step_key)
    pid = st.get("pid")
    killed = False
    if pid and pid_alive(pid):
        try:
            import signal
            os.kill(int(pid), signal.SIGTERM if os.name != "nt" else signal.SIGTERM)
            killed = True
        except Exception:
            try:
                import subprocess
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                               capture_output=True, check=False)
                killed = True
            except Exception:
                killed = False
    state.write_step_state(project_name, step_key, {
        "status": "error",
        "started_at": st.get("started_at"),
        "finished_at": time.time(),
        "error": "已被用户手动停止",
        "pid": pid,
    })
    return killed


if __name__ == "__main__":
    raise SystemExit(main_cli())
