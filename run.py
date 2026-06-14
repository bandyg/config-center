"""Kiosk Config Center — 启动入口（也用于 PyInstaller 打包）"""

import socket
import sys
import traceback
import webbrowser
from pathlib import Path

# PyInstaller 打包后模板路径处理
# --add-data "app/templates;app/templates" 让 templates 落在 _MEIPASS/app/templates
# 所以 BASE_DIR 必须是 _MEIPASS / "app" 而不是 _MEIPASS
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS) / "app"
else:
    BASE_DIR = Path(__file__).parent / "app"

# 告诉 FastAPI 模板位置
import os
os.environ["KIOSK_CONFIG_BASE_DIR"] = str(BASE_DIR)


def is_port_free(host, port):
    """检测端口是否可绑定。返回 (ok, error_msg)。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
        return True, None
    except OSError as e:
        return False, str(e)
    finally:
        s.close()


def show_error_and_pause(msg):
    """PyInstaller --console 模式下，让错误信息停留 30 秒，让用户看清"""
    print("\n" + "=" * 60, flush=True)
    print(msg, flush=True)
    print("=" * 60, flush=True)
    print("窗口将在 30 秒后自动关闭，或按回车立即退出...", flush=True)
    try:
        import msvcrt
        # Windows: 等 30 秒或键盘输入
        for _ in range(300):
            if msvcrt.kbhit():
                msvcrt.getch()
                break
            import time
            time.sleep(0.1)
    except Exception:
        try:
            input()
        except Exception:
            pass


def main():
    host = os.getenv("KIOSK_HOST", "127.0.0.1")
    port = int(os.getenv("KIOSK_PORT", "8300"))
    open_browser = os.getenv("KIOSK_OPEN_BROWSER", "1") == "1"

    print(f"🖥  Kiosk Config Center v1.0")
    print(f"📡  http://{host}:{port}/")
    print("⏹  Ctrl+C 停止服务")

    # 预检端口是否空闲
    ok, err = is_port_free(host, port)
    if not ok:
        msg = (
            f"❌ 端口 {port} 已被占用，无法启动！\n"
            f"\n"
            f"原始错误：{err}\n"
            f"\n"
            f"可能的原因：\n"
            f"  1. 上一个 EXE 没退干净（请到任务管理器结束 KioskConfigCenter.exe）\n"
            f"  2. 其他程序正在使用端口 {port}\n"
            f"\n"
            f"处理方法：\n"
            f"  - 打开任务管理器 → 结束 KioskConfigCenter.exe → 重新双击 EXE\n"
            f"  - 或运行命令：netstat -ano | findstr :{port} 找到 PID 后 taskkill /F /PID <PID>"
        )
        show_error_and_pause(msg)
        return 1

    if open_browser:
        import threading
        import time
        def _open_browser():
            time.sleep(1.2)
            try:
                webbrowser.open(f"http://{host}:{port}/")
            except Exception:
                pass
        threading.Thread(target=_open_browser, daemon=True).start()

    try:
        from app.main import app as fastapi_app  # noqa: F401
        import uvicorn
        uvicorn.run(
            fastapi_app,
            host=host,
            port=port,
            reload=False,
            log_level="info",
        )
    except OSError as e:
        if "address already in use" in str(e).lower() or "10048" in str(e):
            show_error_and_pause(
                f"❌ 端口 {port} 启动后被占用（race condition）：{e}\n"
                f"请检查任务管理器中的 KioskConfigCenter.exe 残留进程并结束它们。"
            )
        else:
            show_error_and_pause(f"❌ 启动失败: {e}\n{traceback.format_exc()}")
        return 1
    except KeyboardInterrupt:
        print("\n👋 服务已停止", flush=True)
        return 0
    except SystemExit as e:
        if e.code not in (0, None):
            show_error_and_pause(f"❌ uvicorn 异常退出 (code={e.code})")
        return e.code or 0
    except Exception as e:
        show_error_and_pause(f"❌ 启动失败: {e}\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
