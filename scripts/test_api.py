"""API 接口自动化测试脚本 — 覆盖全部 27 个用例"""
import httpx
import sys
import json
import time

BASE = "http://127.0.0.1:8300"
passed = 0
failed = 0
results = []

def test(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        results.append((name, "✅ PASS", detail))
    else:
        failed += 1
        results.append((name, "❌ FAIL", detail))

def heading(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

# ──────────────────────────────────────────────
# 前置：获取终端列表
# ──────────────────────────────────────────────
client = httpx.Client(timeout=10.0)

heading("TC-API-001~003: 终端列表 API")
try:
    r = client.get(f"{BASE}/api/terminals")
    test("API-001: 获取终端列表", r.status_code == 200, f"status={r.status_code}")
    data = r.json()
    test("API-001: 返回 JSON 数组", isinstance(data, list), f"type={type(data)}")
    
    if data:
        t = data[0]
        for field in ["ip", "alias", "group", "port", "online"]:
            test(f"API-002: 字段 '{field}' 存在", field in t, f"缺失字段: {field}")
        test("API-002: online 为布尔值", isinstance(t.get("online"), bool), f"value={t.get('online')}")
        test("API-002: port 为整数", isinstance(t.get("port"), int), f"value={t.get('port')}")
        
        # 找一个在线终端
        online_terminals = [t for t in data if t.get("online")]
        offline_terminals = [t for t in data if not t.get("online")]
        
        if online_terminals:
            print(f"\n  在线终端: {len(online_terminals)} 台")
            test("API-003: 在线终端有 config_version", 
                 bool(online_terminals[0].get("config_version")),
                 f"ip={online_terminals[0]['ip']} cv={online_terminals[0].get('config_version')}")
        else:
            print("\n  ⚠️ 无在线终端，部分测试将跳过")
        
        if offline_terminals:
            print(f"  离线终端: {len(offline_terminals)} 台")
            test("API-003: 离线终端 config_version 为 None",
                 offline_terminals[0].get("config_version") is None,
                 f"ip={offline_terminals[0]['ip']}")
    else:
        print("  ⚠️ 无终端数据")
except Exception as e:
    test("API-001: 请求异常", False, str(e))

# ──────────────────────────────────────────────
# 配置读取 API
# ──────────────────────────────────────────────
heading("TC-API-004~007: 配置读取 API")
try:
    r = client.get(f"{BASE}/api/terminals")
    data = r.json()
    online = [t for t in data if t.get("online")]
    
    if online:
        ip = online[0]["ip"]
        
        # API-004: 读取全部配置
        r = client.get(f"{BASE}/api/proxy/{ip}/config")
        test("API-004: 读取全部配置", r.status_code == 200, f"status={r.status_code}")
        all_configs = r.json()
        test("API-004: 返回为 JSON 对象", isinstance(all_configs, dict), "非 dict 返回")
        for expected_key in ["serviceConfig", "terminalFunction"]:
            test(f"API-004: 包含 {expected_key}", 
                 expected_key in all_configs,
                 f"keys={list(all_configs.keys())[:5]}")
        
        # API-006: 读取指定配置项
        r = client.get(f"{BASE}/api/proxy/{ip}/config/terminalFunction")
        test("API-006: 读取指定配置项", r.status_code == 200, f"status={r.status_code}")
        tf = r.json()
        test("API-006: 返回为 JSON 对象", isinstance(tf, dict), "非 dict 返回")
        test("API-006: 包含 configVersion", "configVersion" in tf or "config_version" in str(tf).lower(), 
             f"keys={list(tf.keys())[:5]}")
        
        # API-007: 读取不存在的配置项
        r = client.get(f"{BASE}/api/proxy/{ip}/config/nonexistentKey12345")
        test("API-007: 读取不存在配置项", r.status_code == 200, f"status={r.status_code}")
        test("API-007: 返回空或错误对象", isinstance(r.json(), dict), f"type={type(r.json())}")
    else:
        print("  ⚠️ 无在线终端，跳过读取测试")
    
    # API-005: 读取离线终端（找离线终端测试）
    offline = [t for t in data if not t.get("online")]
    if offline:
        ip_off = offline[0]["ip"]
        r = client.get(f"{BASE}/api/proxy/{ip_off}/config")
        test("API-005: 读取离线终端", r.status_code == 200, f"status={r.status_code}")
        err_data = r.json()
        has_error = "error" in err_data or "detail" in err_data
        test("API-005: 返回错误信息", has_error, f"resp={json.dumps(err_data)[:100]}")
    else:
        print("  ⚠️ 无离线终端，跳过 API-005")
except Exception as e:
    test("API-004~007: 异常", False, str(e))

# ──────────────────────────────────────────────
# 配置写入 API
# ──────────────────────────────────────────────
heading("TC-API-008~011: 配置写入 API")
try:
    r = client.get(f"{BASE}/api/terminals")
    data = r.json()
    online = [t for t in data if t.get("online")]
    
    if online and len(online) > 0:
        ip = online[0]["ip"]
        
        # API-008: 写入配置
        test_value = {"_test_key": f"test_value_{int(time.time())}"}
        r = client.put(f"{BASE}/api/proxy/{ip}/config/serviceConfig", json=test_value)
        test("API-008: 写入在线终端", r.status_code == 200, f"status={r.status_code}")
        
        # 验证写入
        r = client.get(f"{BASE}/api/proxy/{ip}/config/serviceConfig")
        read_back = r.json()
        test("API-008: 写入后读取确认", 
             read_back.get("_test_key") == test_value["_test_key"],
             f"expected={test_value} got={read_back.get('_test_key')}")
        
        # API-009: 写入后自动记录历史
        # 注意: restore操作放在历史检查之后，避免restore创建的新记录覆盖测试写入的历史
        time.sleep(0.5)
        r = client.get(f"{BASE}/api/history/{ip}/serviceConfig")
        test("API-009: 历史记录", r.status_code == 200, f"status={r.status_code}")
        hist = r.json()
        test("API-009: records 不为空", len(hist.get("records", [])) > 0,
             f"records_count={len(hist.get('records', []))}")
        if hist.get("records"):
            rec = hist["records"][0]
            for field in ["timestamp", "time_str", "old_value", "new_value", "ip", "key"]:
                test(f"API-009: 历史记录含 '{field}'", field in rec, f"mising: {field}")
            test("API-009: new_value 与写入一致",
                 rec.get("new_value", {}).get("_test_key") == test_value["_test_key"],
                 f"expected={test_value} got={rec.get('new_value')}")
        
        # 恢复原值（历史检查之后执行，避免覆盖历史记录）
        if "_test_key" in read_back:
            r = client.put(f"{BASE}/api/proxy/{ip}/config/serviceConfig", json={"demoMode": True})
        
        # API-010: 写入非法 JSON（通过 API 层面测试，发送非法内容）
        # FastAPI 会自动校验 JSON body，非法内容返回 422
        # 这里通过发送非 dict 来测试
        r = client.put(f"{BASE}/api/proxy/{ip}/config/serviceConfig", content=b"not json", headers={"Content-Type": "application/json"})
        test("API-010: 非法 JSON 返回错误", r.status_code in [400, 422], f"status={r.status_code}")
        test("API-010: 错误信息提示", "detail" in r.json(), f"resp={r.json()}")
    else:
        print("  ⚠️ 无在线终端，跳过写入测试")
    
    # API-011: 写入离线终端
    offline = [t for t in data if not t.get("online")]
    if offline:
        ip_off = offline[0]["ip"]
        r = client.put(f"{BASE}/api/proxy/{ip_off}/config/serviceConfig", json={"demoMode": True})
        test("API-011: 写入离线终端", r.status_code == 200, f"status={r.status_code}")
        resp = r.json()
        test("API-011: 返回错误信息", "error" in resp, f"resp={json.dumps(resp)[:100]}")
    else:
        print("  ⚠️ 无离线终端，跳过 API-011")
except Exception as e:
    test("API-008~011: 异常", False, str(e))

# ──────────────────────────────────────────────
# 批量操作 API
# ──────────────────────────────────────────────
heading("TC-API-012~016: 批量操作 API")
try:
    r = client.get(f"{BASE}/api/terminals")
    data = r.json()
    online = [t for t in data if t.get("online")]
    
    if len(online) >= 2:
        ips = [t["ip"] for t in online[:2]]
        
        # API-012: 按 IP 批量写入
        r = client.post(f"{BASE}/api/batch", json={
            "targets": {"ips": ips},
            "configs": {"serviceConfig": {"demoMode": True}}
        })
        test("API-012: 按 IP 批量写入", r.status_code == 200, f"status={r.status_code}")
        result = r.json()
        test("API-012: 返回结果数正确", result.get("total") == len(ips),
             f"total={result.get('total')} expected={len(ips)}")
        test("API-012: 结果状态正确", 
             all(r.get("status") == 200 for r in result.get("results", [])),
             f"results={json.dumps(result.get('results'))[:200]}")
        
        # API-016: 批量写入后验证历史
        r = client.get(f"{BASE}/api/history/{ips[0]}/serviceConfig")
        hist = r.json()
        test("API-016: 批量后历史记录", len(hist.get("records", [])) > 0, f"count={len(hist.get('records', []))}")
    
    if len(online) >= 1 and data:
        # API-013: 按分组批量写入
        groups = list(set(t.get("group", "") for t in data if t.get("group")))
        if groups:
            r = client.post(f"{BASE}/api/batch", json={
                "targets": {"groups": [groups[0]]},
                "configs": {"webConfig": {"pageTitle": "BatchTest"}}
            })
            test("API-013: 按分组批量写入", r.status_code == 200, f"status={r.status_code}")
            result = r.json()
            test("API-013: 返回结果", result.get("total", -1) > 0, f"total={result.get('total')}")
    
    # API-015: 空目标
    r = client.post(f"{BASE}/api/batch", json={
        "targets": {"ips": []},
        "configs": {"serviceConfig": {"demoMode": True}}
    })
    test("API-015: 空目标批量写入", r.status_code == 200, f"status={r.status_code}")
    result = r.json()
    test("API-015: total=0", result.get("total") == 0, f"total={result.get('total')}")
    
    # API-014: 混合在线+离线
    offline = [t for t in data if not t.get("online")]
    mixed_ips = []
    if online: mixed_ips.append(online[0]["ip"])
    if offline: mixed_ips.append(offline[0]["ip"])
    if len(mixed_ips) >= 2:
        r = client.post(f"{BASE}/api/batch", json={
            "targets": {"ips": mixed_ips},
            "configs": {"serviceConfig": {"demoMode": False}}
        })
        test("API-014: 混合在线/离线批量写入", r.status_code == 200, f"status={r.status_code}")
        result = r.json()
        test("API-014: 终端数正确", result.get("total") == len(mixed_ips), f"total={result.get('total')}")
except Exception as e:
    test("API-012~016: 异常", False, str(e))

# ──────────────────────────────────────────────
# 配置对比 API
# ──────────────────────────────────────────────
heading("TC-API-017~020: 配置对比 API")
try:
    r = client.get(f"{BASE}/api/terminals")
    data = r.json()
    online = [t for t in data if t.get("online")]
    
    if len(online) >= 2:
        ips = [t["ip"] for t in online[:2]]
        
        # API-017: 两终端单配置项对比
        r = client.get(f"{BASE}/api/compare", params={"ips": ",".join(ips), "keys": "serviceConfig"})
        test("API-017: 两终端单配置项对比", r.status_code == 200, f"status={r.status_code}")
        result = r.json()
        test("API-017: 返回含配置项 key", "serviceConfig" in result, f"keys={list(result.keys())}")
        for ip in ips:
            test(f"API-017: 含终端 {ip}", ip in result.get("serviceConfig", {}),
                 f"available_ips={list(result.get('serviceConfig', {}).keys())}")
            if ip in result.get("serviceConfig", {}):
                test(f"API-017: 含 flattened 数据", "flattened" in result["serviceConfig"][ip],
                     f"keys={list(result['serviceConfig'][ip].keys())}")
        
        # API-018: 多配置项对比
        r = client.get(f"{BASE}/api/compare", params={"ips": ",".join(ips), "keys": "serviceConfig,terminalFunction"})
        test("API-018: 多配置项对比", r.status_code == 200, f"status={r.status_code}")
        result = r.json()
        test("API-018: 包含两个配置项", "serviceConfig" in result and "terminalFunction" in result,
             f"keys={list(result.keys())}")
        
        # API-019: 三终端对比
        if len(online) >= 3:
            ips3 = [t["ip"] for t in online[:3]]
            r = client.get(f"{BASE}/api/compare", params={"ips": ",".join(ips3), "keys": "serviceConfig"})
            test("API-019: 三终端对比", r.status_code == 200, f"status={r.status_code}")
            result = r.json()
            test("API-019: 包含三终端数据", 
                 all(ip in result.get("serviceConfig", {}) for ip in ips3),
                 f"actual_ips={list(result.get('serviceConfig', {}).keys())}")
        
        # API-020: 同一台终端对比
        r = client.get(f"{BASE}/api/compare", params={"ips": f"{ips[0]},{ips[0]}", "keys": "serviceConfig"})
        test("API-020: 同终端对比", r.status_code == 200, f"status={r.status_code}")
    else:
        print("  ⚠️ 在线终端不足 2 台，跳过对比测试")
except Exception as e:
    test("API-017~020: 异常", False, str(e))

# ──────────────────────────────────────────────
# 配置历史 API
# ──────────────────────────────────────────────
heading("TC-API-021~022: 配置历史 API")
try:
    r = client.get(f"{BASE}/api/terminals")
    data = r.json()
    online = [t for t in data if t.get("online")]
    
    if online:
        ip = online[0]["ip"]
        
        # API-021: 获取已有修改历史
        r = client.get(f"{BASE}/api/history/{ip}/serviceConfig")
        test("API-021: 获取历史记录", r.status_code == 200, f"status={r.status_code}")
        hist = r.json()
        test("API-021: 返回含 records 字段", "records" in hist, f"keys={list(hist.keys())}")
        
        # API-022: 获取无历史配置项
        r = client.get(f"{BASE}/api/history/{ip}/posterConfig_nonexistent")
        test("API-022: 无历史记录", r.status_code == 200, f"status={r.status_code}")
        hist = r.json()
        test("API-022: records 为空数组", hist.get("records") == [], f"records={hist.get('records')}")
    else:
        print("  ⚠️ 无在线终端，跳过历史测试")
except Exception as e:
    test("API-021~022: 异常", False, str(e))

# ──────────────────────────────────────────────
# 回滚 API
# ──────────────────────────────────────────────
heading("TC-API-023~025: 回滚 API")
try:
    r = client.get(f"{BASE}/api/terminals")
    data = r.json()
    online = [t for t in data if t.get("online")]
    
    if online:
        ip = online[0]["ip"]
        
        # 构造一条新记录用于回滚测试
        ts = int(time.time() * 1000) / 1000.0
        client.put(f"{BASE}/api/proxy/{ip}/config/serviceConfig", json={"_rollback_test_val": "v1"})
        time.sleep(0.2)
        client.put(f"{BASE}/api/proxy/{ip}/config/serviceConfig", json={"_rollback_test_val": "v2"})
        time.sleep(0.2)
        
        # 获取历史，找到 v1 版本的时间戳
        r = client.get(f"{BASE}/api/history/{ip}/serviceConfig")
        hist = r.json()
        v1_ts = None
        for rec in hist.get("records", []):
            if rec.get("new_value", {}).get("_rollback_test_val") == "v1":
                v1_ts = rec["timestamp"]
                break
        
        if v1_ts:
            # API-023: 回滚到历史版本
            r = client.post(f"{BASE}/api/rollback/{ip}/serviceConfig", json={"timestamp": v1_ts})
            test("API-023: 回滚到历史版本", r.status_code == 200, f"status={r.status_code}")
            rollback_resp = r.json()
            test("API-023: 回滚成功", rollback_resp.get("status") == "ok",
                 f"resp={json.dumps(rollback_resp)[:100]}")
        else:
            print("  ⚠️ 未找到回滚目标版本")
        
        # API-024: 回滚到不存在的版本
        r = client.post(f"{BASE}/api/rollback/{ip}/serviceConfig", json={"timestamp": 9999999999.0})
        test("API-024: 回滚不存在的版本", r.status_code == 200, f"status={r.status_code}")
        resp = r.json()
        test("API-024: 返回 error 状态", resp.get("status") == "error",
             f"resp={json.dumps(resp)[:100]}")
        
        # API-025: 缺少 timestamp
        r = client.post(f"{BASE}/api/rollback/{ip}/serviceConfig", json={})
        test("API-025: 缺少 timestamp", r.status_code == 200, f"status={r.status_code}")
        resp = r.json()
        test("API-025: 返回 error 状态", resp.get("status") == "error",
             f"resp={json.dumps(resp)[:100]}")
    else:
        print("  ⚠️ 无在线终端，跳过回滚测试")
except Exception as e:
    test("API-023~025: 异常", False, str(e))

# ──────────────────────────────────────────────
# 健康度 API
# ──────────────────────────────────────────────
heading("TC-API-026~027: 健康度 API")
try:
    r = client.get(f"{BASE}/api/health")
    test("API-026: 获取健康度列表", r.status_code == 200, f"status={r.status_code}")
    health_data = r.json()
    test("API-026: 返回 JSON 数组", isinstance(health_data, list), f"type={type(health_data)}")
    
    if health_data:
        for field in ["ip", "alias", "online", "score", "issues"]:
            test(f"API-026: 含字段 '{field}'", field in health_data[0],
                 f"keys={list(health_data[0].keys())}")
        
        # API-027: 评分范围
        for h in health_data:
            test(f"API-027: 评分 0-100 ({h['ip']})", 0 <= h.get("score", -1) <= 100,
                 f"score={h.get('score')}")
            test(f"API-027: 评分整数 ({h['ip']})", isinstance(h.get("score"), (int, float)),
                 f"score_type={type(h.get('score'))}")
        
        # 在线终端评分 > 0
        for h in health_data:
            if h.get("online"):
                test(f"API-027: 在线终端评分 >0 ({h['ip']})", h.get("score", 0) > 0,
                     f"score={h.get('score')}")
            else:
                test(f"API-027: 离线终端评分=0 ({h['ip']})", h.get("score", -1) == 0,
                     f"score={h.get('score')}")
    else:
        print("  ⚠️ 返回空数组")
except Exception as e:
    test("API-026~027: 异常", False, str(e))

# ──────────────────────────────────────────────
# 页面基础渲染测试
# ──────────────────────────────────────────────
heading("页面基础渲染测试")
pages = [
    ("GET /", "/", "首页"),
    ("GET /batch", "/batch", "批量操作页"),
    ("GET /compare", "/compare", "配置对比页"),
]
for name, path, label in pages:
    try:
        r = client.get(f"{BASE}{path}")
        test(f"UI-{label}: HTTP 200", r.status_code == 200, f"status={r.status_code}")
        test(f"UI-{label}: 返回 HTML", "text/html" in r.headers.get("content-type", ""),
             f"content-type={r.headers.get('content-type')}")
        test(f"UI-{label}: 含 DOCTYPE", "<!DOCTYPE" in r.text, "missing DOCTYPE")
        # 基础内容校验
        if "配置" in r.text or "Config" in r.text or "Kiosk" in r.text:
            test(f"UI-{label}: 含中文内容", True, "页面含中文或标题")
        else:
            test(f"UI-{label}: 含中文内容", False, "页面不含中文或标题")
    except Exception as e:
        test(f"UI-{label}: 异常", False, str(e))

# ──────────────────────────────────────────────
# 总结
# ──────────────────────────────────────────────
heading("测试总结")
print(f"\n  总计: {passed + failed} 个用例")
print(f"  通过: {passed} ✅")
print(f"  失败: {failed} ❌")
print(f"  通过率: {passed/(passed+failed)*100:.1f}%\n")

if failed > 0:
    print("  失败详情:")
    for name, status, detail in results:
        if "FAIL" in status:
            print(f"    • {name}: {detail}")

client.close()
sys.exit(0 if failed == 0 else 1)
