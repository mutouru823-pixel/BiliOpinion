# -*- coding: utf-8 -*-
"""BiliOpinion Streamlit 前端主入口。

启动：
    streamlit run app/app.py
    或：python run_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# 让 REPO_ROOT 在 sys.path（streamlit run 时 cwd 可能不对）
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app import state, config_ui, viewer  # noqa: E402
from biliopinion.config import REPO_ROOT as _repo  # noqa: E402


# ----------------------------------------------------------------------
# 页面配置
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="BiliOpinion · B 站舆情分析",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ----------------------------------------------------------------------
# 侧边栏：项目选择 + Cookie + 全局
# ----------------------------------------------------------------------
def sidebar() -> None:
    with st.sidebar:
        st.markdown("## 📊 BiliOpinion")
        st.caption("B 站评论舆情演化分析管线 · 前端控制台")

        # 项目选择
        st.markdown("### 项目")
        existing = state.list_projects()

        col1, col2 = st.columns([3, 1])
        with col1:
            options = ["➕ 新建项目…"] + existing
            idx = 0
            cur = state.get_current_project()
            if cur and cur in existing:
                idx = options.index(cur)
            choice = st.selectbox("选择项目", options=options, index=idx,
                                    label_visibility="collapsed")
        with col2:
            if st.button("🔄", help="刷新列表"):
                st.rerun()

        if choice == "➕ 新建项目…":
            new_name = st.text_input("项目名 (英文/拼音)", key="new_project_name",
                                       placeholder="my_event")
            if new_name and st.button("创建", use_container_width=True):
                # 创建空目录 + 默认 config
                from app.config_ui import default_config, save_config
                cfg = default_config()
                cfg["project"]["name"] = new_name
                cfg["project"]["topic"] = new_name
                save_config(cfg, new_name)
                state.set_current_project(new_name)
                st.rerun()
            return
        else:
            state.set_current_project(choice)

        st.markdown("---")
        # 项目摘要
        cur = state.get_current_project()
        if cur:
            summ = state.project_summary(cur)
            st.markdown(f"**当前项目**: `{cur}`")
            st.markdown(f"**主题**: {summ['topic'] or '(未设置)'}")
            st.markdown(f"**进度**: {summ['n_done']} / {summ['n_total']} step")
            if summ["raw_comments"]:
                st.markdown(f"**原始评论**: {summ['raw_comments']:,}")
            if summ["valid_comments"]:
                st.markdown(f"**有效评论**: {summ['valid_comments']:,}")
            if summ["running_steps"]:
                st.warning(f"运行中: {', '.join(summ['running_steps'])}")

        st.markdown("---")
        st.markdown("### 🔑 B 站 Cookie")
        st.caption("用于 Step0 采集。留空则用 .env 中的 BILI_COOKIE。")
        cookie = st.text_input(
            "Cookie", type="password",
            value=st.session_state.get("cookie_input", ""),
            key="cookie_input",
            label_visibility="collapsed")
        st.session_state["bili_cookie"] = cookie

        if st.button("💾 记住到 .env", help="写入仓库根 .env"):
            _save_dotenv(cookie)

        st.markdown("---")
        st.caption(f"仓库根: `{_repo}`")


def _save_dotenv(cookie: str) -> None:
    env_file = _repo / ".env"
    lines = []
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if not line.startswith("BILI_COOKIE="):
                lines.append(line)
    if cookie:
        lines.append(f"BILI_COOKIE={cookie}")
    env_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    st.success(f"已写入 {env_file}")


# ----------------------------------------------------------------------
# 主页面
# ----------------------------------------------------------------------
def main() -> None:
    sidebar()

    cur = state.get_current_project()
    if not cur:
        st.markdown("## 👋 欢迎使用 BiliOpinion")
        st.markdown("""
请在左侧 **新建一个项目** 或选择已有项目开始。

本前端将 9 步管线（采集 → 清洗 → 时间演化 → 主题 → 情感 → 网络 → BERT → 报告）
拆分为可单独触发、按依赖解锁的卡片，让你逐步推进、随时查看产出。
        """)
        return

    tab_cfg, tab_run, tab_report, tab_proj = st.tabs(
        ["📋 配置", "🚀 运行", "📊 报告", "📁 项目"])

    with tab_cfg:
        _tab_config(cur)
    with tab_run:
        _tab_run(cur)
    with tab_report:
        _tab_report(cur)
    with tab_proj:
        _tab_projects()


# ----------------------------------------------------------------------
# 配置 Tab
# ----------------------------------------------------------------------
def _tab_config(project_name: str) -> None:
    st.header("📋 配置")

    # 加载已有 config
    cfg_file = state.config_path(project_name)
    cfg = config_ui.load_config_file(cfg_file)
    # 从 effective_config.yaml 同步主题等已实际生效的字段
    eff = state.project_root(project_name) / "effective_config.yaml"
    if eff.exists():
        try:
            import yaml
            eff_cfg = yaml.safe_load(eff.read_text(encoding="utf-8")) or {}
            # 用 effective 覆盖默认 + 用户未填的字段
            cfg = config_ui._deep_merge(cfg, eff_cfg)
        except Exception:
            pass

    col_a, col_b = st.columns([1, 4])
    with col_a:
        mode = st.radio("编辑模式", ["表单", "YAML 原文"], label_visibility="collapsed")
    with col_b:
        if mode == "YAML 原文":
            text = st.text_area(
                "config.yaml",
                value=config_ui.dict_to_yaml(cfg),
                height=600,
                label_visibility="collapsed")
            try:
                cfg = config_ui.yaml_to_dict(text)
            except Exception as e:
                st.error(f"YAML 解析失败: {e}")
        else:
            cfg = config_ui.render_config_form(cfg, cookie=st.session_state.get("bili_cookie", ""))

    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        if st.button("💾 保存", type="primary", use_container_width=True):
            try:
                # 校验：通过 load_config 走一遍
                from biliopinion.config import load_config
                import tempfile, yaml
                # 先写到临时文件做校验
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".yaml", delete=False, mode="w", encoding="utf-8")
                yaml.safe_dump(cfg, tmp, allow_unicode=True, sort_keys=False)
                tmp.close()
                load_config(tmp.name)
                config_ui.save_config(cfg, project_name)
                st.success("配置已保存 ✅")
            except Exception as e:
                st.error(f"配置校验失败: {e}")
    with col2:
        # 下载 yaml
        st.download_button(
            "⬇️ 下载 yaml",
            data=config_ui.dict_to_yaml(cfg).encode("utf-8"),
            file_name=f"{project_name}_config.yaml",
            mime="application/x-yaml",
            use_container_width=True,
        )


# ----------------------------------------------------------------------
# 运行 Tab
# ----------------------------------------------------------------------
def _tab_run(project_name: str) -> None:
    st.header("🚀 运行管线")
    st.caption("9 步按依赖顺序解锁。每步独立运行，产出落盘后即可解锁下一步。")

    # 校验 config 是否存在
    if not state.config_path(project_name).exists():
        st.warning("尚未保存配置。请先到「配置」Tab 保存。")
        return

    # 顶部进度条
    states = state.all_step_states(project_name)
    done = sum(1 for s in states.values() if s.get("status") == "done")
    running = sum(1 for s in states.values() if s.get("status") == "running")
    err = sum(1 for s in states.values() if s.get("status") == "error")
    total = len(states)
    p_done = done / total if total else 0
    p_run = running / total if total else 0
    st.progress(p_done + p_run, text=f"完成 {done}/{total} · 运行中 {running} · 失败 {err}")

    # 顶部操作：「运行所有未完成」
    cookie = st.session_state.get("bili_cookie", "")
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button("▶ 运行到下一步", help="依次跑完所有 pending 的 step"):
            _run_next_pending(project_name, cookie)
    with col2:
        if st.button("🔄 刷新", help="重新读取所有 step 状态"):
            st.rerun()

    # 各 step 卡片
    for step in state.STEPS:
        viewer.render_step_card(project_name, step, cookie=cookie)
        st.markdown("")


def _run_next_pending(project_name: str, cookie: str) -> None:
    """找到第一个未完成且依赖已就绪的 step，运行它。"""
    from app import runner
    for step in state.STEPS:
        key = step["key"]
        st_state = state.read_step_state(project_name, key)
        status = st_state.get("status", "pending")
        if status in ("pending", "error"):
            if state.can_run(project_name, key):
                try:
                    pid = runner.run_step_in_background(project_name, key, cookie=cookie)
                    st.success(f"已启动 {step['name']} (pid={pid})")
                    return
                except Exception as e:
                    st.error(f"启动 {step['name']} 失败: {e}")
                    return
    st.info("所有 step 都已运行过或正在运行。")


# ----------------------------------------------------------------------
# 报告 Tab
# ----------------------------------------------------------------------
def _tab_report(project_name: str) -> None:
    st.header("📊 报告与产出")
    viewer.render_report_tab(project_name)


# ----------------------------------------------------------------------
# 项目 Tab
# ----------------------------------------------------------------------
def _tab_projects() -> None:
    st.header("📁 项目管理")
    projects = state.list_projects()
    if not projects:
        st.info("暂无项目。请在左侧新建。")
        return

    rows = []
    for name in projects:
        s = state.project_summary(name)
        rows.append({
            "项目": name,
            "主题": s["topic"],
            "进度": f"{s['n_done']}/{s['n_total']}",
            "原始评论": s["raw_comments"],
            "有效评论": s["valid_comments"],
            "报告": "✅" if s["has_report"] else "—",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    st.markdown("---")
    selected = st.selectbox("选择项目操作", options=projects)
    if selected:
        col1, col2, col3 = st.columns([1, 1, 3])
        with col1:
            if st.button("切换到该项目"):
                state.set_current_project(selected)
                st.rerun()
        with col2:
            if st.button("🗑️ 删除", type="secondary"):
                if st.session_state.get(f"confirm_delete_{selected}", False):
                    state.delete_project(selected)
                    st.success(f"已删除 {selected}")
                    st.rerun()
                else:
                    st.session_state[f"confirm_delete_{selected}"] = True
                    st.warning("再点一次确认删除（不可恢复）")


# streamlit run 会以 __main__ 加载本文件；每次交互 rerun 整个脚本，
# 所以 main() 直接在模块级调用即可。
main()
