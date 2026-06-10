# Kiosk 配置管理中心 — 实现任务

## Phase 1: 项目脚手架 + 终端列表 (可运行验证)

- [ ] 创建 FastAPI 项目结构 `app/main.py`, `app/terminals.py`, `app/proxy.py`
- [ ] 创建 `terminals.yaml` 配置文件（先加当前这台机器的 config-serv）
- [ ] 实现 `GET /api/terminals` — 读取 YAML + ping 在线状态
- [ ] 实现终端列表页面 `GET /` — HTML 表格，在线/离线指示灯
- [ ] 验证：浏览器打开能看到本机 config-serv 在线

## Phase 2: 配置读取代理 (可运行验证)

- [ ] 实现 `GET /api/proxy/{ip}/config` — httpx 代理到终端的 config-serv
- [ ] 实现 `GET /api/proxy/{ip}/config/{key}` — 读取指定配置项
- [ ] 实现终端详情页面 `GET /terminal/{ip}` — 展示所有配置（JSON 格式化）
- [ ] 验证：浏览器打开能看到本机 config-serv 的配置数据

## Phase 3: 配置写入 + 批量操作 (可运行验证)

- [ ] 实现 `PUT /api/proxy/{ip}/config/{key}` — 单台写入
- [ ] 实现 `POST /api/batch` — 批量写入（ips / groups 选择）
- [ ] 实现配置编辑页面 — 表单修改 + 提交
- [ ] 实现批量操作页面 — 选择终端/分组 → 修改配置 → 推送
- [ ] 验证：修改本机 config-serv 的某个值，确认生效

## Phase 4: 配置对比 (可运行验证)

- [ ] 实现 `GET /api/compare` — 多终端配置对比 API
- [ ] 实现对比页面 — 选择终端 → 差异高亮显示
- [ ] 验证：添加两台不同终端 → 对比能看到差异

## Phase 5: 完善和部署

- [ ] 添加 systemd 服务文件
- [ ] 错误处理和超时控制
- [ ] 操作日志记录（可选，可复用 log-serv）
