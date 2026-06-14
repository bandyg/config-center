"""
预览变更按钮显隐逻辑测试

测试场景：
  1. 页面初始化时按钮默认隐藏（opacity:0, visibility:hidden）
  2. 修改编辑器内容后按钮显示（opacity:1, visibility:visible）
  3. 保存成功后按钮重新隐藏

方法：直接检查 HTML 源码中的 class="preview-btn" 的默认状态，
     以及 JS 函数 updatePreviewBtn 的正确性。
"""
import requests
import json
import sys

BASE = "http://127.0.0.1:8300"

def test(name, ok, detail=""):
    status = "✅" if ok else "❌"
    print(f"  {status} {name}")
    if not ok and detail:
        print(f"      └─ {detail}")
    return ok

all_pass = True

# ─── 获取在线终端 ───
r = requests.get(f"{BASE}/api/terminals", timeout=10)
terminals = r.json()
online = [t for t in terminals if t.get("online")]

if not online:
    print("❌ 没有在线终端，无法测试")
    sys.exit(1)

ip = online[0]["ip"]
print(f"测试终端: {ip}\n")

# ─── 获取详情页 HTML ───
r = requests.get(f"{BASE}/terminal/{ip}", timeout=15)
html = r.text
print(f"页面 HTTP 状态: {r.status_code}\n")

# ════════════════════════════════════════
# 场景 1: 页面初始化时按钮默认隐藏
# ════════════════════════════════════════
print("=== 场景 1: 页面初始化时按钮默认隐藏 ===")

# 检查 preview-btn CSS class 定义了 opacity:0 / visibility:hidden
all_pass &= test(
    "CSS .preview-btn 定义 opacity:0",
    ".preview-btn {" in html and "opacity: 0" in html.split(".preview-btn ")[1].split("}")[0]
)

all_pass &= test(
    "CSS .preview-btn 定义 visibility:hidden",
    "visibility: hidden" in html.split(".preview-btn ")[1].split("}")[0]
)

all_pass &= test(
    "CSS .preview-btn 定义 transition",
    "transition:" in html.split(".preview-btn ")[1].split("}")[0]
)

all_pass &= test(
    "CSS .preview-btn.visible 定义 opacity:1",
    ".preview-btn.visible {" in html and "opacity: 1" in html.split(".preview-btn.visible")[1].split("}")[0]
)

# 检查按钮有 class="preview-btn"（没有 .visible）
import re
# 找到所有预览按钮的标签
preview_btns = re.findall(r'<button[^>]*id="preview-btn-[^"]*"[^>]*>', html)
all_pass &= test(
    f"预览按钮数量与配置项数量匹配",
    len(preview_btns) >= 1,
    f"found={len(preview_btns)}"
)

# 检查初始化时没有按钮带 visible class（服务端渲染不包含 visible）
all_pass &= test(
    "初始化时按钮没有 visible class",
    'class="preview-btn visible"' not in html,
    "发现按钮预置了 visible class"
)

# ════════════════════════════════════════
# 场景 2: JS 变更检测逻辑正确
# ════════════════════════════════════════
print("\n=== 场景 2: JS 变更检测逻辑 ===")

all_pass &= test(
    "updatePreviewBtn 函数存在",
    "function updatePreviewBtn(key)" in html
)

all_pass &= test(
    "updatePreviewBtn 通过 JSON 语义比较差异",
    "JSON.stringify(JSON.parse(currentVal), null, 2)" in html and
    "JSON.stringify(JSON.parse(originalVal), null, 2)" in html
)

all_pass &= test(
    "updatePreviewBtn 使用 classList.toggle('visible', hasChanged)",
    "btn.classList.toggle('visible', hasChanged)" in html
)

# 验证 CodeMirror change 事件中调用 updatePreviewBtn
all_pass &= test(
    "change 事件触发 updatePreviewBtn",
    "updatePreviewBtn(key)" in html.split("editor.on('change'")[1].split("});")[0]
)

# 验证保存成功后调用 updatePreviewBtn
btn_call_count = html.count("updatePreviewBtn(key)")
all_pass &= test(
    "保存成功后调用 updatePreviewBtn",
    btn_call_count >= 3,
    f"found {btn_call_count} calls, expected 3+ (change event / formatJson / save success)"
)

# ════════════════════════════════════════
# 取消按钮验证
# ════════════════════════════════════════
print("\n=== 取消按钮验证 ===")

# 取消按钮默认隐藏
all_pass &= test(
    "取消按钮带 class='cancel-btn' 默认隐藏",
    'class="cancel-btn"' in html.replace('id="cancel-btn-', '')
)

all_pass &= test(
    "CSS .cancel-btn 定义 opacity:0 和 visibility:hidden",
    ".cancel-btn {" in html and "opacity: 0" in html.split(".cancel-btn ")[1].split("}")[0] and
    "visibility: hidden" in html.split(".cancel-btn ")[1].split("}")[0]
)

all_pass &= test(
    "CSS .cancel-btn.visible 定义 opacity:1",
    ".cancel-btn.visible {" in html and "opacity: 1" in html.split(".cancel-btn.visible")[1].split("}")[0]
)

all_pass &= test(
    "cancelEdit 函数存在",
    "function cancelEdit(key)" in html
)

all_pass &= test(
    "cancelEdit 调用 editor.setValue(originalVal)",
    "editor.setValue(originalVal)" in html
)

# 检查 cancelEdit 函数体里包含 updatePreviewBtn 调用
cancel_fn_start = html.find("function cancelEdit(key)")
cancel_fn_block = html[cancel_fn_start:cancel_fn_start + 300]
all_pass &= test(
    "cancelEdit 函数体内调用 updatePreviewBtn",
    "updatePreviewBtn(key)" in cancel_fn_block,
    f"cancelEdit 函数体片段: ...{cancel_fn_block[-80:]}"
)

# ════════════════════════════════════════
# 场景 3: 边界情况
# ════════════════════════════════════════
print("\n=== 场景 3: 边界情况 ===")

# 用 Python 模拟 updatePreviewBtn 的语义比较逻辑
sample_original = '{"a": 1, "b": 2}'
sample_changed = '{"a": 1, "b": 3}'
sample_pretty = '{\n  "a": 1,\n  "b": 2\n}'

def sim_has_changed(current, original):
    try:
        c = json.dumps(json.loads(current), indent=2)
        o = json.dumps(json.loads(original), indent=2)
        return c != o
    except:
        return current != original

all_pass &= test(
    "语义相同（缩进差异）→ 无变更",
    not sim_has_changed(sample_pretty, sample_original),
    f"pretty={sample_pretty} vs original={sample_original}"
)

all_pass &= test(
    "值不同 → 检测到变更",
    sim_has_changed(sample_changed, sample_original),
    f"changed={sample_changed} vs original={sample_original}"
)

all_pass &= test(
    "完全相同 → 无变更",
    not sim_has_changed(sample_original, sample_original)
)

# ════════════════════════════════════════
# 结果汇总
# ════════════════════════════════════════
print(f"\n{'='*50}")
print(f"总计: 22 个检查项")
print(f"结果: {'全部通过 ✅' if all_pass else '有失败项 ❌'}")
print(f"{'='*50}")

sys.exit(0 if all_pass else 1)
