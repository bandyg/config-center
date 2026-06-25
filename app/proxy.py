"""代理 httpx 请求到各终端的 config-serv（兼容层）

现有逻辑已迁移到 app.accessor.DirectAccessor。
此文件保留模块级函数接口以向后兼容。
新增代码应直接从 app.accessor 导入 TerminalAccessor。
"""

from typing import Optional
from app.accessor import DirectAccessor, TIMEOUT, MAX_RETRIES  # noqa: F401

_da = DirectAccessor()


async def check_online(ip: str, port: int = 8081) -> bool:
    return await _da.check_online(ip, port)


async def fetch_config(ip: str, port: int = 8081, config_key: Optional[str] = None) -> dict:
    return await _da.fetch_config(ip, port, config_key)


async def write_config(ip: str, port: int = 8081, config_key: str = "", data: dict = None) -> dict:
    return await _da.write_config(ip, port, config_key, data)


async def fetch_all_configs(ip: str, port: int = 8081) -> dict:
    return await _da.fetch_all_configs(ip, port)
