# -*- coding: utf-8 -*-
"""Streamlit 前端自检（无需浏览器 / 无需启动服务）。

用 Streamlit 官方的 AppTest 无头渲染整个 UI，捕获运行时异常与弃用警告，
并顺带验证「新建项目 → 保存配置 → 后台执行器 → 僵尸状态对账」这条链路。

用法：
    python tools/test_app.py
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PROBE = "_apptest_probe"
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        PASS.append(name)
        print(f"  [OK]   {name}")
    else:
        FAIL.append(f"{name} — {detail}")
        print(f"  [FAIL] {name} — {detail}")


def main() -> int:
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError:
        print("需要 streamlit>=1.49：pip install -r requirements.txt", file=sys.stderr)
        return 1

    from app import config_ui, state, runner

    print("\n[1/5] 首屏渲染")
    at = AppTest.from_file(str(REPO_ROOT / "app" / "home.py"), default_timeout=120)
    at.run()
    check("首屏无异常", len(at.exception) == 0,
          "; ".join(repr(e.value)[:200] for e in at.exception))
    check("首屏无警告", len(at.warning) == 0,
          "; ".join(w.value[:160] for w in at.warning))
    check("侧边栏项目选择器存在", len(at.sidebar.selectbox) > 0)

    print("\n[2/5] 新建项目 + 保存配置")
    cfg = config_ui.default_config()
    cfg["project"]["name"] = PROBE
    cfg["project"]["topic"] = "自检主题"
    cfg["crawl"]["enabled"] = False
    cfg_file = config_ui.save_config(cfg, PROBE)
    check("config.yaml 已落盘", cfg_file.exists(), str(cfg_file))
    check("项目出现在列表中", PROBE in state.list_projects())

    print("\n[3/5] 选中项目后四个 Tab 渲染")
    at2 = AppTest.from_file(str(REPO_ROOT / "app" / "home.py"), default_timeout=120)
    at2.run()
    opts = at2.sidebar.selectbox[0].options
    if PROBE in opts:
        at2.sidebar.selectbox[0].select(PROBE).run()
    check("选中项目后无异常", len(at2.exception) == 0,
          "; ".join(repr(e.value)[:300] for e in at2.exception))
    check("选中项目后无警告", len(at2.warning) == 0,
          "; ".join(w.value[:160] for w in at2.warning))
    labels = [t.label for t in at2.tabs]
    check("四个 Tab 齐全", labels == ["配置", "运行", "报告", "项目"], str(labels))
    check("运行 Tab 有 step 按钮", any(b.label == "运行" for b in at2.button))

    print("\n[4/5] 后台执行器（step0 在 crawl.enabled=False 时应直接完成）")
    runner.run_step_in_background(PROBE, "step0_crawl")
    ok = False
    for _ in range(20):
        time.sleep(1)
        if state.read_step_state(PROBE, "step0_crawl").get("status") == "done":
            ok = True
            break
    check("step0 后台执行完成", ok,
          str(state.read_step_state(PROBE, "step0_crawl")))
    check("依赖解锁：step1 可运行", state.can_run(PROBE, "step1_clean"))

    print("\n[5/5] 僵尸状态对账（进程没了不该永远卡 running）")
    # 用无依赖的 step0 验证：把它伪造成「进程早已消失但状态还写着 running」
    state.write_step_state(PROBE, "step0_crawl", {
        "status": "running", "started_at": time.time() - 999,
        "finished_at": None, "error": None, "pid": 999_999,
    })
    reconciled = state.read_step_state(PROBE, "step0_crawl")
    check("僵尸 running 自动改判为 error",
          reconciled.get("status") == "error", str(reconciled))
    check("改判后已落盘（不是只改内存）",
          state.read_step_state(PROBE, "step0_crawl").get("stale") is True)
    check("对账后按钮可重新触发", state.can_run(PROBE, "step0_crawl"))
    check("宽限期内不误判刚启动的进程", _grace_ok(state))
    check("存活进程不会被误判", runner.pid_alive(__import__("os").getpid()))
    check("不存在的 pid 判定为已退出", not runner.pid_alive(999_999))

    # 清理探针项目
    shutil.rmtree(state.project_root(PROBE), ignore_errors=True)
    if state.project_root(PROBE).exists():
        print(f"  (提示：探针目录未能自动删除，可手动清理 {state.project_root(PROBE)})")


def _grace_ok(state) -> bool:
    """刚启动 1 秒的 step 即使 pid 不存在，也应保持 running 而非立刻判死。"""
    state.write_step_state(PROBE, "step1_clean", {
        "status": "running", "started_at": time.time(),
        "finished_at": None, "error": None, "pid": 999_999,
    })
    return state.read_step_state(PROBE, "step1_clean").get("status") == "running"

    print("\n" + "=" * 56)
    print(f"通过 {len(PASS)}/{len(PASS) + len(FAIL)}")
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
