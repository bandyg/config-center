# DC Mode — 功能规格

## 概述

Kiosk Config Center 支持两种运行模式：`bc`（分行模式，默认）和 `dc`（总行模式）。同一份代码、同一个可执行文件，通过配置切换模式。

---

## S1: 模式切换

### S1.1 环境变量切换
- `KIOSK_MODE` 环境变量：`bc`（默认）或 `dc`
- 启动时读取，决定加载哪份配置文件、注入哪个 Accessor

### S1.2 配置文件分离
- BC 模式：读 `terminals.yaml`（`mode: bc`, 终端列表）
- DC 模式：读 `servers.yaml`（`mode: dc`, BC Server 列表）
- 两种模式互斥，不同时加载两份配置

### S1.3 缺失配置的启动行为
- BC 模式找不到 `terminals.yaml` 时：正常启动，终端列表为空
- DC 模式找不到 `servers.yaml` 时：报错退出，提示缺少配置文件

---

## S2: TerminalAccessor 抽象层

### S2.1 接口定义
```python
class TerminalAccessor(ABC):
    async def check_online(ip, port) -> bool
    async def fetch_config(ip, port, config_key) -> dict
    async def fetch_all_configs(ip, port) -> dict
    async def write_config(ip, port, config_key, data) -> dict
```

### S2.2 DirectAccessor（BC 模式实现）
- 将现有 `app/proxy.py` 中的函数移入此类
- 直连 terminal 的 config-serv（`http://{ip}:{port}/api/terminalConfig/...`）
- 保持现有重试 + 超时逻辑

### S2.3 BcProxyAccessor（DC 模式实现）
- 将请求转发到 terminal 所属 BC Server 的对应 API
- `fetch_config(ip, port, key)` → `GET {bc_url}/api/proxy/{ip}/config/{key}`（**不传 port**）
- `write_config(ip, port, key, data)` → `PUT {bc_url}/api/proxy/{ip}/config/{key}`
- `fetch_all_configs(ip, port)` → `GET {bc_url}/api/proxy/{ip}/config`
- `check_online(ip, port)` → 从 `BcRegistry` 缓存中查询

### S2.4 依赖注入
- `app/main.py` 路由 handler 通过 FastAPI `Depends(get_accessor)` 获取 accessor 实例
- 不在路由层做 if-else 分支

---

## S3: BcRegistry（DC 模式 BC Server 注册表）

### S3.1 servers.yaml 格式
```yaml
mode: dc
branches:
  - id: sz
    name: 深圳分行
    url: http://100.66.1.100:8300
```

### S3.2 并行聚合
- `BcRegistry.refresh_all()` 并行请求所有 BC 的 `GET /api/terminals`
- 并发控制：`asyncio.Semaphore(20)`
- 100 台 BC Server 约 5~10 秒完成
- BC 响应失败时：将该 BC 标记为离线，已缓存的 terminal 仍显示但状态标记为 unknown

### S3.3 IP → BC 映射
- 聚合时构建 `{ip: BcServer}` 映射表
- `BcRegistry.url_for(ip)` 方法供 `BcProxyAccessor` 调用

### S3.4 缓存刷新
- 首次请求时触发全量聚合
- 后续请求在缓存有效期内（默认 30s）直接返回缓存
- 后台 `asyncio.Task` 每 30s 自动刷新
- 手动刷新按钮可强制立即刷新

---

## S4: DC 模式 API 改造

### S4.1 GET /api/terminals
- BC 模式：不变
- DC 模式：调用 `BcRegistry.refresh_all()` 获取聚合终端列表
- 返回的每条 terminal 额外包含 `branch_id`、`branch_name`、`bc_url`
- 返回字段 `port` 仅在 BC 模式返回，DC 模式不暴露

### S4.2 GET/PUT /api/proxy/{ip}/config/{key}
- BC 模式：不变
- DC 模式：通过 `BcProxyAccessor` 转发到对应 BC
- URL 中不需要 port 参数（DC 模式下忽略 `?port=` query param）

### S4.3 POST /api/batch
- DC 模式：按 BC 分组 → 并行推送到各 BC 的 `/api/batch`
- 返回结果合并，标明每个操作的 BC 来源

### S4.4 GET /api/compare
- DC 模式：每个 terminal 通过其所属 BC 获取配置

### S4.5 GET /api/history/{ip}/{key} / POST /api/rollback/{ip}/{key}
- DC 模式：转发到 terminal 所属 BC

### S4.6 POST /api/terminals/add
- DC 模式：不支持（终端归属由各 BC 自行管理，返回 405 或前端隐藏按钮）

### S4.7 POST /api/terminals/scan
- DC 模式：不支持（扫描由各 BC 自行执行）

### S4.8 GET/POST /api/shutdown
- 两种模式均支持

---

## S5: DC 模式前端适配

### S5.1 首页终端列表
- 增加「分支」列，显示 `branch_name`
- 健康度列在 DC 模式下只显示在线/离线，不显示评分详情
- 分页默认每页 50 条
- 「添加终端」「扫描子网」按钮在 DC 模式下隐藏

### S5.2 终端详情页
- 页面标题增加分支信息：`深圳分行 — bhs-4`
- 功能不变：查看配置、编辑配置、历史回滚（均通过 BC proxy 转发）
- 全屏编辑、Diff 预览等功能不变

### S5.3 批量操作页
- 终端列表按分支分组显示
- 选择逻辑不变（按分支/filter/分组勾选）

### S5.4 配置对比页
- 终端列表标注分支信息
- 对比逻辑不变

---

## S6: 性能要求

| 指标 | 目标 |
|---|---|
| DC 首页首次加载 | < 15s（含 100 个 BC 聚合）|
| DC 首页缓存命中 | < 200ms |
| 单台配置读取（DC 模式）| < 3s（DC → BC → terminal）|
| 单台配置写入（DC 模式）| < 3s |
| 并发 terminal 检测（BC 模式）| 不变，保持现有 < 5s |
| 100 台 BC 并行聚合 | < 10s |

---

## S7: 向后兼容

- BC 模式行为与当前版本完全一致
- `terminals.yaml` 格式不变
- 现有 API 路径不变
- 现有 Web UI 在 BC 模式下不变
- `run.py` 默认模式为 `bc`，不加环境变量时行为不变
