"""DC 模式 BC Server 注册表

从 servers.yaml 加载所有 BC Server，并行聚合各 BC 的终端列表，
维护 IP→BC 映射表和缓存。
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx
import yaml


SERVERS_FILE = Path(__file__).parent.parent / "servers.yaml"

CACHE_TTL = 30.0  # 缓存有效期（秒）
MAX_CONCURRENT = 20  # 并行请求 BC 的最大并发数
BC_REQUEST_TIMEOUT = 10.0  # 请求 BC 的超时时间


@dataclass
class BcServer:
    """单个 BC Server 信息"""
    id: str
    name: str
    url: str                     # DC 侧可达地址
    online: bool = True
    terminals: list[dict] = field(default_factory=list)  # 该 BC 管辖的终端列表（缓存）


class BcRegistry:
    """DC 模式 BC Server 注册表，负责数据聚合与缓存"""

    def __init__(self, servers_file: Path = SERVERS_FILE):
        self._servers: dict[str, BcServer] = {}
        self._ip_map: dict[str, str] = {}                      # IP → bc_server.id
        self._aggregated_terminals: list[dict] = []             # 全行终端列表（带 branch 信息）
        self._last_refresh: float = 0
        self._refreshing: bool = False
        self._refresh_lock = asyncio.Lock()
        self._background_task: Optional[asyncio.Task] = None
        self._load_servers(servers_file)

    # ── 配置加载 ───────────────────────────────────────

    def _load_servers(self, servers_file: Path):
        if not servers_file.exists():
            raise FileNotFoundError(
                f"DC 模式需要 servers.yaml，但未找到: {servers_file}\n"
                f"请创建 servers.yaml 并列出各 BC Server 地址"
            )
        with open(servers_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data.get("mode") != "dc":
            raise ValueError("servers.yaml 中 mode 必须为 'dc'")
        for b in data.get("branches", []):
            srv = BcServer(
                id=b["id"],
                name=b.get("name", b["id"]),
                url=b["url"].rstrip("/"),
            )
            self._servers[srv.id] = srv

    @property
    def servers(self) -> dict[str, BcServer]:
        return self._servers

    @property
    def total_terminals(self) -> int:
        return len(self._aggregated_terminals)

    @property
    def cache_valid(self) -> bool:
        return (time.time() - self._last_refresh) < CACHE_TTL

    # ── 数据聚合 ───────────────────────────────────────

    async def refresh_all(self) -> list[dict]:
        """并行请求所有 BC 的 /api/terminals，聚合全行终端列表。

        Semaphore(20) 控制并发，100 台 BC 约 5~10 秒完成。
        失败的 BC 标记为 offline，该 BC 的旧缓存保留。
        """
        async with self._refresh_lock:
            if self._refreshing:
                # 正在刷新中，等待完成
                while self._refreshing:
                    await asyncio.sleep(0.1)
                return self._aggregated_terminals
            self._refreshing = True

        try:
            sem = asyncio.Semaphore(MAX_CONCURRENT)
            all_terminals: list[dict] = []

            async def _fetch_one(srv: BcServer):
                async with sem:
                    try:
                        async with httpx.AsyncClient(timeout=BC_REQUEST_TIMEOUT) as client:
                            r = await client.get(f"{srv.url}/api/terminals")
                            if r.status_code == 200:
                                terminals = r.json()
                                srv.online = True
                                # 给每条 terminal 加上 branch 信息
                                enriched = []
                                for t in terminals:
                                    enriched.append({
                                        **t,
                                        "branch_id": srv.id,
                                        "branch_name": srv.name,
                                        "bc_url": srv.url,
                                    })
                                srv.terminals = enriched
                                return enriched
                            else:
                                srv.online = False
                                return srv.terminals  # 返回旧缓存
                    except Exception:
                        srv.online = False
                        return srv.terminals  # 返回旧缓存

            tasks = [_fetch_one(srv) for srv in self._servers.values()]
            results = await asyncio.gather(*tasks)

            # 合并结果并重建 IP 映射
            all_terminals = []
            new_ip_map: dict[str, str] = {}
            for terminal_list in results:
                all_terminals.extend(terminal_list)
                for t in terminal_list:
                    new_ip_map[t["ip"]] = t["branch_id"]

            self._aggregated_terminals = all_terminals
            self._ip_map = new_ip_map
            self._last_refresh = time.time()
            return all_terminals

        finally:
            self._refreshing = False

    # ── 查询接口 ───────────────────────────────────────

    def url_for(self, ip: str) -> Optional[str]:
        """根据 terminal IP 查找其所属 BC Server 的 URL"""
        bc_id = self._ip_map.get(ip)
        if bc_id and bc_id in self._servers:
            return self._servers[bc_id].url
        return None

    def get_terminals(self, force_refresh: bool = False) -> list[dict]:
        """获取聚合后的终端列表（优先返回缓存）"""
        if force_refresh or not self.cache_valid:
            # 触发异步刷新（不等待）
            if not self._refreshing:
                asyncio.ensure_future(self.refresh_all())
        return self._aggregated_terminals

    # ── 后台刷新 ───────────────────────────────────────

    async def _periodic_refresh(self):
        """后台定时刷新任务（每 CACHE_TTL 秒）"""
        while True:
            await asyncio.sleep(CACHE_TTL)
            try:
                await self.refresh_all()
            except Exception:
                pass  # 后台刷新静默失败

    def start_background_refresh(self):
        """启动后台定时刷新任务"""
        if self._background_task is None or self._background_task.done():
            self._background_task = asyncio.ensure_future(self._periodic_refresh())

    def stop_background_refresh(self):
        """停止后台定时刷新任务"""
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
