# DC Mode — 实现任务

## Phase 1: 数据访问抽象层重构

> **目标**：抽取出 `TerminalAccessor` 接口和 `DirectAccessor` 实现，BC 模式行为完全不变

- [ ] **T1.1** 新建 `app/accessor.py`，定义 `TerminalAccessor` 抽象基类
  - 4 个抽象方法：`check_online()`, `fetch_config()`, `fetch_all_configs()`, `write_config()`
- [ ] **T1.2** 实现 `DirectAccessor` 类
  - 将 `app/proxy.py` 中的 4 个函数逻辑平移进来
  - 保持 HTTP 超时、重试逻辑不变
- [ ] **T1.3** 修改 `app/proxy.py`，保留兼容导入
  - `from app.accessor import DirectAccessor`
  - 原有函数改为调用 `DirectAccessor` 实例，保持对外 API 不变
- [ ] **T1.4** 修改 `app/main.py`，通过依赖注入使用 accessor
  - 创建 `get_accessor()` 依赖函数（目前始终返回 `DirectAccessor`）
  - 所有路由 handler 改为 `accessor: TerminalAccessor = Depends(get_accessor)`
- [ ] **T1.5** 验证：启动 BC 模式，所有页面和 API 功能正常

## Phase 2: DC 模式配置与 BcRegistry

> **目标**：实现 DC 模式的配置体系和 BC Server 注册表

- [ ] **T2.1** 新建 `servers.yaml` 示例文件
  ```yaml
  mode: dc
  branches:
    - id: sz
      name: 深圳分行
      url: http://100.66.1.100:8300
  ```
- [ ] **T2.2** 新建 `app/bc_registry.py`，定义 `BcServer` 数据类
  - 字段：`id`, `name`, `url`, `terminals`（缓存列表）, `online`（BC 自身在线状态）
- [ ] **T2.3** 实现 `BcRegistry` 类
  - 构造函数：从 `servers.yaml` 加载 BC 列表
  - `refresh_all()`：`asyncio.Semaphore(20)` 并行请求所有 BC 的 `/api/terminals`
  - 构建 `{ip: BcServer}` 映射表
  - 聚合时给每条 terminal 加上 `branch_id`, `branch_name`, `bc_url`
  - 对失败的 BC 标记 `online=False`，已缓存数据保留
- [ ] **T2.4** 实现缓存刷新策略
  - 缓存有效期 30s
  - 后台 `asyncio.Task` 定时刷新
  - `url_for(ip)` 查询方法
- [ ] **T2.5** 验证：本地模拟 BC 端点，测试聚合逻辑正确性

## Phase 3: BcProxyAccessor 实现

> **目标**：DC 模式下的数据访问实现，通过 BC API 代理访问终端

- [ ] **T3.1** 在 `app/accessor.py` 中实现 `BcProxyAccessor` 类
  - 构造函数接收 `BcRegistry` 实例
  - `fetch_config(ip, port, key)` → `GET {bc_url}/api/proxy/{ip}/config/{key}`（不传 port）
  - `write_config(ip, port, key, data)` → `PUT {bc_url}/api/proxy/{ip}/config/{key}`
  - `fetch_all_configs(ip, port)` → `GET {bc_url}/api/proxy/{ip}/config`
  - `check_online(ip, port)` → 从 BcRegistry 缓存查询
- [ ] **T3.2** 添加超时和错误处理
  - BC 连接超时 10s（比直连 terminal 长，因为多一层代理）
  - BC 返回非 200 时透传错误信息
  - BC 离线时返回 `{"error": "BC server offline", "branch": "..."}`
- [ ] **T3.3** 验证：本地启动两个 BC 模式实例 + 一个 DC 模式实例，确认代理链路正常

## Phase 4: 启动入口与模式切换

> **目标**：`run.py` / `main.py` 支持模式切换

- [ ] **T4.1** 修改 `run.py`，增加模式检测
  ```python
  mode = os.getenv("KIOSK_MODE", "bc")
  if mode == "dc":
      os.environ["KIOSK_CONFIG_MODE"] = "dc"
  ```
- [ ] **T4.2** 修改 `app/main.py`，按模式初始化
  ```python
  _accessor: TerminalAccessor = None
  _bc_registry: BcRegistry = None

  def init_app():
      global _accessor, _bc_registry
      mode = os.getenv("KIOSK_CONFIG_MODE", "bc")
      if mode == "dc":
          _bc_registry = BcRegistry()
          _accessor = BcProxyAccessor(_bc_registry)
          # 启动后台刷新任务
          asyncio.create_task(_bc_registry.periodic_refresh())
      else:
          _accessor = DirectAccessor()

  def get_accessor() -> TerminalAccessor:
      return _accessor
  ```
- [ ] **T4.3** DC 模式首页 SSR 改造（`GET /` 路由）
  - DC 模式：首页只渲染 BC 聚合缓存数据，不做终端在线检测
  - BC 模式：保持现有 SSR 全量检测逻辑
- [ ] **T4.4** DC 模式 API 路由改造
  - `/api/proxy/{ip}/config/{key}` → 忽略 `port` 参数，通过 accessor 处理
  - `/api/batch` → DC 模式按 BC 分组后调用各 BC 的 `/api/batch`
  - `/api/terminals/add` → DC 模式返回 405
  - `/api/terminals/scan` → DC 模式返回 405
  - `/api/history/{ip}/{key}` / `/api/rollback/{ip}/{key}` → 转发到 BC
- [ ] **T4.5** 验证：分别以 BC 和 DC 模式启动，确认 API 行为符合预期

## Phase 5: 前端模板适配

> **目标**：DC 模式下的 Web UI 适配

- [ ] **T5.1** `index.html` DC 模式适配
  - 表格增加「分支」列（DC 模式渲染，BC 模式隐藏）
  - 「添加终端」「扫描子网」按钮：DC 模式隐藏
  - 健康度列：DC 模式简化为在线/离线图标
  - 模板通过 `{{ mode }}` 变量控制条件渲染
- [ ] **T5.2** `terminal.html` DC 模式适配
  - 标题增加分支信息
  - 其他功能不变（通过 proxy 链路透明转发）
- [ ] **T5.3** `batch.html` DC 模式适配
  - 终端列表按 `branch_name` 分组显示
  - 推送结果标注 BC 来源
  - 批量推送逻辑：按 BC 聚合 → 并行发送
- [ ] **T5.4** `compare.html` DC 模式适配
  - 终端选择列表标注分支信息
- [ ] **T5.5** 验证：DC 模式启动后浏览器功能走查（列表/详情/编辑/批量/对比/历史）

## Phase 6: 性能测试与部署

> **目标**：确认 100 台 BC 场景下的性能，输出部署文档

- [ ] **T6.1** 并发聚合性能测试
  - 本地启动 5 个 BC 模式实例（模拟 5 个分支）
  - 验证 DC 模式聚合耗时 < 3s
  - 验证 Semaphore(20) 限流生效
- [ ] **T6.2** 缓存命中测试
  - 验证第二次请求首页 < 200ms
  - 验证后台刷新不阻塞前台请求
- [ ] **T6.3** 前端压力测试
  - DC 模式首页渲染 3000 台终端（模拟数据）
  - 确认浏览器不卡顿，分页正常
- [ ] **T6.4** `servers.yaml` 配置 prod-ready
  - 预填 100 个 BC Server 的 URL
- [ ] **T6.5** 更新 `build-windows.ps1`
  - `--add-data servers.yaml;.` 加入打包
- [ ] **T6.6** 更新用户操作手册（`docs/用户操作手册.md`）
  - 增加 DC 模式部署章节
