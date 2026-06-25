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
BC_PROXY_TIMEOUT = 10.0  # DC → BC 代理超时（多一跳）


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


class BcProxyAccessor(TerminalAccessor):
    """通过 BC Server 代理访问终端 (DC 模式)

    DC → BC 网卡1 (DC 侧) → BC 网卡2 → Terminal

    port 参数在 DC 模式下被忽略 —— BC 内部已从 terminals.yaml 知道各终端 port。
    """

    def __init__(self, bc_registry):
        from app.bc_registry import BcRegistry
        self._registry: BcRegistry = bc_registry

    def _get_bc_url(self, ip: str) -> str:
        """查找 terminal 所属 BC 的 URL；未找到时抛出 ValueError"""
        url = self._registry.url_for(ip)
        if not url:
            raise ValueError(f"终端 {ip} 未在任何 BC Server 注册")
        return url

    async def check_online(self, ip: str, port: int = 8081) -> bool:
        """从 BcRegistry 缓存中查询终端在线状态"""
        for t in self._registry._aggregated_terminals:
            if t.get("ip") == ip:
                return t.get("online", False)
        # 终端不在缓存中 → 尝试强制刷新
        await self._registry.refresh_all()
        for t in self._registry._aggregated_terminals:
            if t.get("ip") == ip:
                return t.get("online", False)
        return False

    async def fetch_config(self, ip: str, port: int = 8081, config_key: Optional[str] = None) -> dict:
        """GET {bc_url}/api/proxy/{ip}/config/{key} → 透传返回"""
        try:
            bc_url = self._get_bc_url(ip)
        except ValueError as e:
            return {"error": str(e)}

        if config_key:
            url = f"{bc_url}/api/proxy/{ip}/config/{config_key}"
        else:
            url = f"{bc_url}/api/proxy/{ip}/config"

        try:
            async with httpx.AsyncClient(timeout=BC_PROXY_TIMEOUT) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    try:
                        return r.json()
                    except Exception:
                        return {"error": "无法解析配置", "detail": r.text[:200]}
                return {"error": f"BC 返回 HTTP {r.status_code}", "detail": r.text[:200]}
        except httpx.ConnectError:
            return {"error": "无法连接到 BC Server", "ip": ip}
        except httpx.TimeoutException:
            return {"error": "BC Server 超时", "ip": ip}

    async def fetch_all_configs(self, ip: str, port: int = 8081) -> dict:
        """GET {bc_url}/api/proxy/{ip}/config → 获取全部配置"""
        try:
            bc_url = self._get_bc_url(ip)
        except ValueError as e:
            return {"error": str(e)}

        try:
            async with httpx.AsyncClient(timeout=BC_PROXY_TIMEOUT) as client:
                r = await client.get(f"{bc_url}/api/proxy/{ip}/config")
                if r.status_code == 200:
                    try:
                        return r.json()
                    except Exception:
                        return {"error": "无法解析配置", "detail": r.text[:200]}
                return {"error": f"BC 返回 HTTP {r.status_code}", "detail": r.text[:200]}
        except httpx.ConnectError:
            return {"error": "无法连接到 BC Server", "ip": ip}
        except httpx.TimeoutException:
            return {"error": "BC Server 超时", "ip": ip}

    async def write_config(self, ip: str, port: int = 8081, config_key: str = "", data: dict = None) -> dict:
        """PUT {bc_url}/api/proxy/{ip}/config/{key} → 透传写入"""
        try:
            bc_url = self._get_bc_url(ip)
        except ValueError as e:
            return {"error": str(e)}

        if data is None:
            data = {}

        try:
            async with httpx.AsyncClient(timeout=BC_PROXY_TIMEOUT) as client:
                r = await client.put(
                    f"{bc_url}/api/proxy/{ip}/config/{config_key}",
                    json=data,
                )
                try:
                    return r.json()
                except Exception:
                    return {"status": r.status_code, "text": r.text}
        except httpx.ConnectError:
            return {"error": "无法连接到 BC Server", "ip": ip}
        except httpx.TimeoutException:
            return {"error": "BC Server 超时", "ip": ip}
