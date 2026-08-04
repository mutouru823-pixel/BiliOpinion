# -*- coding: utf-8 -*-
"""BiliOpinion Streamlit 前端主入口 — Modern Minimal (Linear/Notion 式)。

启动：
    streamlit run app/home.py
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
# 页面配置 + 全局设计 tokens（Modern Minimal）
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="BiliOpinion",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "BiliOpinion · B 站评论舆情演化分析管线",
    },
)

# ----------------------------------------------------------------------
# 全局 CSS 注入（设计 tokens + 组件细调，不依赖自动生成类名）
# 用 :root 定义 CSS 变量，后续自定义元素直接用 var(...)
# ----------------------------------------------------------------------
_GLOBAL_CSS = """
<style>
/* ====== Design tokens (Modern Minimal — Linear/Notion 式) ====== */
:root {
  --bop-accent:        #4F46E5;  /* 主色 Indigo */
  --bop-accent-hover:  #4338CA;
  --bop-accent-soft:   #EEF2FF;
  --bop-bg:            #FAFAFB;  /* 页面层 */
  --bop-surface:       #FFFFFF;  /* 分区/控件层 */
  --bop-border:        #E5E7EB;  /* 控件边框 */
  --bop-divider:       #F0F1F3;  /* 列表分隔线 */
  --bop-muted-border:  #ECEEF1;
  --bop-text:          #111827;  /* 主文字 */
  --bop-text-mid:      #4B5563;
  --bop-text-muted:    #6B7280;
  --bop-text-faint:    #9CA3AF;
  --bop-ok:            #16A34A;
  --bop-ok-bg:         #DCFCE7;
  --bop-warn:          #B45309;
  --bop-warn-bg:       #FEF3C7;
  --bop-err:           #DC2626;
  --bop-err-bg:        #FEE2E2;
  --bop-info:          #2563EB;
  --bop-info-bg:       #DBEAFE;
  --bop-radius-sm:     6px;
  --bop-radius:        8px;
  --bop-radius-lg:     12px;
  --bop-shadow-sm:     0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.04);
  --bop-shadow:        0 1px 2px rgba(16,24,40,.05), 0 2px 6px rgba(16,24,40,.04);
}

/* ====== 字体：系统字体栈 ====== */
html, body, [class*="css"] {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display",
               "PingFang SC", "Microsoft YaHei", "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--bop-text);
}
body {
  background: var(--bop-bg);
}

/* ====== 主容器内边距收紧（默认 Streamlit 太松） ====== */
.stApp > header {
  height: 0;
  display: none;
}
.block-container {
  padding-top: 1.4rem;
  padding-bottom: 3rem;
  padding-left: 2rem;
  padding-right: 2rem;
  max-width: 1280px;
}
@media (max-width: 768px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
}

/* ====== 侧边栏：减噪，分层更弱更线性 ====== */
section[data-testid="stSidebar"] {
  background: var(--bop-surface);
  border-right: 1px solid var(--bop-divider);
}
section[data-testid="stSidebar"] .block-container {
  padding-top: 1.4rem;
  padding-bottom: 1rem;
}

/* ====== Tabs: Notion 式下划线 + 移除重 chrome ====== */
div[data-testid="stTabs"] button[data-baseweb="tab"] {
  background: transparent !important;
  color: var(--bop-text-muted) !important;
  padding: 0.6rem 0.2rem 0.6rem 0.2rem !important;
  margin: 0 0.9rem !important;
  border-radius: 0 !important;
  border-bottom: 2px solid transparent !important;
  box-shadow: none !important;
  font-size: 14px !important;
  font-weight: 600 !important;
  letter-spacing: 0.1px;
}
div[data-testid="stTabs"] button[data-baseweb="tab"]:hover {
  color: var(--bop-text-mid) !important;
}
div[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
  color: var(--bop-text) !important;
  border-bottom-color: var(--bop-accent) !important;
}
div[data-testid="stTabs"] > div:nth-child(1) {
  background: var(--bop-surface);
  border-bottom: 1px solid var(--bop-divider);
  gap: 0;
}

/* ====== 按钮：线性扁平，Primary=实色，Secondary=描边 ====== */
button[kind="primary"] {
  background: var(--bop-accent) !important;
  color: #fff !important;
  border-radius: var(--bop-radius-sm) !important;
  font-weight: 600 !important;
  border: 1px solid var(--bop-accent) !important;
  box-shadow: var(--bop-shadow-sm) !important;
  transition: background .15s ease, transform .05s ease;
}
button[kind="primary"]:hover { background: var(--bop-accent-hover) !important; }
button[kind="primary"]:disabled {
  background: #D1D5DB !important;
  border-color: #D1D5DB !important;
  color: #fff !important;
  box-shadow: none !important;
  opacity: .9;
}
button[kind="secondary"] {
  background: #fff !important;
  color: var(--bop-text-mid) !important;
  border-radius: var(--bop-radius-sm) !important;
  border: 1px solid var(--bop-border) !important;
  font-weight: 500 !important;
}
button[kind="secondary"]:hover {
  border-color: #CBD5E1 !important;
  background: #FAFAFB !important;
  color: var(--bop-text) !important;
}
button[kind="secondary"]:disabled {
  opacity: .5 !important;
}
/* 无 kind 的小按钮 */
button:not([kind]) {
  border-radius: var(--bop-radius-sm) !important;
}

/* ====== 输入控件：扁平，去多余阴影 ====== */
div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
div[data-baseweb="textarea"] > div,
div[data-testid="stNumberInput"] > div[data-baseweb="input"] > div {
  border-radius: var(--bop-radius-sm) !important;
  border-color: var(--bop-border) !important;
  background: var(--bop-surface) !important;
  box-shadow: none !important;
  transition: border-color .12s ease;
}
div[data-baseweb="input"]:hover > div,
div[data-baseweb="select"]:hover > div {
  border-color: #CBD5E1 !important;
}
div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="select"]:focus-within > div {
  border-color: var(--bop-accent) !important;
  box-shadow: 0 0 0 3px var(--bop-accent-soft) !important;
}
label[data-testid="stMetricLabel"],
label[data-baseweb="radio"],
label[data-baseweb="checkbox"] {
  color: var(--bop-text-mid) !important;
}

/* ====== selectbox / radio 高亮色 ====== */
div[role="radiogroup"] label[data-baseweb="radio"] input:checked + div {
  background-color: var(--bop-accent) !important;
}
div[role="option"][aria-selected="true"],
div[role="option"]:hover {
  background: var(--bop-accent-soft) !important;
  color: var(--bop-text) !important;
}

/* ====== Progress bar ====== */
div[data-testid="stProgress"] > div > div > div {
  background: var(--bop-accent) !important;
  border-radius: 999px !important;
}
div[data-testid="stProgress"] > div > div {
  background: #EEF0F3 !important;
  border-radius: 999px !important;
  height: 6px !important;
}
/* Streamlit st.progress 自带文字说明（st.progress(value, text="...")） */
div[data-testid="stProgress"] + div {
  font-size: 12px !important;
  color: var(--bop-text-muted) !important;
  margin-top: -6px;
  letter-spacing: 0.2px;
}

/* ====== Checkbox / Switch ====== */
div[data-testid="stCheckbox"] input:checked + div {
  background-color: var(--bop-accent) !important;
  border-color: var(--bop-accent) !important;
}

/* ====== Slider ====== */
div[data-testid="stSlider"] .thumb {
  background-color: var(--bop-accent) !important;
  border-color: var(--bop-accent) !important;
}

/* ====== Streamlit 原生容器去边框（Linear 式默认无边框） ====== */
div[data-testid="stContainer"] {
  border: none !important;
  padding: 0 !important;
}
/* st.container(border=True) 保留，仅微调 */
div[data-testid="stVerticalBlock"] div[style*="border: 1px solid"] {
  border-color: var(--bop-border) !important;
  border-radius: var(--bop-radius) !important;
  background: var(--bop-surface);
  box-shadow: var(--bop-shadow-sm);
}

/* ====== st.info/warning/success/error 去 emoji + Linear 色带 ====== */
div[data-testid="stAlertContainer"] {
  border-radius: var(--bop-radius) !important;
  border: none !important;
  box-shadow: var(--bop-shadow-sm);
  padding: 0.7rem 1rem !important;
  font-size: 13px;
}
div[data-testid="stAlertContainer"] .stAlert {
  background: transparent !important;
}
/* 每种 alert 顶部一条色带 */
div[data-testid="stAlertContainer"]:has(.stAlert[data-testid="stAlert-info"]) {
  background: var(--bop-info-bg) !important;
  border-left: 3px solid var(--bop-info) !important;
}
div[data-testid="stAlertContainer"]:has(.stAlert[data-testid="stAlert-success"]) {
  background: var(--bop-ok-bg) !important;
  border-left: 3px solid var(--bop-ok) !important;
}
div[data-testid="stAlertContainer"]:has(.stAlert[data-testid="stAlert-warning"]) {
  background: var(--bop-warn-bg) !important;
  border-left: 3px solid var(--bop-warn) !important;
}
div[data-testid="stAlertContainer"]:has(.stAlert[data-testid="stAlert-error"]) {
  background: var(--bop-err-bg) !important;
  border-left: 3px solid var(--bop-err) !important;
}

/* ====== code block (日志/预览) 更紧凑 ====== */
pre {
  background: #0F172A !important;
  color: #E2E8F0 !important;
  border-radius: var(--bop-radius-sm) !important;
  font-size: 12px !important;
  line-height: 1.55 !important;
  padding: 0.9rem 1rem !important;
  border: 1px solid #1E293B;
}
pre code {
  font-family: "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace !important;
  font-size: 12px !important;
}

/* ====== 代码/JSON expander 去强 chrome ====== */
div[data-testid="stExpander"] details {
  border: 1px solid var(--bop-border) !important;
  border-radius: var(--bop-radius-sm) !important;
  background: var(--bop-surface);
  box-shadow: none !important;
}
div[data-testid="stExpander"] summary {
  padding: 0.5rem 0.9rem !important;
  font-size: 13px;
  font-weight: 600;
  color: var(--bop-text-mid);
}
div[data-testid="stExpander"] summary:hover {
  background: #FAFAFB;
}

/* ====== Dataframe / table 去 chrome ====== */
div[data-testid="stDataFrame"] {
  border: 1px solid var(--bop-border) !important;
  border-radius: var(--bop-radius-sm) !important;
  overflow: hidden;
  background: var(--bop-surface);
}

/* ====== Image / charts caption 缩小 ====== */
img + em, figcaption, .caption {
  font-size: 12px !important;
  color: var(--bop-text-muted) !important;
}

/* ====== 下载按钮对齐 ====== */
a[kind="secondary"] {
  border-radius: var(--bop-radius-sm) !important;
}
</style>
"""
st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def _brand_header(title: str = "BiliOpinion", subtitle: str | None = None) -> None:
    """品牌 header：自定义，不使用 Streamlit 内部 header。"""
    sub = subtitle or "B 站评论舆情演化分析管线 · 前端操作台"
    html = f"""
    <div style="display:flex;align-items:flex-end;justify-content:space-between;
                padding: 0 0 14px 0;border-bottom:1px solid var(--bop-divider);margin-bottom:14px;">
      <div>
        <div style="display:flex;align-items:center;gap:10px;">
          <span style="width:30px;height:30px;border-radius:8px;
                       background:linear-gradient(135deg, var(--bop-accent), #818CF8);
                       display:inline-flex;align-items:center;justify-content:center;
                       color:#fff;font-weight:700;font-size:14px;box-shadow:var(--bop-shadow-sm);">📊</span>
          <h1 style="font-size:22px;font-weight:700;margin:0;color:var(--bop-text);
                     letter-spacing:-0.01em;">{title}</h1>
        </div>
        <div style="margin-top:4px;margin-left:40px;font-size:12.5px;color:var(--bop-text-muted);">
          {sub}
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:10px;">
        <span style="display:inline-flex;align-items:center;gap:6px;
                     padding:4px 10px;border-radius:999px;background:#F3F4F6;
                     color:var(--bop-text-muted);font-size:11.5px;font-weight:600;">
          <span style="width:6px;height:6px;border-radius:50%;background:var(--bop-ok);
                       box-shadow:0 0 0 3px #DCFCE7;"></span>
          Ready
        </span>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# 侧边栏：项目选择 + Cookie + 全局（Linear 式极简分组）
# ----------------------------------------------------------------------
def sidebar() -> None:
    with st.sidebar:
        # 侧边栏品牌 header
        st.markdown("""
        <div style="padding: 2px 0 14px 0; border-bottom: 1px solid var(--bop-divider);">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="width:26px;height:26px;border-radius:7px;
                         background:linear-gradient(135deg, var(--bop-accent), #818CF8);
                         display:inline-flex;align-items:center;justify-content:center;
                         color:#fff;font-weight:700;font-size:12px;">📊</span>
            <span style="font-size:15px;font-weight:700;color:var(--bop-text);
                         letter-spacing:-0.01em;">BiliOpinion</span>
          </div>
          <div style="margin-top:4px;margin-left:34px;font-size:11.5px;color:var(--bop-text-faint);
                      letter-spacing:0.1px;">B 站舆情演化分析管线</div>
        </div>
        """, unsafe_allow_html=True)

        # 项目分组
        _sidebar_group("项目")
        existing = state.list_projects()

        col1, col2 = st.columns([5, 1], gap="small")
        with col1:
            options = ["➕ 新建项目…"] + existing
            idx = 0
            cur = state.get_current_project()
            if cur and cur in existing:
                idx = options.index(cur)
            choice = st.selectbox("选择项目", options=options, index=idx,
                                    label_visibility="collapsed")
        with col2:
            if st.button("↻", help="刷新项目列表", width='stretch'):
                st.rerun()

        if choice == "➕ 新建项目…":
            new_name = st.text_input("项目名 (英文/拼音)", key="new_project_name",
                                       placeholder="my_event", label_visibility="collapsed")
            if new_name and st.button("创建项目", type="primary", width='stretch'):
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

        # 项目摘要（Linear 式：纯数据点分行，**去 markdown bold 反引号**）
        cur = state.get_current_project()
        if cur:
            summ = state.project_summary(cur)
            st.markdown("")
            _sidebar_group("当前项目")
            _sidebar_kv("名称", cur)
            _sidebar_kv("主题", summ["topic"] or "未设置")
            _sidebar_kv("进度", f"{summ['n_done']} / {summ['n_total']} step")
            if summ["raw_comments"]:
                _sidebar_kv("原始评论", f"{summ['raw_comments']:,}")
            if summ["valid_comments"]:
                _sidebar_kv("有效评论", f"{summ['valid_comments']:,}")
            if summ["running_steps"]:
                html_names = "、".join(summ["running_steps"])
                st.markdown(
                    f"<div style='margin:4px 2px 0 2px;padding:6px 9px;"
                    f"background:var(--bop-info-bg);color:var(--bop-info);"
                    f"border-radius:var(--bop-radius-sm);font-size:11.5px;font-weight:600;"
                    f"display:flex;align-items:center;gap:6px;'>"
                    f"<span style='width:5px;height:5px;border-radius:50%;background:var(--bop-info);"
                    f"box-shadow:0 0 0 3px var(--bop-info-bg);'></span>"
                    f"运行中：{html_names}</div>",
                    unsafe_allow_html=True)

        st.markdown("")
        _sidebar_group("🔑 B 站 Cookie")
        st.caption("用于 Step0 采集。留空则回落到 `.env` 的 `BILI_COOKIE`。")
        # 只传 key、不传 value：同时传会与 session_state 冲突并触发 Streamlit 警告
        cookie = st.text_input(
            "Cookie", type="password",
            key="cookie_input",
            label_visibility="collapsed",
            placeholder="粘贴整段 Cookie…")
        st.session_state["bili_cookie"] = cookie
        if st.button("记住到 .env", width='stretch'):
            _save_dotenv(cookie)
        if not cookie:
            env_cookie = _env_cookie()
            if env_cookie:
                st.caption(f"✅ 已从 .env 读到 Cookie（{len(env_cookie)} 字符）")
            else:
                st.caption("⚠️ 未检测到 Cookie，Step0 采集会失败")

        st.markdown("")
        from app.paths import writable_base as _wb
        _wbase = _wb()
        st.caption(f"数据目录：{_wbase.name}/outputs/")


def _sidebar_group(title: str) -> None:
    """侧边栏分组标题（Linear 式：小号全大写 + 重字重 + 灰字）。"""
    st.markdown(
        f"<div style='font-size:10.5px;font-weight:700;letter-spacing:0.12em;"
        f"color:var(--bop-text-faint);text-transform:uppercase;"
        f"margin:10px 2px 6px 2px;'>{title}</div>",
        unsafe_allow_html=True)


def _sidebar_kv(key: str, val: str) -> None:
    """侧边栏纯 key-value 行，Linear 式（左对齐灰 key，右对齐黑 val，一行）。"""
    st.markdown(
        f"<div style='display:flex;justify-content:space-between;align-items:baseline;"
        f"padding:2px 2px;gap:12px;'>"
        f"<span style='font-size:11.5px;color:var(--bop-text-faint);'>{key}</span>"
        f"<span style='font-size:12px;color:var(--bop-text);font-weight:600;"
        f"max-width:65%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>{val}</span>"
        f"</div>",
        unsafe_allow_html=True)


def _env_cookie() -> str:
    """读取当前可用的 BILI_COOKIE（环境变量 > .env > Streamlit Secrets）。"""
    import os
    val = os.environ.get("BILI_COOKIE", "").strip()
    if val:
        return val
    try:
        from app.paths import writable_base
        for base in {writable_base(), REPO_ROOT}:
            env_file = base / ".env"
            if not env_file.exists():
                continue
            for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith("BILI_COOKIE=") and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    try:
        return str(st.secrets.get("BILI_COOKIE", "")).strip()
    except Exception:
        return ""


def _save_dotenv(cookie: str) -> None:
    """写入 .env（Streamlit Cloud 上只读会静默跳过）。"""
    try:
        from app.paths import writable_base
        env_file = writable_base() / ".env"
        lines = []
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if not line.startswith("BILI_COOKIE="):
                    lines.append(line)
        if cookie:
            lines.append(f"BILI_COOKIE={cookie}")
        env_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        st.success("已写入 .env", icon="✅")
    except Exception as e:
        st.warning(f"写入 .env 失败（可在 Streamlit Secrets 中配置 BILI_COOKIE）: {e}", icon="⚠️")


# ----------------------------------------------------------------------
# 主页面（带品牌 header）
# ----------------------------------------------------------------------
def main() -> None:
    sidebar()
    _brand_header()

    cur = state.get_current_project()
    if not cur:
        _render_welcome()
        return

    tab_cfg, tab_run, tab_report, tab_proj = st.tabs(
        ["配置", "运行", "报告", "项目"])

    with tab_cfg:
        _tab_config(cur)
    with tab_run:
        _tab_run(cur)
    with tab_report:
        _tab_report(cur)
    with tab_proj:
        _tab_projects()


def _render_welcome() -> None:
    """欢迎页：Linear 式无卡片 Hero + 三点简介。"""
    hero = """
    <div style="padding: 60px 0 40px 0;">
      <div style="font-size:34px;font-weight:700;color:var(--bop-text);
                  letter-spacing:-0.02em;line-height:1.2;max-width:620px;">
        先建一个项目，
        <span style="color:var(--bop-accent);">然后让管线替你跑。</span>
      </div>
      <div style="margin-top:10px;font-size:15px;color:var(--bop-text-mid);
                  line-height:1.6;max-width:620px;">
        在左侧选择「➕ 新建项目…」，或打开已有项目。
        BiliOpinion 把 10 步舆情分析管线拆成可单独触发的流程——
        采集、清洗、时间演化、主题、情感、网络、BERT、报告，按依赖解锁，逐步推进。
      </div>
    </div>
    """
    st.markdown(hero, unsafe_allow_html=True)

    col_a, col_b, col_c = st.columns(3, gap="medium")
    items = [
        ("01", "按依赖触发", "每步独立运行，前序完成自动解锁后续；卡住随时重跑单步。"),
        ("02", "后台执行", "步骤运行在子进程里，采集几小时也不会卡死 UI，随时回来看状态。"),
        ("03", "产出即用", "图表、指标、数据文件、自包含 report.html 全部落盘在 outputs/。"),
    ]
    for c, (num, title, desc) in zip([col_a, col_b, col_c], items):
        with c:
            st.markdown(
                f"<div style='font-size:11px;font-weight:700;letter-spacing:0.1em;"
                f"color:var(--bop-accent);text-transform:uppercase;'>{num}</div>"
                f"<div style='margin-top:6px;font-size:15px;font-weight:600;"
                f"color:var(--bop-text);'>{title}</div>"
                f"<div style='margin-top:4px;font-size:13px;color:var(--bop-text-muted);"
                f"line-height:1.6;'>{desc}</div>",
                unsafe_allow_html=True)


# ----------------------------------------------------------------------
# 配置 Tab（Linear 式：模式 seg 控件在右上方，标题+副文案）
# ----------------------------------------------------------------------
def _tab_config(project_name: str) -> None:
    _page_title(
        "配置",
        "常用字段全部表单化；高级字段可切到 YAML 原文模式直接编辑。保存前会用 `load_config` 做一次校验。",
    )

    cfg_file = state.config_path(project_name)
    cfg = config_ui.load_config_file(cfg_file)
    eff = state.project_root(project_name) / "effective_config.yaml"
    if eff.exists():
        try:
            import yaml
            eff_cfg = yaml.safe_load(eff.read_text(encoding="utf-8")) or {}
            cfg = config_ui._deep_merge(cfg, eff_cfg)
        except Exception:
            pass

    # 模式切换：st.segmented 风格（用 radio + 容器模拟）
    head_c1, head_c2 = st.columns([4, 1.6], gap="large")
    with head_c2:
        mode = st.radio(
            "编辑模式",
            options=["表单", "YAML 原文"],
            label_visibility="collapsed",
            horizontal=True,
        )
    with head_c1:
        st.caption(
            "💡 修改完记得点「💾 保存」—— 配置先存盘，运行 Tab 的执行器才会读到最新内容。"
        )

    st.markdown(
        f"<div style='height:1px;background:var(--bop-divider);margin:4px 0 18px 0;'></div>",
        unsafe_allow_html=True)

    if mode == "YAML 原文":
        text = st.text_area(
            "config.yaml",
            value=config_ui.dict_to_yaml(cfg),
            height=640,
            label_visibility="collapsed")
        try:
            cfg = config_ui.yaml_to_dict(text)
        except Exception as e:
            st.error(f"YAML 解析失败：{e}")
    else:
        cfg = config_ui.render_config_form(cfg, cookie=st.session_state.get("bili_cookie", ""))

    st.markdown(
        f"<div style='height:1px;background:var(--bop-divider);margin:24px 0 14px 0;'></div>",
        unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1.1, 1.1, 3], gap="small")
    with col1:
        if st.button("💾 保存配置", type="primary", width='stretch'):
            try:
                from biliopinion.config import load_config
                import tempfile, yaml
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".yaml", delete=False, mode="w", encoding="utf-8")
                yaml.safe_dump(cfg, tmp, allow_unicode=True, sort_keys=False)
                tmp.close()
                load_config(tmp.name)
                config_ui.save_config(cfg, project_name)
                st.success("配置已保存", icon="✅")
            except Exception as e:
                st.error(f"配置校验失败：{e}", icon="🚨")
    with col2:
        st.download_button(
            "⬇️ 下载 yaml",
            data=config_ui.dict_to_yaml(cfg).encode("utf-8"),
            file_name=f"{project_name}_config.yaml",
            mime="application/x-yaml",
            width='stretch',
        )
    with col3:
        # 展示保存位置
        st.caption(f"保存位置：`outputs/{project_name}/.state/config.yaml`")


# ----------------------------------------------------------------------
# 运行 Tab（Linear 式：顶部 KPI + 操作条，再无卡片纯 step 列表）
# ----------------------------------------------------------------------
def _tab_run(project_name: str) -> None:
    _page_title(
        "运行",
        "10 步按依赖顺序解锁。每步独立跑在后台子进程，产出落盘后自动解锁下一步。",
    )

    if not state.config_path(project_name).exists():
        st.warning("尚未保存配置。请先到「配置」Tab 保存。")
        return

    cookie = st.session_state.get("bili_cookie", "")
    has_running = any(
        s.get("status") == "running"
        for s in state.all_step_states(project_name).values()
    )

    # 有 step 在跑时，整块面板每 3 秒自动重绘一次，状态与日志自己会动；
    # 空闲时不轮询，避免无谓的重跑开销。
    if has_running:
        _run_panel_live(project_name, cookie)
    else:
        _run_panel(project_name, cookie)


@st.fragment(run_every=3)
def _run_panel_live(project_name: str, cookie: str) -> None:
    _run_panel(project_name, cookie, live=True)


def _run_panel(project_name: str, cookie: str, live: bool = False) -> None:
    """运行面板：KPI + 操作条 + step 列表。"""
    # KPI 条（Linear 式：4 个数值点）
    states = state.all_step_states(project_name)
    done = sum(1 for s in states.values() if s.get("status") == "done")
    running = sum(1 for s in states.values() if s.get("status") == "running")
    err = sum(1 for s in states.values() if s.get("status") == "error")
    pending = len(states) - done - running - err
    total = len(states)
    pct = int((done / total) * 100) if total else 0

    k1, k2, k3, k4 = st.columns(4, gap="small")
    _kpi_card(k1, f"{done}/{total}", "已完成", ok=(done == total))
    _kpi_card(k2, f"{running}", "运行中", info=(running > 0))
    _kpi_card(k3, f"{err}", "失败", danger=(err > 0))
    _kpi_card(k4, f"{pending}", "待运行")
    # 进度条（放在 KPI 下方，整宽）
    st.progress(done / total if total else 0, text=f"{pct}% · 完成 {done}/{total}")

    st.markdown(
        f"<div style='height:1px;background:var(--bop-divider);margin:16px 0 12px 0;'></div>",
        unsafe_allow_html=True)

    # 操作条
    c_run, c_refresh, c_note = st.columns([1, 1, 3], gap="small")
    with c_run:
        if st.button("▶ 运行到下一步", help="启动第一个 pending/error 且依赖满足的 step",
                      type="primary", width='stretch'):
            _run_next_pending(project_name, cookie)
    with c_refresh:
        if st.button("↻ 刷新状态", help="重新读取所有 step 状态文件",
                      width='stretch'):
            st.rerun()
    with c_note:
        if live:
            st.markdown(
                "<div style='display:flex;align-items:center;gap:7px;height:38px;"
                "font-size:12px;color:var(--bop-text-muted);'>"
                "<span style='width:6px;height:6px;border-radius:50%;background:#2563EB;'></span>"
                "实时刷新中 · 每 3 秒自动更新状态与日志</div>",
                unsafe_allow_html=True)

    st.markdown("")

    # 纯线性 step 列表
    for step in state.STEPS:
        viewer.render_step_card(project_name, step, cookie=cookie)


def _kpi_card(col, value: str, label: str, ok: bool = False,
              info: bool = False, danger: bool = False) -> None:
    """Linear KPI 卡 — 纯背景色 + 双行排版，去重阴影。"""
    if danger:
        bg, vc = "#FEF2F2", "#B91C1C"
    elif ok:
        bg, vc = "#F0FDF4", "#15803D"
    elif info:
        bg, vc = "#EFF6FF", "#1D4ED8"
    else:
        bg, vc = "#FFFFFF", "var(--bop-text)"
    col.markdown(
        f"<div style='background:{bg};border:1px solid var(--bop-border);"
        f"border-radius:var(--bop-radius);padding:12px 14px;'>"
        f"<div style='font-size:22px;font-weight:700;color:{vc};"
        f"letter-spacing:-0.02em;line-height:1;'>{value}</div>"
        f"<div style='margin-top:5px;font-size:11.5px;color:var(--bop-text-muted);"
        f"letter-spacing:0.05em;text-transform:uppercase;font-weight:600;'>{label}</div>"
        f"</div>",
        unsafe_allow_html=True)


# ----------------------------------------------------------------------
# 通用小工具
# ----------------------------------------------------------------------
def _page_title(title: str, subtitle: str | None = None) -> None:
    """Tab 内页标题（Linear 式：大标题 + 灰色副文案）。"""
    html = f"""
    <div style="margin:4px 0 14px 0;">
      <div style="font-size:20px;font-weight:700;color:var(--bop-text);
                  letter-spacing:-0.015em;">{title}</div>
      {"<div style='margin-top:4px;font-size:13px;color:var(--bop-text-muted);line-height:1.55;'>" + subtitle + "</div>" if subtitle else ""}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


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
                    st.toast(f"已启动 {step['name']}（pid={pid}）", icon="🚀")
                    st.rerun()
                except Exception as e:
                    st.error(f"启动 {step['name']} 失败：{e}", icon="🚨")
                    return
    st.info("所有 step 都已完成或正在运行。", icon="ℹ️")


# ----------------------------------------------------------------------
# 报告 Tab
# ----------------------------------------------------------------------
def _tab_report(project_name: str) -> None:
    _page_title(
        "报告与产出",
        "每步完成后，图表、数据、分析报告都会出现在这里。最终 report.html 可以直接下载。",
    )
    viewer.render_report_tab(project_name)


# ----------------------------------------------------------------------
# 项目 Tab（Linear 式：数据行用轻表格 + 操作行紧凑排版）
# ----------------------------------------------------------------------
def _tab_projects() -> None:
    _page_title(
        "项目管理",
        "所有 `outputs/` 下的项目都会在这里列出来。点「切换」跳到对应项目，或「删除」彻底移除。",
    )
    projects = state.list_projects()
    if not projects:
        st.info("暂无项目。请在左侧「新建项目…」开始。", icon="📁")
        return

    rows = []
    for name in projects:
        s = state.project_summary(name)
        rows.append({
            "项目": name,
            "主题": s["topic"] or "—",
            "进度": f"{s['n_done']}/{s['n_total']}",
            "原始评论": s["raw_comments"] or 0,
            "有效评论": s["valid_comments"] or 0,
            "报告": "✅" if s["has_report"] else "—",
        })
    st.dataframe(rows, width='stretch', hide_index=True, column_config={
        "项目": st.column_config.TextColumn(width="small"),
        "主题": st.column_config.TextColumn(width="large"),
        "进度": st.column_config.TextColumn(width="small"),
        "原始评论": st.column_config.NumberColumn(width="small"),
        "有效评论": st.column_config.NumberColumn(width="small"),
        "报告": st.column_config.TextColumn(width="small"),
    })

    st.markdown(
        f"<div style='height:1px;background:var(--bop-divider);margin:20px 0 14px 0;'></div>",
        unsafe_allow_html=True)

    c_sel, c_switch, c_del, _ = st.columns([2, 1, 1, 4], gap="small")
    with c_sel:
        selected = st.selectbox("项目", options=projects, label_visibility="collapsed")
    with c_switch:
        if st.button("↔ 切换", help="切换到这个项目", width='stretch'):
            state.set_current_project(selected)
            st.rerun()
    with c_del:
        if st.button("🗑️ 删除", help="删除整个项目（不可逆）", width='stretch'):
            if st.session_state.get(f"confirm_delete_{selected}", False):
                state.delete_project(selected)
                st.success(f"已删除 {selected}", icon="✅")
                st.rerun()
            else:
                st.session_state[f"confirm_delete_{selected}"] = True
                st.warning("再点一次确认删除（不可恢复）", icon="⚠️")


# streamlit run 会以 __main__ 加载本文件；每次交互 rerun 整个脚本，
# 所以 main() 直接在模块级调用即可。
main()
