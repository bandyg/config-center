"""Kiosk Config Center — FastAPI 主入口"""

import sys
from pathlib import Path

# 确保能找到 app 包（PyInstaller 打包兼容）
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.terminals import load_terminals, get_terminal_groups, Terminal
from app.proxy import check_online, fetch_all_configs, fetch_config, write_config

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import httpx
import json
from dataclasses import asdict

app = FastAPI(title="Kiosk Config Center", version="1.0.0")

# Jinja2 模板（兼容 PyInstaller 打包路径）
import os
_base_dir = Path(os.environ.get("KIOSK_CONFIG_BASE_DIR", str(Path(__file__).parent)))
templates_dir = _base_dir / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


# ─── API ─────────────────────────────────────────────


@app.get("/api/terminals")
async def api_terminals():
    """返回终端列表（含在线状态）"""
    terminals = load_terminals()
    result = []
    for t in terminals:
        online = await check_online(t.ip, t.port)
        cv = None
        if online:
            tf = await fetch_config(t.ip, t.port, "terminalFunction")
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


@app.get("/api/proxy/{ip}/config/{key:path}")
async def api_proxy_config_get(ip: str, key: str, port: int = 8081):
    """代理 GET 请求到终端 config-serv 读取配置"""
    data = await fetch_config(ip, port, key)
    return data


@app.get("/api/proxy/{ip}/config")
async def api_proxy_config_all(ip: str, port: int = 8081):
    """获取终端全部配置"""
    data = await fetch_all_configs(ip, port)
    return data


@app.put("/api/proxy/{ip}/config/{key:path}")
async def api_proxy_config_set(ip: str, key: str, request: Request, port: int = 8081):
    """代理 PUT 请求到终端 config-serv 写入配置"""
    body = await request.json()
    result = await write_config(ip, port, key, body)
    return result


@app.post("/api/batch")
async def api_batch(request: Request):
    """批量写入配置到多个终端"""
    body = await request.json()
    targets = body.get("targets", {})
    configs = body.get("configs", {})

    ips = set(targets.get("ips", []))
    groups = set(targets.get("groups", []))

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
            r = await write_config(t.ip, t.port, key, val)
            results.append({
                "ip": t.ip,
                "alias": t.alias,
                "config": key,
                "status": r.get("status", "error"),
                "error": r.get("error"),
            })
    return {"total": len(matched), "results": results}


@app.get("/api/compare")
async def api_compare(ips: str = "", config_key: str = "terminalFunction"):
    """对比多台终端的配置差异"""
    ip_list = [ip.strip() for ip in ips.split(",") if ip.strip()]
    terminals = load_terminals()
    selected = [t for t in terminals if t.ip in ip_list]

    result = {}
    for t in selected:
        data = await fetch_config(t.ip, t.port, config_key)
        result[t.ip] = {"alias": t.alias, "config": data}
    return result


# ─── 页面 ─────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """终端列表首页"""
    terminals_raw = load_terminals()
    groups = get_terminal_groups(terminals_raw)
    return templates.TemplateResponse(
        request, "index.html",
        {"terminals": [asdict(t) for t in terminals_raw], "groups": groups},
    )


@app.get("/terminal/{ip}", response_class=HTMLResponse)
async def terminal_detail(request: Request, ip: str, port: int = 8081):
    """终端详情页"""
    terminals_list = load_terminals()
    t = next((t for t in terminals_list if t.ip == ip), None)
    if not t:
        return HTMLResponse("Terminal not found", status_code=404)

    online = await check_online(ip, port)
    configs = {}
    if online:
        configs = await fetch_all_configs(ip, port)

    return templates.TemplateResponse(
        request, "terminal.html",
        {"terminal": asdict(t), "online": online, "configs": configs},
    )


@app.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request):
    """批量操作页面"""
    terminals_raw = load_terminals()
    groups = get_terminal_groups(terminals_raw)
    return templates.TemplateResponse(
        request, "batch.html",
        {"terminals": [asdict(t) for t in terminals_raw], "groups": groups},
    )


@app.get("/compare", response_class=HTMLResponse)
async def compare_page(request: Request):
    """配置对比页面"""
    terminals_raw = load_terminals()
    return templates.TemplateResponse(
        request, "compare.html",
        {"terminals": [asdict(t) for t in terminals_raw]},
    )
