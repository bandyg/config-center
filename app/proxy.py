"""代理 httpx 请求到各终端的 config-serv"""

import json
import asyncio
from urllib.parse import quote

import httpx
from typing import Optional

TIMEOUT = 5.0  # 终端连接超时
MAX_RETRIES = 2  # 最大重试次数


async def check_online(ip: str, port: int = 8081) -> bool:
    """检查终端 config-serv 是否在线（带重试）"""
    url = f"http://{ip}:{port}/"
    for attempt in range(MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                r = await client.get(url)
                return r.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError, httpx.RequestError, OSError, Exception):
            if attempt < MAX_RETRIES:
                await asyncio.sleep(1)
                continue
            return False
    return False


async def fetch_config(ip: str, port: int = 8081, config_key: Optional[str] = None) -> dict:
    """获取终端配置，可指定某配置项（带重试）"""
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


async def write_config(ip: str, port: int, config_key: str, data: dict) -> dict:
    """写入终端配置 (config-serv 的 set API 把 JSON 值放在 URL 路径中)"""
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


async def fetch_all_configs(ip: str, port: int = 8081) -> dict:
    """获取终端所有配置 (遍历已知配置项)"""
    config_keys = [
        "terminalFunction", "bcConfig", "supervisorConfig", "serviceConfig",
        "infoConfig", "webConfig", "posterConfig", "internalParam",
        "transactionConfig", "ctcConfig", "customer",
    ]
    result = {}
    for key in config_keys:
        data = await fetch_config(ip, port, key)
        if "error" not in data:
            result[key] = data
    return result
