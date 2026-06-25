# DC Mode — 架构设计

## 网络拓扑

BC Server 有**两张网卡**，分属两个隔离的局域网：

```
┌──────────────────────────────────────────────────────────────────┐
│                       DC LAN (10.x.x.x / 总行网段)                │
│                                                                  │
│  ┌──────────────────┐                                            │
│  │   DC Server      │                                            │
│  │   mode=dc        │                                            │
│  └────────┬─────────┘                                            │
│           │ HTTP :8300                                            │
│  ┌────────┴─────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  BC Server (sz)  │    │ BC Server   │    │ BC Server   │     │
│  │  网卡1: DC侧IP   │    │ (bj)        │    │ (sh)        │     │
│  │  网卡2: Terminal侧│    │             │    │             │     │
│  └────────┬─────────┘    └──────┬──────┘    └──────┬──────┘     │
└───────────┼─────────────────────┼───────────────────┼────────────┘
            │                     │                   │
┌───────────┴── Terminal LAN ─────┴───────────────────┴────────────┐
│          (100.66.x.x / 终端网段)                                  │
│                                                                  │
│     Terminal ×30          Terminal ×50         Terminal ×40      │
│     config-serv :8081     config-serv :8081    config-serv :8081 │
└──────────────────────────────────────────────────────────────────┘
```

**关键约束**：DC 只能访问 BC 的 DC 侧网卡，无法直连 Terminal 网段。BC 是唯一的桥。

## 整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                      DC Server (总行)                        │
│                       DC LAN 内                              │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │           Kiosk Config Center (mode=dc)                 │  │
│  │           env: KIOSK_MODE=dc                            │  │
│  │                                                        │  │
│  │  servers.yaml                                           │  │
│  │    → BC 的 DC 侧地址 (10.x.x.x:8300)                    │  │
│  │                                                        │  │
│  │  BcProxyAccessor (TerminalAccessor 实现)                │  │
│  │                                                        │  │
│  │  GET /api/terminals  → 并行请求 100 个 BC → 聚合       │  │
│  │  GET /api/proxy/{ip}/config/{key}  → 转发到对应 BC     │  │
│  └──────────┬──────────┬──────────┬───────────────────────┘  │
│             │          │          │ httpx (Semaphore 20)     │
└─────────────┼──────────┼──────────┼──────────────────────────┘
              │          │          │
   ═══════════╪══════════╪══════════╪══  DC LAN (BC 网卡1)  ═══
              ▼          ▼          ▼
┌──────────────────────────────────────────────────────────────┐
│  BC Server (sz)            网卡1: 10.x.x.x (DC 侧)           │
│                            网卡2: 100.66.x.x (terminal 侧)   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Kiosk Config Center (mode=bc, :8300)                  │  │
│  │  terminals.yaml → terminal 侧 IP (100.66.x.x:8081)     │  │
│  └────────────────────┬───────────────────────────────────┘  │
└───────────────────────┼──────────────────────────────────────┘
                        │
   ═════════════════════╪══════  Terminal LAN (BC 网卡2)  ══════
                        │
           ┌────────────┼────────────┐
           ▼            ▼            ▼
       Terminal      Terminal      Terminal     (×30~50)
       100.66.x.x    100.66.x.x    100.66.x.x
       :8081         :8081         :8081
```

## 核心设计：数据访问抽象层

将连接终端 / BC Server 的逻辑统一为接口，两种模式各有一个实现：

```python
# app/accessor.py (新增)

from abc import ABC, abstractmethod

class TerminalAccessor(ABC):
    """终端数据访问抽象接口"""

    @abstractmethod
    async def check_online(self, ip: str, port: int = 8081) -> bool:
        """检测终端是否在线"""
        ...

    @abstractmethod
    async def fetch_config(self, ip: str, port: int, config_key: str) -> dict:
        """获取终端指定配置项"""
        ...

    @abstractmethod
    async def fetch_all_configs(self, ip: str, port: int) -> dict:
        """获取终端全部配置"""
        ...

    @abstractmethod
    async def write_config(self, ip: str, port: int, config_key: str, data: dict) -> dict:
        """写入终端配置"""
        ...
```

### DirectAccessor（BC 模式）

```python
# app/accessor.py

class DirectAccessor(TerminalAccessor):
    """直连终端 config-serv (现有 proxy.py 逻辑搬过来)
    
    通过 BC 网卡2 (terminal 侧) 直连 terminal :8081
    """

    async def check_online(self, ip, port=8081):
        # 现有 check_online() 逻辑（httpx 直连 terminal）

    async def fetch_config(self, ip, port, config_key):
        # 现有 fetch_config() 逻辑

    # ... 其余方法同现有 proxy.py
```

### BcProxyAccessor（DC 模式）

```python
# app/accessor.py

class BcProxyAccessor(TerminalAccessor):
    """通过 BC Server 代理访问终端 (DC 模式)
    
    DC → BC 网卡1 (DC 侧) → BC 网卡2 (terminal 侧) → terminal
    """

    def __init__(self, bc_registry: "BcRegistry"):
        self._registry = bc_registry

    def _get_bc_url(self, ip: str) -> str:
        """根据 terminal IP 查找其所属 BC Server 的 URL"""
        return self._registry.url_for(ip)

    async def fetch_config(self, ip, port, config_key):
        bc_url = self._get_bc_url(ip)
        # GET {bc_url}/api/proxy/{ip}/config/{config_key}
        # 注意：port 不需要 DC 关心，BC 内部已经知道

    async def write_config(self, ip, port, config_key, data):
        bc_url = self._get_bc_url(ip)
        # PUT {bc_url}/api/proxy/{ip}/config/{config_key}
```

**关键点**：`port` 在 DC 模式下不需要透传。BC Server 的 API 内部已经知道 terminal port（从 `terminals.yaml` 读取），DC 只需给出 terminal IP 即可。

## 配置设计

### BC 模式配置（`terminals.yaml`，不变）

IP 填 terminal 侧地址（BC 网卡2 可达）：

```yaml
mode: bc
terminals:
  - alias: bhs-4
    group: 管理服务器xxx
    ip: 100.66.5.26
    port: 8081
```

### DC 模式配置（新增 `servers.yaml`）

**url 填 BC 的 DC 侧地址**（DC 网卡可达的 IP）：

```yaml
mode: dc
branches:
  - id: sz
    name: 深圳分行
    url: http://10.66.1.100:8300     # ← BC 网卡1 的 IP (DC 侧)
  - id: bj
    name: 北京分行
    url: http://10.66.2.100:8300
  - id: sh
    name: 上海分行
    url: http://10.66.3.100:8300
```

### 启动方式

```bash
# BC 模式（默认）
python run.py

# DC 模式
$env:KIOSK_MODE="dc"; python run.py
```

## 数据模型

### BcRegistry（DC 模式核心）

```python
# app/bc_registry.py

@dataclass
class BcServer:
    id: str          # "sz"
    name: str        # "深圳分行"
    url: str         # BC 的 DC 侧地址 "http://10.66.1.100:8300"
    terminals: list  # 从该 BC 拉取的 terminal 列表（聚合后缓存）

class BcRegistry:
    servers: dict[str, BcServer]  # id → BcServer

    async def refresh_all(self) -> list[dict]:
        """并行请求所有 BC 的 /api/terminals，聚合全行终端列表"""
        sem = asyncio.Semaphore(20)
        # GC 请求 BC 的 DC 侧地址，BC 内部通过网卡2 连接 terminal
        # 返回 enriched terminals: [{"ip": ..., "branch_id": "sz", "bc_url": ..., ...}, ...]

    def url_for(self, ip: str) -> str:
        """根据 terminal IP 查找所属 BC 的 DC 侧 URL（从缓存查询）"""
```

### 聚合后的 Terminal 数据结构

```python
{
    "ip": "100.66.5.26",          # terminal 侧 IP (来自 BC 的 terminals.yaml)
    "alias": "bhs-4",
    "group": "管理服务器xxx",
    "port": 8081,
    "online": True,
    "config_version": "v2.3.1",
    # ↓ DC 模式新增字段
    "branch_id": "sz",
    "branch_name": "深圳分行",
    "bc_url": "http://10.66.1.100:8300",   # ← BC 的 DC 侧地址
}
```

## API 设计（DC 模式路由差异）

所有现有 API 路由保持不变，差异仅在 handler 内部根据 accessor 类型选择不同的实现路径。

### GET /api/terminals

| | BC 模式 | DC 模式 |
|---|---|---|
| 数据源 | 读 terminals.yaml + ping | 并行请求所有 BC 的 `/api/terminals` |
| 在线状态 | SSR 实时检测 | 复用 BC 返回的在线状态（BC 已检测过）|
| 缓存 | 无 | BcRegistry 缓存（后台定时刷新，默认 30s）|

DC 模式请求流：

```
GET /api/terminals (DC)
  → BcRegistry.refresh_all()
    → asyncio.gather(
        GET http://10.66.1.100:8300/api/terminals,   ← BC 网卡1 (DC 侧)
        GET http://10.66.2.100:8300/api/terminals,
        ... (Semaphore 20 限流)
      )
    → 聚合，加上 branch_id/bc_url
  → 返回全行 ~3000 台终端
```

### GET /api/proxy/{ip}/config/{key}

BC 模式保持不变。DC 模式转发到对应 BC：

```
GET /api/proxy/100.66.5.26/config/terminalFunction (DC 收到请求)
  → BcRegistry.url_for("100.66.5.26")
  → "http://10.66.1.100:8300"   ← BC 的 DC 侧地址
  → httpx GET http://10.66.1.100:8300/api/proxy/100.66.5.26/config/terminalFunction
  → BC 内部通过网卡2 (terminal 侧) 直连 100.66.5.26:8081
  → 透传返回
```

### POST /api/batch

DC 模式：按 BC 分组后并行推送：

```
POST /api/batch (DC)  {targets: {groups: ["深圳分行"]}, configs: {...}}
  → 过滤出"深圳分行"的所有 terminal
  → 它们都在 BC sz 上 → POST 10.66.1.100:8300/api/batch
  → (多 BC 时并行 gather)
```

### GET /api/history/{ip}/{key} / POST /api/rollback/{ip}/{key}

DC 模式转发到对应 BC（历史记录存在 BC 本地）。

## 性能策略（DC 模式 3000 台规模）

### 首页加载

| 策略 | 说明 |
|---|---|
| BC 聚合用 Semaphore(20) | 100 个 BC 分 5 轮 ≈ 5~10s |
| BC 层已检测在线状态 | DC 不重复检测，直接复用 BC 返回值 |
| 缓存 BC 聚合结果 | 首次加载后缓存 30s，后续请求直接返回缓存 |
| 后台定时刷新 | 独立 asyncio task，每 30s 拉一次所有 BC |
| 首页不展示健康度详情 | DC 首页只显示「在线/离线」，健康度改为按需加载 |
| 首页保留分页 | 每页 50 台，浏览器只渲染当前页 |

### 其他操作

| 操作 | 策略 |
|---|---|
| 单台配置读写 | 1 次 httpx 请求到对应 BC（低延迟）|
| 批量操作 | 按 BC 分组，并行推送到各 BC |
| 配置对比 | 按需请求对应 BC，不做预加载 |
| 扫描子网 | DC 模式不提供（由各 BC 自行管理）|

## 代码组织

```
app/
  accessor.py          ← 新增：TerminalAccessor 接口 + DirectAccessor + BcProxyAccessor
  main.py              ← 修改：路由 handler 改为注入 accessor
  proxy.py             ← 修改：原有逻辑移入 DirectAccessor，保留兼容导入
  terminals.py         ← 少量修改：Terminal 增加 branch_id/bc_url 字段
  bc_registry.py       ← 新增：DC 模式 BC Server 注册表
  templates/
    index.html         ← 修改：DC 模式首页适配（分支列、分页按钮）
  static/              ← 不变
servers.yaml           ← 新增：DC 模式配置
terminals.yaml         ← 不变
run.py                 ← 修改：启动时根据模式初始化 accessor
```

## 关键决策记录

1. **DC 无法直连 terminal** — BC 双网卡（DC LAN + Terminal LAN），DC 只能通过 BC 代理访问
2. **servers.yaml 用 DC 侧地址** — `url` 填 BC 网卡1 的 IP（DC 可达），BC 内部通过网卡2 连 terminal
3. **terminals.yaml 用 terminal 侧地址** — IP 填 100.66.x.x（BC 网卡2 可达），DC 不直接使用这个文件
4. **不增加 BC 端新 API** — 复用现有 `/api/terminals`、`/api/proxy/...`、`/api/batch`、`/api/history/...`
5. **port 不在 DC 模式 URL 中透传** — BC 的 proxy API 已封装 port，DC 不需要知道
6. **DC 不自建历史记录** — 历史/回滚转发到 BC，避免数据分散
7. **缓存策略用内存** — 不必上 Redis，asyncio task + dict 够用
8. **TerminalAccessor 用依赖注入** — FastAPI `Depends()` 注入 accessor 实例，路由层无 if-else
