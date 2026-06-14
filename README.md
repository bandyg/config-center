# Kiosk Config Center — 配置管理中心

集中管理所有 Kiosk 终端的配置。通过代理层统一读写各终端上 `config-serv` 的 REST API。

---

## 架构概览

```
用户浏览器
     │  http://<host>:8300/
     ▼
┌─────────────────────────────────────┐
│      Config Center (FastAPI)        │
│  端口 8300                          │
│                                     │
│  ┌───────────────────────────────┐  │
│  │  Web UI (Jinja2 模板)         │  │
│  │  - 终端列表仪表盘              │  │
│  │  - 配置详情 + 在线编辑         │  │
│  │  - 批量操作（分组/多选）       │  │
│  │  - 配置对比（差异高亮）        │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │  代理层 (httpx)               │  │
│  │  GET/PUT → 各终端 config-serv │  │
│  └───────────────────────────────┘  │
└──────────────┬──────────────────────┘
               │ HTTP (内网/Tailscale)
     ┌─────────┴─────────┐
     │                   │
 T1 (:8081)        T2 (:8081)      ... TN
(config-serv)    (config-serv)
```

## 组件关系

| 组件 | 技术 | 位置 | 作用 |
|------|------|------|------|
| **Config Center** (本项目) | Python FastAPI | `~/services/kiosk-config-center/` | 集中管理面板 + 代理层 |
| **config-serv** | TypeScript/Node.js | 每台终端上运行 | 实际配置服务（Config Center 通过 HTTP 代理读写） |
| **kiosk-next** | Angular + Electron | `~/services/kiosk-next/` | Electron 客户端（另一项目） |

> Config Center 是 **代理/管理面板**，本身不存储配置。配置读写都代理到各终端的 config-serv。

---

## 快速启动

### 开发模式

```bash
cd ~/services/kiosk-config-center
source venv/bin/activate
python run.py
# 访问 http://127.0.0.1:8300/
```

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KIOSK_HOST` | `127.0.0.1` | 监听地址 |
| `KIOSK_PORT` | `8300` | 监听端口 |
| `KIOSK_OPEN_BROWSER` | `1` | 启动时自动打开浏览器（设为 `0` 禁用） |

---

## 项目结构

```
kiosk-config-center/
├── app/
│   ├── main.py              # FastAPI 主入口（API + 页面路由）
│   ├── proxy.py             # httpx 代理层（转发到 config-serv，含重试机制）
│   ├── terminals.py         # YAML 终端列表加载
│   ├── history.py           # 配置修改历史记录与回滚管理
│   ├── static/
│   │   ├── css/app.css      # 增强 UI 样式（树形浏览、Diff 着色、骨架屏等）
│   │   └── js/app.js        # 前端工具函数（预留）
│   ├── templates/
│   │   ├── index.html       # 终端列表仪表盘（含健康度、分页）
│   │   ├── terminal.html    # 配置详情（CodeMirror 编辑器、树形浏览、Diff 预览）
│   │   ├── batch.html       # 批量操作（分组筛选、进度条、结果增强）
│   │   ├── compare.html     # 配置对比（多配置项 Tab、CSV/Markdown 导出）
│   │   └── test.html        # 基础验证页
│   └── __init__.py
├── run.py                   # 启动入口（PyInstaller 兼容）
├── terminals.yaml           # 终端配置文件
├── requirements.txt         # Python 依赖
├── .gitignore
├── .github/workflows/
│   └── build-exe.yml        # GitHub Actions → 自动打包 Windows EXE
├── kiosk-config-center.spec # PyInstaller 打包配置
├── build-windows.bat        # Windows 本地打包脚本
├── docs/
│   ├── 用户操作手册.md       # 面向最终用户的操作指南
│   ├── 测试说明文档.md       # 面向测试人员的全面测试用例
│   ├── PM-需求评审材料.md    # 产品经理评审材料
│   ├── 项目PR方案.md         # 项目 PR 方案与迭代规划
│   └── 项目实现计划.md       # 完整 WBS 任务分解与甘特图
├── scripts/
│   ├── install-service.ps1  # Windows 服务安装/卸载脚本
│   └── download-static-assets.ps1  # CDN 资源离线下载脚本
└── openspec/                # OpenSpec 项目文档
```

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/terminals` | 终端列表（含在线状态 + 配置版本号） |
| `GET` | `/api/proxy/{ip}/config` | 获取终端全部配置 |
| `GET` | `/api/proxy/{ip}/config/{key}` | 获取指定配置项 |
| `PUT` | `/api/proxy/{ip}/config/{key}` | 写入指定配置项（自动记录修改历史） |
| `POST` | `/api/batch` | 批量写入（支持 ips/groups，自动记录历史） |
| `GET` | `/api/compare` | 多终端配置对比（支持多配置项） |
| `GET` | `/api/history/{ip}/{key}` | 获取配置修改历史记录 |
| `POST` | `/api/rollback/{ip}/{key}` | 回滚配置到历史版本 |
| `GET` | `/api/health` | 获取各终端健康度评分 |

### 批量写入示例

```json
POST /api/batch
{
  "targets": {
    "ips": ["10.202.1.1", "10.202.1.2"],
    "groups": ["分店A"]
  },
  "configs": {
    "serviceConfig": { "demoMode": false }
  }
}
```

### 对比示例

```
GET /api/compare?ips=10.0.0.1,10.0.0.2&keys=terminalFunction,serviceConfig
```

### 配置历史示例

```
GET /api/history/10.0.0.1/serviceConfig
```

### 健康度示例

```
GET /api/health
```

---

## 终端配置 (terminals.yaml)

```yaml
terminals:
  - ip: 127.0.0.1
    alias: "本机 (bhs-4)"
    group: "管理服务器"
    port: 8081
```

**字段说明：**
- `ip` — 终端 IP 地址（config-serv 所在机器）
- `alias` — 显示别名
- `group` — 分组名（用于批量操作筛选）
- `port` — config-serv 端口（默认 8081）

---

## 打包成 EXE

### 方式一：GitHub Actions（推荐）

1. 推送到 GitHub → 自动触发 Actions
2. 去 https://github.com/bandyg/config-center/actions 下载
3. 解压 `KioskConfigCenter-Windows.zip`，得到 `KioskConfigCenter.exe`

### 方式二：本地 Windows 打包

1. 装 Python 3.11+
2. 双击 `build-windows.bat`
3. 输出在 `dist/KioskConfigCenter.exe`

### 打包原理

- 使用 **PyInstaller** 将 FastAPI + Uvicorn + Jinja2 全部打进单文件
- 模板和 YAML 配置文件一并打包
- 双击 exe → 启动 Uvicorn → 自动打开浏览器
- **目标机器不需要装 Python**，exe 自包含

### 打包配置

- `kiosk-config-center.spec` — PyInstaller 配置（定义 data files、hidden imports、排除项）
- `run.py` — 启动入口，已处理 PyInstaller 的 `sys._MEIPASS` 路径
- `app/main.py` — 通过 `KIOSK_CONFIG_BASE_DIR` 环境变量获取打包后的模板路径

---

## 开发说明

### 依赖

```
fastapi>=0.100.0
uvicorn>=0.20.0
httpx>=0.24.0
pyyaml>=6.0
jinja2>=3.1
```

### 虚拟环境

项目自带 venv，在 `/home/bandyg/services/kiosk-config-center/venv/`。

```bash
source venv/bin/activate
pip install -r requirements.txt
```

### 模板引擎

使用 Jinja2（服务器端渲染），无前端构建步骤。页面通过 HTMX 风格的 JS 直接调 API。

---

## 注意事项

1. **Config Center 不存配置**，只是代理到各终端 config-serv。各终端下线后无法读写配置。
2. **terminals.yaml 只配了本机**，部署到生产需添加所有终端 IP。
3. 打包 EXE 时 `console=True`（显示控制台窗口），方便调试。发布版本可改为 `console=False`。
4. GitHub Actions 的 Windows 打包在云端完成，本地不需要 Windows 环境。

---

## 链接

- GitHub 仓库：https://github.com/bandyg/config-center
- 本地目录：`/home/bandyg/services/kiosk-config-center/`
- 原始 config-serv：`/home/bandyg/services/new_projects/old_one/config-serv/`
