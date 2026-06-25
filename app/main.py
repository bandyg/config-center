"""Kiosk Config Center — FastAPI 主入口"""

import sys
from pathlib import Path

# 确保能找到 app 包（PyInstaller 打包兼容）
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.terminals import load_terminals, save_terminals, get_terminal_groups, Terminal
from app.accessor import TerminalAccessor, DirectAccessor
from app.proxy import check_online, fetch_all_configs, fetch_config, write_config  # noqa: F401 — 兼容层
from app.history import record_config_change, get_config_history, rollback_config

from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import Query
import httpx
import json
import re
import asyncio
from typing import Optional
from dataclasses import asdict

app = FastAPI(title="Kiosk Config Center", version="1.0.0")

# ─── 依赖注入 ────────────────────────────────────────

_accessor: TerminalAccessor = DirectAccessor()
_bc_registry = None  # DC 模式下持有 BcRegistry 引用
_mode: str = "bc"


def init_app(mode: str = "bc"):
    """初始化应用（启动时调用一次，注入对应模式的 accessor）"""
    global _accessor, _bc_registry, _mode
    _mode = mode
    if mode == "dc":
        from app.bc_registry import BcRegistry
        from app.accessor import BcProxyAccessor
        _bc_registry = BcRegistry()
        _accessor = BcProxyAccessor(_bc_registry)
        # 首次预热 + 启动后台定时刷新
        async def _warmup():
            try:
                await _bc_registry.refresh_all()
            except Exception:
                pass
            _bc_registry.start_background_refresh()
        import asyncio as _asyncio
        try:
            loop = _asyncio.get_running_loop()
            loop.create_task(_warmup())
        except RuntimeError:
            pass
    else:
        _accessor = DirectAccessor()
        _bc_registry = None


def get_accessor() -> TerminalAccessor:
    return _accessor


def get_mode() -> str:
    return _mode

# Jinja2 模板 + 静态文件（兼容 PyInstaller 打包路径）
import os
_base_dir = Path(os.environ.get("KIOSK_CONFIG_BASE_DIR", str(Path(__file__).parent)))
templates_dir = _base_dir / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

static_dir = _base_dir / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ─── API ─────────────────────────────────────────────


@app.get("/api/terminals")
async def api_terminals(accessor: TerminalAccessor = Depends(get_accessor)):
    """返回终端列表（含在线状态）"""
    if get_mode() == "dc" and _bc_registry is not None:
        return _bc_registry.get_terminals()

    terminals = load_terminals()
    result = []
    for t in terminals:
        online = await accessor.check_online(t.ip, t.port)
        cv = None
        if online:
            tf = await accessor.fetch_config(t.ip, t.port, "terminalFunction")
            if "configVersion" in tf:
                cv = tf["configVersion"]
        result.append({
            "ip": t.ip,
            "alias": t.alias,
            "group": t.group,
            "port": t.port,
            "online": online,
            "config_version": cv,
        })
    return result


@app.post("/api/terminals/add")
async def api_terminals_add(request: Request, accessor: TerminalAccessor = Depends(get_accessor)):
    """添加新的终端（校验 IP 有效性 → 检测在线 → 写入 YAML）

    DC 模式不支持此操作（终端归属由各 BC 自行管理）。
    """
    if get_mode() == "dc":
        return {"status": "error", "error": "DC 模式不支持添加终端，请在对应 BC Server 上操作"}
    import traceback
    try:
        body = await request.json()
        ip = body.get("ip", "").strip()
        alias = body.get("alias", "").strip() or ip
        group = body.get("group", "").strip() or "default"
        port = int(body.get("port", 8081))

        # IP 格式校验
        ip_pattern = r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$"
        m = re.match(ip_pattern, ip)
        if not m:
            return {"status": "error", "error": "IP 地址格式不合法"}
        for octet in m.groups():
            if int(octet) > 255:
                return {"status": "error", "error": f"IP 段不能超过 255: {octet}"}

        # 查重
        terminals_list = load_terminals()
        if any(t.ip == ip for t in terminals_list):
            return {"status": "error", "error": "该 IP 已在终端列表中"}

        # 检测连通性
        try:
            online = await accessor.check_online(ip, port)
        except Exception:
            online = False

        # 添加到列表
        new_terminal = Terminal(ip=ip, alias=alias, group=group, port=port)
        terminals_list.append(new_terminal)
        save_terminals(terminals_list)

        return {
            "status": "ok",
            "terminal": {"ip": ip, "alias": alias, "group": group, "port": port, "online": online},
        }
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "error": f"服务异常: {type(e).__name__}: {e}"}


# ─── 子网扫描状态 ──
_scan_progress = {"running": False, "total": 0, "done": 0, "found": [], "error": None}


def _cidr_to_ips(cidr: str):
    """将 CIDR 转为 IP 列表"""
    import ipaddress
    net = ipaddress.ip_network(cidr, strict=False)
    return [str(ip) for ip in net.hosts()]


@app.post("/api/terminals/scan")
async def api_terminals_scan(request: Request):
    """扫描子网内开放指定端口的终端

    DC 模式不支持此操作（扫描由各 BC 自行执行）。
    """
    if get_mode() == "dc":
        return {"status": "error", "error": "DC 模式不支持扫描子网，请在对应 BC Server 上操作"}
    global _scan_progress
    body = await request.json()
    cidr = body.get("cidr", "").strip()
    port = int(body.get("port", 8081))

    # CIDR 格式校验
    try:
        ips = _cidr_to_ips(cidr)
    except Exception as e:
        return {"status": "error", "error": f"CIDR 格式不合法: {e}"}

    if not ips:
        return {"status": "error", "error": "CIDR 未包含有效主机地址"}

    # 已有终端列表（用于去重）
    existing = set(t.ip for t in load_terminals())

    _scan_progress = {"running": True, "total": len(ips), "done": 0, "found": [], "error": None}

    async def scan_one(host_ip):
        try:
            # 尝试 TCP 连接 8081 端口
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host_ip, port), timeout=2
            )
            writer.close()
            await writer.wait_closed()
            # 进一步验证是否为 config-serv（GET / 看响应）
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    r = await client.get(f"http://{host_ip}:{port}/")
                    if r.status_code < 500:
                        return host_ip
            except Exception:
                pass
        except Exception:
            pass
        return None

    async def scan_all():
        sem = asyncio.Semaphore(50)  # 并发控制
        async def bounded_scan(host_ip):
            async with sem:
                result = await scan_one(host_ip)
                _scan_progress["done"] += 1
                if result and result not in existing:
                    _scan_progress["found"].append({"ip": result, "port": port, "alias": result, "group": "已发现"})
                return result

        tasks = [bounded_scan(ip) for ip in ips]
        await asyncio.gather(*tasks)
        _scan_progress["running"] = False

    asyncio.create_task(scan_all())
    return {
        "status": "ok",
        "message": f"开始扫描 {cidr}，共 {len(ips)} 个地址",
        "total": len(ips),
    }


@app.get("/api/terminals/scan/progress")
async def api_terminals_scan_progress():
    """获取扫描进度"""
    return _scan_progress


@app.post("/api/terminals/scan/batch-add")
async def api_terminals_scan_batch_add(request: Request):
    """批量添加扫描到的主机"""
    body = await request.json()
    hosts = body.get("hosts", [])
    if not hosts:
        return {"status": "error", "error": "没有要添加的主机"}

    terminals_list = load_terminals()
    existing = set(t.ip for t in terminals_list)
    added = []
    skipped = []

    for h in hosts:
        ip = h.get("ip", "").strip()
        if not ip:
            continue
        if ip in existing:
            skipped.append(ip)
            continue
        alias = h.get("alias", "").strip() or ip
        group = h.get("group", "").strip() or "已发现"
        port = int(h.get("port", 8081))
        terminals_list.append(Terminal(ip=ip, alias=alias, group=group, port=port))
        existing.add(ip)
        added.append({"ip": ip, "alias": alias, "group": group})

    save_terminals(terminals_list)
    return {"status": "ok", "added": added, "skipped": skipped}


@app.get("/api/proxy/{ip}/config/{key:path}")
async def api_proxy_config_get(ip: str, key: str, port: int = 8081, accessor: TerminalAccessor = Depends(get_accessor)):
    """代理 GET 请求到终端 config-serv 读取配置"""
    data = await accessor.fetch_config(ip, port, key)
    return data


@app.get("/api/proxy/{ip}/config")
async def api_proxy_config_all(ip: str, port: int = 8081, accessor: TerminalAccessor = Depends(get_accessor)):
    """获取终端全部配置"""
    data = await accessor.fetch_all_configs(ip, port)
    return data


@app.put("/api/proxy/{ip}/config/{key:path}")
async def api_proxy_config_set(ip: str, key: str, request: Request, port: int = 8081, accessor: TerminalAccessor = Depends(get_accessor)):
    """代理 PUT 请求到终端 config-serv 写入配置（含历史记录）"""
    try:
        body = await request.json()
    except Exception:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=422,
            content={"detail": "请求体不是合法的 JSON 格式", "error": "JSON parse error"},
        )
    # 获取旧值用于历史记录
    old_val = await accessor.fetch_config(ip, port, key)
    result = await accessor.write_config(ip, port, key, body)
    # 记录历史
    terminals = load_terminals()
    alias = next((t.alias for t in terminals if t.ip == ip), ip)
    record_config_change(ip, alias, key, old_val, body)
    return result


@app.post("/api/batch")
async def api_batch(request: Request, accessor: TerminalAccessor = Depends(get_accessor)):
    """批量写入配置到多个终端"""
    body = await request.json()
    targets = body.get("targets", {})
    configs = body.get("configs", {})

    ips = set(targets.get("ips", []))
    groups = set(targets.get("groups", []))

    if get_mode() == "dc" and _bc_registry is not None:
        # DC 模式：从 BcRegistry 匹配终端，按 BC 分组推送
        all_terms = _bc_registry.get_terminals()
        matched = []
        for t in all_terms:
            if t["ip"] in ips:
                matched.append(t)
            elif t.get("branch_name", t.get("group", "")) in groups:
                matched.append(t)

        # 按 BC URL 分组
        bc_groups: dict[str, list[dict]] = {}
        for t in matched:
            bc_url = t.get("bc_url", "")
            if bc_url not in bc_groups:
                bc_groups[bc_url] = []
            bc_groups[bc_url].append(t)

        results = []
        async def _push_to_bc(bc_url, terminals):
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.post(
                        f"{bc_url}/api/batch",
                        json={"targets": {"ips": [t["ip"] for t in terminals]}, "configs": configs},
                    )
                    if r.status_code == 200:
                        data = r.json()
                        return data.get("results", [])
            except Exception:
                pass
            return [{"ip": t["ip"], "alias": t.get("alias", ""), "config": k,
                     "status": "error", "error": "BC 请求失败"}
                    for t in terminals for k in configs]

        tasks = [_push_to_bc(url, terms) for url, terms in bc_groups.items()]
        batch_results = await asyncio.gather(*tasks)
        for br in batch_results:
            results.extend(br)

        return {"total": len(matched), "results": results}

    # BC 模式：原始逻辑
    terminals = load_terminals()
    matched = []
    for t in terminals:
        if t.ip in ips:
            matched.append(t)
        elif t.group in groups:
            matched.append(t)

    results = []
    for t in matched:
        for key, val in configs.items():
            old_val = await accessor.fetch_config(t.ip, t.port, key)
            r = await accessor.write_config(t.ip, t.port, key, val)
            record_config_change(t.ip, t.alias, key, old_val, val)
            results.append({
                "ip": t.ip,
                "alias": t.alias,
                "config": key,
                "status": r.get("status", "error"),
                "error": r.get("error"),
            })
    return {"total": len(matched), "results": results}


@app.get("/api/compare")
async def api_compare(request: Request, accessor: TerminalAccessor = Depends(get_accessor)):
    """对比多台终端的配置差异（支持多配置项）"""
    # 直接从 query string 解析，兼容 ?ips=a&ips=b 和 ?ips=a,b 两种形式
    params = request.query_params
    ip_list = []
    for v in params.getlist("ips"):
        for part in v.split(","):
            p = part.strip()
            if p and p not in ip_list:
                ip_list.append(p)
    key_list = []
    for v in params.getlist("keys"):
        for part in v.split(","):
            p = part.strip()
            if p and p not in key_list:
                key_list.append(p)
    # 默认值
    if not key_list:
        key_list = ["terminalFunction"]
    terminals = load_terminals()
    selected = [t for t in terminals if t.ip in ip_list]

    def flatten(obj, prefix=""):
        """将嵌套 JSON 展平为 dot-notation 键值对"""
        items = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                path = f"{prefix}.{k}" if prefix else k
                if isinstance(v, (dict, list)):
                    items.update(flatten(v, path))
                else:
                    items[path] = v
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                path = f"{prefix}[{i}]"
                if isinstance(v, (dict, list)):
                    items.update(flatten(v, path))
                else:
                    items[path] = v
        return items

    result = {}
    for key in key_list:
        result[key] = {}
        for t in selected:
            data = await accessor.fetch_config(t.ip, t.port, key)
            result[key][t.ip] = {"alias": t.alias, "flattened": flatten(data)}
    return result


# ─── 配置历史与回滚 API ──────────────────────────────


@app.get("/api/history/{ip}/{key:path}")
async def api_history(ip: str, key: str, limit: int = 50):
    """获取指定终端指定配置项的修改历史"""
    records = get_config_history(ip, key, limit=limit)
    return {"ip": ip, "key": key, "records": records}


@app.post("/api/rollback/{ip}/{key:path}")
async def api_rollback(ip: str, key: str, request: Request, accessor: TerminalAccessor = Depends(get_accessor)):
    """回滚配置到指定版本（将回滚值写入终端并记录历史）"""
    body = await request.json()
    target_ts = body.get("timestamp")
    if not target_ts:
        return {"status": "error", "error": "缺少 timestamp 参数"}

    success, rollback_value, error = rollback_config(ip, key, target_ts)
    if not success:
        return {"status": "error", "error": error}

    # 将回滚后的值实际写入终端
    result = await accessor.write_config(ip, 8081, key, rollback_value)
    if result.get("error"):
        return {"status": "error", "error": f"写入终端失败: {result['error']}"}

    return {"status": "ok", "rollback_value": rollback_value}


# ─── 健康度 API ──────────────────────────────────────


@app.get("/api/health")
async def api_health(accessor: TerminalAccessor = Depends(get_accessor)):
    """计算各终端健康度评分"""
    terminals = load_terminals()

    def flatten(obj, prefix=""):
        items = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                path = f"{prefix}.{k}" if prefix else k
                if isinstance(v, (dict, list)):
                    items.update(flatten(v, path))
                else:
                    items[path] = v
        return items

    results = []
    for t in terminals:
        online = await accessor.check_online(t.ip, t.port)
        score = 0
        issues = []
        config_version = None
        config_count = 0

        if online:
            score += 40  # 在线基础分
            all_cfgs = await accessor.fetch_all_configs(t.ip, t.port)
            if all_cfgs:
                config_count = len(all_cfgs)
                tf = all_cfgs.get("terminalFunction", {})
                config_version = tf.get("configVersion", "unknown")
                # 检查必需的配置项是否存在
                required_keys = ["serviceConfig", "terminalFunction", "supervisorConfig",
                                 "bcConfig", "infoConfig", "webConfig"]
                for rk in required_keys:
                    if rk not in all_cfgs:
                        issues.append(f"缺少配置项: {rk}")
                    else:
                        score += 5  # 每个必需项 +5 分
                # 版本号合理性
                if config_version and isinstance(config_version, str):
                    score += 10
                # 配置完整性
                if config_count >= 6:
                    score += 10
        else:
            issues.append("终端离线")

        score = min(score, 100)
        results.append({
            "ip": t.ip,
            "alias": t.alias,
            "online": online,
            "score": score,
            "issues": issues,
            "config_version": config_version,
            "config_count": config_count,
        })

    return results


# ─── 页面 ─────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, page: int = 1, page_size: int = 20, accessor: TerminalAccessor = Depends(get_accessor)):
    """终端列表首页（SSR 直接输出在线状态，支持分页与健康度）"""
    mode = get_mode()

    if mode == "dc" and _bc_registry is not None:
        # DC 模式：从 BcRegistry 缓存加载（BC 已检测在线状态）
        all_terminals = _bc_registry.get_terminals()
        groups = sorted(set(t.get("branch_name", t.get("group", "")) for t in all_terminals))
        online_count = sum(1 for t in all_terminals if t.get("online"))
        status_map = {t["ip"]: t for t in all_terminals}
        health_map = {}
        for t in all_terminals:
            health_map[t["ip"]] = {"score": 80 if t.get("online") else 0,
                                    "issues": [] if t.get("online") else ["离线"]}

        total = len(all_terminals)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        start = (page - 1) * page_size
        end = start + page_size
        paged_terminals = all_terminals[start:end]

        return templates.TemplateResponse(
            request, "index.html",
            {
                "terminals": paged_terminals,
                "all_terminals": all_terminals,
                "groups": groups,
                "status_map": status_map,
                "health_map": health_map,
                "online_count": online_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "total": total,
                "mode": "dc",
            },
        )

    # BC 模式：原始逻辑
    terminals_raw = load_terminals()
    groups = get_terminal_groups(terminals_raw)
    
    # SSR: 并行检测所有终端在线状态
    async def check(t):
        online = await accessor.check_online(t.ip, t.port)
        cv = None
        if online:
            tf = await accessor.fetch_config(t.ip, t.port, "terminalFunction")
            if "configVersion" in tf:
                cv = tf.get("configVersion")
        return {"ip": t.ip, "online": online, "config_version": cv}
    
    status_results = await asyncio.gather(*[check(t) for t in terminals_raw])
    status_map = {r["ip"]: r for r in status_results}
    online_count = sum(1 for r in status_results if r["online"])
    
    # 计算健康度评分
    health_map = {}
    for t in terminals_raw:
        s = status_map.get(t.ip, {})
        online = s.get("online", False)
        score = 0
        issues = []
        if not online:
            score = 0
            issues.append("离线")
        else:
            score += 60  # 在线基础分
            cv = s.get("config_version")
            if cv:
                score += 20
            if online:
                score += 20  # 可访问加分
            score = min(score, 100)
        health_map[t.ip] = {"score": score, "issues": issues}
    
    # 分页
    total = len(terminals_raw)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    paged_terminals = [asdict(t) for t in terminals_raw[start:end]]
    
    return templates.TemplateResponse(
        request, "index.html",
        {
            "terminals": paged_terminals,
            "all_terminals": [asdict(t) for t in terminals_raw],
            "groups": groups,
            "status_map": status_map,
            "health_map": health_map,
            "online_count": online_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total": total,
            "mode": "bc",
        },
    )


@app.get("/terminal/{ip}", response_class=HTMLResponse)
async def terminal_detail(request: Request, ip: str, port: int = 8081, accessor: TerminalAccessor = Depends(get_accessor)):
    """终端详情页"""
    mode = get_mode()
    branch_info = {}

    if mode == "dc" and _bc_registry is not None:
        # DC 模式：从 BcRegistry 查找终端信息
        all_terms = _bc_registry.get_terminals()
        t_dict = next((t for t in all_terms if t["ip"] == ip), None)
        if not t_dict:
            return HTMLResponse("Terminal not found", status_code=404)
        branch_info = {
            "branch_name": t_dict.get("branch_name", ""),
            "branch_id": t_dict.get("branch_id", ""),
        }
        terminal_ctx = {
            "ip": t_dict["ip"],
            "alias": t_dict.get("alias", t_dict["ip"]),
            "group": t_dict.get("group", t_dict.get("branch_name", "")),
            "port": t_dict.get("port", 8081),
        }
    else:
        terminals_list = load_terminals()
        t = next((t for t in terminals_list if t.ip == ip), None)
        if not t:
            return HTMLResponse("Terminal not found", status_code=404)
        terminal_ctx = asdict(t)

    online = await accessor.check_online(ip, port)
    configs = {}
    if online:
        configs = await accessor.fetch_all_configs(ip, port)

    return templates.TemplateResponse(
        request, "terminal.html",
        {"terminal": terminal_ctx, "online": online, "configs": configs,
         "mode": mode, "branch_info": branch_info},
    )


@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request):
    """批量操作页面"""
    mode = get_mode()
    if mode == "dc" and _bc_registry is not None:
        terminals_list = _bc_registry.get_terminals()
        groups = sorted(set(t.get("branch_name", t.get("group", "")) for t in terminals_list))
    else:
        terminals_raw = load_terminals()
        terminals_list = [asdict(t) for t in terminals_raw]
        groups = get_terminal_groups(terminals_raw)
    return templates.TemplateResponse(
        request, "batch.html",
        {"terminals": terminals_list, "groups": groups, "mode": mode},
    )


@app.get("/compare", response_class=HTMLResponse)
async def compare_page(request: Request):
    """配置对比页面"""
    mode = get_mode()
    if mode == "dc" and _bc_registry is not None:
        terminals_list = _bc_registry.get_terminals()
    else:
        terminals_raw = load_terminals()
        terminals_list = [asdict(t) for t in terminals_raw]
    terminals_with_alias = {t["ip"]: t.get("alias", t["ip"]) for t in terminals_list}
    return templates.TemplateResponse(
        request, "compare.html",
        {
            "terminals": terminals_list,
            "terminals_with_alias": terminals_with_alias,
            "mode": mode,
        },
    )


# ── 优雅关闭服务（供 web UI 调用）──
import os
import sys
import threading


@app.post("/api/shutdown")
async def api_shutdown():
    """优雅关闭 uvicorn 服务（用于 Web UI 关闭按钮）"""
    def _shutdown():
        import time
        time.sleep(0.3)  # 留时间让响应返回
        # PyInstaller 打包后 SIGINT 在 Windows 上不工作，直接强制退出
        # 开发模式（python run.py）下也会触发 KeyboardInterrupt 让 uvicorn 优雅停止
        def _force_exit():
            time.sleep(0.5)
            # 同时关掉控制台窗口（PyInstaller 打包时）— 找父 cmd.exe
            try:
                import subprocess
                subprocess.Popen(
                    ['taskkill', '/F', '/FI', f'PID eq {os.getpid()}', '/T'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            except Exception:
                pass
            os._exit(0)
        threading.Thread(target=_force_exit, daemon=True).start()
    threading.Thread(target=_shutdown, daemon=True).start()
    return {"status": "ok", "message": "服务正在关闭，请重新启动 EXE 以再次使用"}
