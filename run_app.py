# -*- coding: utf-8 -*-
"""启动 Streamlit 前端。

用法：
    python run_app.py            # 默认 8501 端口，自动打开浏览器
    python run_app.py --port 8600
    或：streamlit run app/home.py
"""
import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description="启动 BiliOpinion Streamlit 前端")
    ap.add_argument("--port", type=int, default=8501, help="监听端口（默认 8501）")
    ap.add_argument("--headless", action="store_true",
                    help="不自动打开浏览器（服务器/远程环境用）")
    args = ap.parse_args()

    app_py = REPO_ROOT / "app" / "home.py"
    if not app_py.exists():
        print(f"找不到 {app_py}", file=sys.stderr)
        return 1

    try:
        import streamlit  # noqa: F401
    except ImportError:
        print("未安装 streamlit。请先运行：pip install -r requirements.txt",
              file=sys.stderr)
        return 1

    cmd = [sys.executable, "-m", "streamlit", "run", str(app_py),
           f"--server.headless={'true' if args.headless else 'false'}",
           f"--server.port={args.port}",
           "--server.enableXsrfProtection=false",
           "--server.enableCORS=false",
           "--browser.gatherUsageStats=false"]
    print(f"启动中… 浏览器打开 http://localhost:{args.port}")
    try:
        return subprocess.call(cmd, cwd=str(REPO_ROOT))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
