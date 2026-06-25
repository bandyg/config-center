"""终端数据访问抽象层

TerminalAccessor 抽象接口 → DirectAccessor (BC) / BcProxyAccessor (DC)
"""

import json
import asyncio
from abc import ABC, abstractmethod
from urllib.parse import quote
from typing import Optional

import httpx

TIMEOUT = 5.0
MAX_RETRIES = 2


class TerminalAccessor(ABC):
    """终端数据访问抽象接口"""

    @abstractmethod
    async def check_online(self, ip: str, port: int = 8081) -> bool:
        """检测终端是否在线"""
        ...

    @abstractmethod
    async def fetch_config(self, ip: str, port: int = 8081, config_key: Optional[str] = None) -> dict:
        """获取终端配置（指定 key 或全部）"""
        ...

    @abstractmethod
    async def fetch_all_configs(self, ip: str, port: int = 8081) -> dict:
        """获取终端所有已知配置项"""
        ...

    @abstractmethod
    async def write_config(self, ip: str, port: int = 8081, config_key: str = "", data: dict = None) -> dict:
        """写入终端配置"""
        ...


class DirectAccessor(TerminalAccessor):
    """直连终端 config-serv (BC 模式)"""

    async def check_online(self, ip: str, port: int = 8081) -> bool:
        url = f"http://{ip}:{port}/"
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    r = await client.get(url)
                    return r.status_code == 200
            except Exception:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1)
                    continue
                return False
        return False

    async def fetch_config(self, ip: str, port: int = 8081, config_key: Optional[str] = None) -> dict:
        if config_key:
            url = f"http://{ip}:{port}/api/terminalConfig/get/{config_key}"
        else:
            url = f"http://{ip}:{port}/api/terminalConfig/get/"

        for attempt in range(MAX_RETRIES + 1):
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        try:
                            return r.json()
                        except Exception:
                            return {"error": "无法解析配置（配置项可能不存在或返回非 JSON）", "detail": r.text[:200]}
                    return {"error": f"HTTP {r.status_code}", "detail": r.text[:200]}
                except httpx.ConnectError:
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(1)
                        continue
                    return {"error": "Connection refused", "ip": ip, "port": port}
                except httpx.TimeoutException:
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(1)
                        continue
                    return {"error": "Timeout", "ip": ip, "port": port}

    async def fetch_all_configs(self, ip: str, port: int = 8081) -> dict:
        config_keys = [
            "terminalFunction", "bcConfig", "supervisorConfig", "serviceConfig",
            "infoConfig", "webConfig", "posterConfig", "internalParam",
            "transactionConfig", "ctcConfig", "customer",
        ]
        result = {}
        for key in config_keys:
            data = await self.fetch_config(ip, port, key)
            if "error" not in data:
                result[key] = data
        return result

    async def write_config(self, ip: str, port: int = 8081, config_key: str = "", data: dict = None) -> dict:
        if data is None:
            data = {}
        encoded_val = quote(json.dumps(data), safe="")
        url = f"http://{ip}:{port}/api/terminalConfig/set/{config_key}/{encoded_val}"

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                r = await client.put(url)
                return {"status": r.status_code, "text": r.text}
            except httpx.ConnectError:
                return {"error": "Connection refused"}
            except httpx.TimeoutException:
                return {"error": "Timeout"}
