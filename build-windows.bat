@echo off
REM Kiosk Config Center — Windows 打包脚本
REM 1. 安装 Python 3.11+
REM 2. 双击运行本脚本

echo ========================================
echo  Kiosk Config Center — Windows 打包
echo ========================================

echo 1/4 检查 Python...
python --version || echo "请先安装 Python 3.11+" && exit /b 1

echo 2/4 创建虚拟环境...
if not exist venv (
    python -m venv venv
)

echo 3/4 安装依赖...
call venv\Scripts\activate.bat
pip install -r requirements.txt
pip install pyinstaller

echo 4/4 打包 EXE...
pyinstaller kiosk-config-center.spec --clean

echo.
echo ========================================
echo  ✅ 打包完成！
echo  输出目录: dist\KioskConfigCenter.exe
echo  双击运行即可启动配置管理中心
echo ========================================

pause
