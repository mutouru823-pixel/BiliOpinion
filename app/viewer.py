# -*- coding: utf-8 -*-
"""报告 / 图表 / 数据查看器。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from app import state


# ----------------------------------------------------------------------
# 报告查看
# ----------------------------------------------------------------------
def render_report_tab(project_name: str) -> None:
    """渲染项目报告 Tab。"""
    root = state.project_root(project_name)
    report_path = root / "report.html"

    if not report_path.exists():
        st.info("尚未生成报告。请先在「运行」Tab 完成必要的 step（至少到 Step9 报告）。")
        _render_figures_only(project_name)
        return

    # 提供「在新标签打开」与「内嵌预览」两种方式
    col1, col2 = st.columns([1, 4])
    with col1:
        st.download_button(
            "⬇️ 下载 report.html",
            data=report_path.read_bytes(),
            file_name="report.html",
            mime="text/html",
        )
    with col2:
        if st.checkbox("内嵌预览（性能较重）", value=False):
            try:
                import streamlit.components.v1 as components
                # 文件可能较大，截断到 5MB 防 streamlit 卡死
                content = report_path.read_text(encoding="utf-8")
                if len(content) > 5_000_000:
                    st.warning(f"报告较大 ({len(content)/1024/1024:.1f} MB)，"
                                f"建议下载后用浏览器打开。")
                components.html(content, height=900, scrolling=True)
            except Exception as e:
                st.error(f"内嵌预览失败: {e}")

    st.markdown("---")
    _render_figures_only(project_name)
    _render_data_files(project_name)


def _render_figures_only(project_name: str) -> None:
    """渲染 figures/ 下所有 PNG 图表。"""
    root = state.project_root(project_name)
    fig_dir = root / "figures"
    if not fig_dir.exists():
        return
    figs = sorted(fig_dir.glob("*.png"))
    if not figs:
        return
    st.subheader(f"🖼️ 图表 ({len(figs)})")
    cols_per_row = 2
    for i in range(0, len(figs), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, p in enumerate(figs[i:i + cols_per_row]):
            with cols[j]:
                st.image(str(p), caption=p.name, use_container_width=True)


def _render_data_files(project_name: str) -> None:
    """渲染 data/ 下的 CSV / JSON 文件。"""
    root = state.project_root(project_name)
    data_dir = root / "data"
    if not data_dir.exists():
        return
    files = sorted(list(data_dir.glob("*.csv")) + list(data_dir.glob("*.json")))
    if not files:
        return
    st.subheader(f"📋 数据文件 ({len(files)})")
    names = [p.name for p in files]
    selected = st.selectbox("选择文件", options=names, index=0)
    if not selected:
        return
    fp = data_dir / selected
    try:
        if fp.suffix == ".csv":
            df = pd.read_csv(fp)
            st.dataframe(df, use_container_width=True, height=400)
            st.download_button("下载 CSV", data=fp.read_bytes(),
                                file_name=fp.name, mime="text/csv")
        elif fp.suffix == ".json":
            obj = json.loads(fp.read_text(encoding="utf-8"))
            st.json(obj, expanded=False)
            st.download_button("下载 JSON", data=fp.read_bytes(),
                                file_name=fp.name, mime="application/json")
    except Exception as e:
        st.error(f"读取 {fp.name} 失败: {e}")


# ----------------------------------------------------------------------
# 运行 Tab 中每个 step 卡片
# ----------------------------------------------------------------------
_STATUS_ICON = {
    "pending": "⬜",
    "running": "🔄",
    "done": "✅",
    "error": "❌",
}


def render_step_card(project_name: str, step: dict, cookie: str = "") -> None:
    """渲染单个 step 卡片。"""
    key = step["key"]
    name = step["name"]
    desc = step["desc"]
    st_state = state.read_step_state(project_name, key)
    status = st_state.get("status", "pending")
    icon = _STATUS_ICON.get(status, "⬜")

    started = state.fmt_time(st_state.get("started_at"))
    finished = state.fmt_time(st_state.get("finished_at"))
    error = st_state.get("error")

    can = state.can_run(project_name, key)
    alive = _safe_alive(project_name, key)

    with st.container(border=True):
        head_col, btn_col = st.columns([4, 2])
        with head_col:
            st.markdown(f"### {icon} {name}")
            st.caption(desc)
            if status == "running":
                st.caption(f"⏱️ 启动于 {started}")
            elif status == "done":
                st.caption(f"✅ {started} → {finished}")
            elif status == "error":
                st.caption(f"❌ 失败于 {finished}")
                if error:
                    st.error(error, icon="🚨")
        with btn_col:
            btn_disabled = (status == "running") or not can
            col1, col2 = st.columns(2)
            with col1:
                if st.button("▶ 运行", key=f"run_{key}",
                              disabled=btn_disabled,
                              use_container_width=True):
                    _launch(project_name, key, cookie)
            with col2:
                # 重跑 = 不管状态强制跑（仍需依赖满足）
                if st.button("↻ 重跑", key=f"rerun_{key}",
                              disabled=status == "running" or not can,
                              use_container_width=True):
                    _launch(project_name, key, cookie, force=True)

        # 日志尾部
        log_tail = state.read_step_log(project_name, key, tail=30)
        if log_tail:
            with st.expander(f"📜 日志尾部 ({key})", expanded=(status == "running")):
                st.code(log_tail, language="text")

        # 产出文件
        if status == "done":
            _render_step_outputs(project_name, key)


def _safe_alive(project_name: str, step_key: str) -> bool:
    try:
        from app.runner import is_step_process_alive
        return is_step_process_alive(project_name, step_key)
    except Exception:
        return False


def _launch(project_name: str, step_key: str, cookie: str, force: bool = False) -> None:
    """触发一个 step 在后台运行。"""
    from app import runner
    try:
        pid = runner.run_step_in_background(project_name, step_key, cookie=cookie)
        st.success(f"已启动 {step_key} (pid={pid})")
        st.toast(f"{step_key} 已在后台启动", icon="🚀")
    except Exception as e:
        st.error(f"启动失败: {e}")


def _render_step_outputs(project_name: str, step_key: str) -> None:
    """展示该 step 的产出（figures / data_files / stats / result）。"""
    root = state.project_root(project_name)
    result_file = root / ".state" / f"{step_key}.result.json"
    if not result_file.exists():
        return
    try:
        result = json.loads(result_file.read_text(encoding="utf-8"))
    except Exception:
        return

    stats = result.get("stats") or {}
    figs = result.get("figures") or []
    data_files = result.get("data_files") or []

    if stats:
        with st.expander("📈 关键指标"):
            if isinstance(stats, dict):
                rows = []
                for k, v in stats.items():
                    if isinstance(v, (dict, list)):
                        import json as _json
                        v = _json.dumps(v, ensure_ascii=False)
                    rows.append({"指标": k, "值": v})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.write(stats)

    if figs:
        with st.expander(f"🖼️ 图表 ({len(figs)})"):
            for fig_path, fig_title, fig_caption in figs:
                p = Path(fig_path)
                if p.exists():
                    st.image(str(p), caption=f"{fig_title} — {fig_caption}" if fig_caption else fig_title,
                             use_container_width=True)

    if data_files:
        with st.expander(f"📁 数据文件 ({len(data_files)})"):
            for fn in data_files:
                p = root / "data" / fn
                if p.exists():
                    size_kb = p.stat().st_size / 1024
                    st.markdown(f"- `{fn}` ({size_kb:.1f} KB)")
                else:
                    st.markdown(f"- `{fn}` (未生成)")
