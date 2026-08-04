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
# 运行 Tab — 线性 step 列表 (Modern Minimal)
# 不用卡片马赛克：每行一个 step，左 badge/中描述/右按钮，用极细分隔线分层
# ----------------------------------------------------------------------

_STATUS_BADGE = {
    # (label, bg_color, text_color)
    "pending": ("待运行",  "#E5E7EB", "#6B7280"),
    "running": ("运行中",  "#DBEAFE", "#1E40AF"),
    "done":    ("已完成",  "#DCFCE7", "#166534"),
    "error":   ("失败",    "#FEE2E2", "#991B1B"),
}


def _badge(status: str) -> str:
    label, bg, tc = _STATUS_BADGE.get(status, _STATUS_BADGE["pending"])
    return (f"<span class='bop-badge' style='background:{bg};color:{tc};"
            f"padding:2px 10px;border-radius:999px;font-size:11px;"
            f"font-weight:600;letter-spacing:.2px;'>{label}</span>")


def render_step_card(project_name: str, step: dict, cookie: str = "") -> None:
    """线性单 step 行（无卡片 chrome，只靠分隔线与左右对齐组构层次）。"""
    key = step["key"]
    name = step["name"]
    desc = step["desc"]
    st_state = state.read_step_state(project_name, key)
    status = st_state.get("status", "pending")

    started = state.fmt_time(st_state.get("started_at"))
    finished = state.fmt_time(st_state.get("finished_at"))
    error = st_state.get("error")
    can = state.can_run(project_name, key)

    # 行头：左组（序号 + 徽章 + 标题/描述） | 右组（运行/重跑按钮）
    # 用 markdown HTML 做组内紧凑排版，按钮留在 Streamlit 原生列
    # 序号 (Step0 → 0)
    try:
        idx = int(name.split(" ")[0].replace("Step", ""))
    except Exception:
        idx = ""
    idx_html = (f"<span class='bop-stepidx' style='font-family:-apple-system,"
                f"BlinkMacSystemFont,sans-serif;font-size:11px;"
                f"font-weight:600;color:#9CA3AF;background:#F3F4F6;"
                f"padding:2px 7px;border-radius:4px;margin-right:10px;"
                f"letter-spacing:.5px;'>{idx:02d}</span>" if idx != "" else "")

    left_top = f"{idx_html}<span class='bop-stepname' style='font-size:14px;font-weight:600;color:#111827;'>{name}</span>"
    status_html = _badge(status)
    # 时间副文案
    time_str = ""
    if status == "running":
        time_str = f"启动于 {started}"
    elif status == "done":
        dur = ""
        try:
            s = st_state.get("started_at")
            f = st_state.get("finished_at")
            if s and f:
                diff = float(f) - float(s)
                if diff < 60:
                    dur = f" · {diff:.1f}s"
                else:
                    dur = f" · {diff/60:.1f}min"
        except Exception:
            pass
        time_str = f"{started} → {finished}{dur}"
    elif status == "error":
        time_str = f"失败于 {finished}"

    # 左列：紧凑两行
    st.markdown(
        f"<div class='bop-steprow'>"
        f"  <div style='display:flex;align-items:center;gap:6px;flex-wrap:wrap;'>"
        f"    {left_top}"
        f"    {status_html}"
        f"  </div>"
        f"  <div style='margin-top:2px;font-size:12px;color:#6B7280;line-height:1.5;'>{desc}{(' · ' + time_str) if time_str else ''}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # 按钮区 + 产出折叠
    btn_col, exp_col = st.columns([1, 3], gap="small")
    with btn_col:
        col_run, col_rerun = st.columns(2, gap="small")
        btn_disabled = (status == "running") or not can
        with col_run:
            if st.button("运行", key=f"run_{key}",
                          disabled=btn_disabled,
                          use_container_width=True, type="primary" if status == "pending" else "secondary"):
                _launch(project_name, key, cookie)
        with col_rerun:
            if st.button("重跑", key=f"rerun_{key}",
                          disabled=status == "running" or not can,
                          use_container_width=True):
                _launch(project_name, key, cookie, force=True)

    with exp_col:
        # 轻量：状态特定的错误提示内嵌在按钮行下方
        extra_lines = 0
        if status == "error" and error:
            # 只取第一行错误作摘要，完整看日志
            err_head = str(error).splitlines()[0][:120]
            st.caption(f"🚨 {err_head}")
            extra_lines += 1

        # 日志折叠
        log_tail = state.read_step_log(project_name, key, tail=30)
        show_expander = bool(log_tail) or (status == "done")
        if show_expander:
            label = "日志"
            if status == "done":
                if _step_has_outputs(project_name, key):
                    label = "日志 · 产出"
            expanded = status == "running"
            with st.expander(label, expanded=expanded):
                if log_tail:
                    st.code(log_tail, language="text", wrap_lines=True)
                if status == "done":
                    _render_step_outputs(project_name, key)

    # 极细分隔线（最后一行除外）
    st.markdown(
        "<div style='height:1px;background:#F0F1F3;margin:12px 0;'></div>",
        unsafe_allow_html=True,
    )


def _step_has_outputs(project_name: str, step_key: str) -> bool:
    root = state.project_root(project_name)
    return (root / ".state" / f"{step_key}.result.json").exists()


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
