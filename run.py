"""Kiosk Config Center — 启动入口（也用于 PyInstaller 打包）"""

import sys
import webbrowser
import uvicorn
from pathlib import Path

# PyInstaller 打包后模板路径处理
if getattr(sys, "frozen", False):
    # 打包为 exe 时，模板在 _MEIPASS 目录下
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent / "app"

# 告诉 FastAPI 模板位置（通过环境变量或直接修改 main.py 行为）
import os
os.environ["KIOSK_CONFIG_BASE_DIR"] = str(BASE_DIR)


def main():
    host = os.getenv("KIOSK_HOST", "127.0.0.1")
    port = int(os.getenv("KIOSK_PORT", "8300"))
    open_browser = os.getenv("KIOSK_OPEN_BROWSER", "1") == "1"

    print(f"🖥  Kiosk Config Center v1.0")
    print(f"📡  http://{host}:{port}/")
    print("⏹  Ctrl+C 停止服务")

    if open_browser:
        webbrowser.open(f"http://{host}:{port}/")

    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
