import httpx

c = httpx.Client(timeout=10)
BASE = 'http://127.0.0.1:8300'

# Test 1: invalid JSON returns 422
r = c.put(f'{BASE}/api/proxy/100.66.5.26/config/serviceConfig', content=b'not json', headers={'Content-Type': 'application/json'})
print(f'非法JSON: {r.status_code} (期望422), body={r.json()}')

# Test 2: nonexistent config key returns 200 with error
r = c.get(f'{BASE}/api/proxy/100.66.5.26/config/nonexistentKey999')
print(f'不存在配置项: {r.status_code} (期望200), error={r.json().get("error", "none")}')
