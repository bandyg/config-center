# DC Mode — 同一程序支持分支/总行双模式

## Why

当前 Kiosk Config Center 仅支持**分行（BC）模式**：每台 BC Server 上单独部署一份，管理本分行内 30~50 台 Kiosk 终端。总行（DC）运维人员想全局查看或修改配置时，需要逐个登录各 BC Server，无法统一管理。

全行约有 **100 台 BC Server**，管辖 **~3000 台终端**。需要在 DC Server 上也能运行 Kiosk Config Center，实现对全行所有终端的集中管理。

## What Changes

将 Kiosk Config Center 改造为**一个程序、两种模式**，通过环境变量 `KIOSK_MODE` 切换：

### 新增设施

1. **数据访问抽象层 (`TerminalAccessor`)** — 将连接终端的逻辑抽象为接口，BC 模式下直连 terminal config-serv，DC 模式下代理到 BC Server 的 API
2. **DC 模式配置 (`servers.yaml`)** — 注册所有 BC Server 的地址和分支信息
3. **BcProxyAccessor** — DC 模式下的数据访问实现，通过 httpx 并行调用各 BC Server 的现有 API
4. **启动入口改造 (`run.py` / `main.py`)** — 根据 `KIOSK_MODE` 环境变量加载不同配置、注入不同 Accessor
5. **DC 模式首页** — 适配 3000 台规模的分页/延迟加载策略

### 受影响的现有组件

- `app/proxy.py` — 抽取出 `DirectAccessor` 实现
- `app/terminals.py` — Terminal 数据结构增加 `branch_id`/`bc_url` 字段
- `app/main.py` — API 路由改为依赖注入 TerminalAccessor
- `run.py` — 启动逻辑按模式分支
- `app/templates/index.html` — DC 模式首页性能优化

### 不做的

- 不在 BC Server 上加装新服务或新 API（复用现有 API）
- 不改变 terminal 端的 config-serv
- DC 不自建配置历史存储（转发到 BC 的历史 API）
- 不实现 DC ↔ BC 间的认证（后续可加）
