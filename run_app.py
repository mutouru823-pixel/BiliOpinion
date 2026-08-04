# -*- coding: utf-8 -*-
"""启动 Streamlit 前端。

用法：
    python run_app.py
    或：streamlit run app/app.py
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def main() -> int:
    app_py = REPO_ROOT / "app" / "home.py"
    if not app_py.exists():
        print(f"找不到 {app_py}", file=sys.stderr)
        return 1
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_py),
           "--server.headless=true",
           "--server.port=8501",
           "--server.enableXsrfProtection=false",
           "--server.enableCORS=false",
           "--browser.gatherUsageStats=false"]
    try:
        return subprocess.call(cmd, cwd=str(REPO_ROOT))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
