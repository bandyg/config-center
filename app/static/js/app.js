/**
 * Kiosk Config Center — 前端工具模块
 * 提供 CodeMirror 集成、JSON 工具、Diff 预览等增强功能
 */

// ── CodeMirror JSON 编辑器 ──────────────────────────

/**
 * 为页面中所有配置编辑区初始化 CodeMirror 实例
 * 每个 .config-body 中的 textarea 会被替换为 CodeMirror 编辑器
 */
function initJsonEditors() {
  const editors = {};
  document.querySelectorAll('.config-body textarea').forEach(textarea => {
    const key = textarea.id.replace('edit-', '');
    const editor = CodeMirror.fromTextArea(textarea, {
      mode: { name: 'javascript', json: true },
      theme: 'default',
      lineNumbers: true,
      matchBrackets: true,
      indentUnit: 2,
      tabSize: 2,
      lineWrapping: true,
      foldGutter: true,
      gutters: ['CodeMirror-linenumbers', 'CodeMirror-foldgutter'],
      extraKeys: {
        'Ctrl-S': function (cm) { saveConfigFromEditor(key); },
        'Cmd-S': function (cm) { saveConfigFromEditor(key); },
        'Ctrl-F': function (cm) { showSearch(cm); },
        'Cmd-F': function (cm) { showSearch(cm); },
      }
    });
    editor.setSize(null, 300);
    editors[key] = editor;
  });
  return editors;
}

/**
 * 显示 CodeMirror 搜索框
 */
function showSearch(cm) {
  if (cm.getWrapperElement().querySelector('.cm-search')) return;
  const searchDiv = document.createElement('div');
  searchDiv.className = 'cm-search';
  searchDiv.innerHTML = `
    <input type="text" placeholder="搜索字段..." style="width:200px;padding:4px 8px;border:1px solid #ddd;border-radius:4px;font-size:13px;">
    <button onclick="this.parentElement.remove()" style="margin-left:4px;border:none;background:none;cursor:pointer;font-size:13px;color:#888">✕</button>
  `;
  cm.getWrapperElement().appendChild(searchDiv);
  const input = searchDiv.querySelector('input');
  input.addEventListener('input', function () {
    const val = this.value;
    if (!val) { cm.execCommand('clearSearch'); return; }
    const cursor = cm.getSearchCursor(val, { line: 0, ch: 0 });
    cm.setCursor(0, 0);
    while (cursor.findNext()) {
      // 高亮匹配项
    }
  });
  input.focus();
}

/**
 * 格式化当前 CodeMirror 编辑器中的 JSON
 */
function formatJson(key) {
  const editor = getEditor(key);
  if (!editor) return;
  try {
    const val = JSON.parse(editor.getValue());
    editor.setValue(JSON.stringify(val, null, 2));
    showMsg(key, '✅ JSON 格式化完成', '#1b7a1b');
  } catch (e) {
    showMsg(key, '❌ JSON 格式错误: ' + e.message, '#c41e1e');
  }
}

/**
 * 获取编辑器实例
 */
function getEditor(key) {
  return window.__codemirror_editors ? window.__codemirror_editors[key] : null;
}

/**
 * 从 CodeMirror 编辑器中读取值并保存
 */
async function saveConfigFromEditor(key) {
  const editor = getEditor(key);
  if (!editor) {
    // 降级到原来基于 textarea 的保存
    return saveConfigLegacy(key);
  }
  const ip = document.getElementById('edit-' + key)?.dataset?.ip;
  if (!ip) return;

  const msg = document.getElementById('msg-' + key);
  msg.textContent = '保存中...';
  msg.style.color = '#888';

  try {
    const val = JSON.parse(editor.getValue());
    const r = await fetch(`/api/proxy/${ip}/config/${key}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(val),
    });
    const result = await r.json();
    if (r.ok) {
      msg.textContent = '✅ 保存成功';
      msg.style.color = '#1b7a1b';
    } else {
      msg.textContent = '❌ ' + (result.detail || result.error || '保存失败');
      msg.style.color = '#c41e1e';
    }
  } catch (e) {
    msg.textContent = '❌ ' + e.message;
    msg.style.color = '#c41e1e';
  }
}

// ── JSON 树形浏览 ────────────────────────────────────

/**
 * 将 JSON 对象渲染为可展开/折叠的树形 HTML
 */
function renderJsonTree(data, maxDepth = 5) {
  function buildNode(val, key = '', depth = 0) {
    if (depth > maxDepth) return `<span class="json-truncated">...</span>`;

    const type = Array.isArray(val) ? 'array' : typeof val;

    if (val === null) return `<span class="json-null">null</span>`;
    if (type === 'string') return `<span class="json-string">"${escapeHtml(val)}"</span>`;
    if (type === 'number') return `<span class="json-number">${val}</span>`;
    if (type === 'boolean') return `<span class="json-boolean">${val}</span>`;

    if (type === 'object' || type === 'array') {
      const isArr = Array.isArray(val);
      const entries = isArr ? val : Object.keys(val);
      const len = entries.length;
      const bracket = isArr ? ['[', ']'] : ['{', '}'];

      if (len === 0) return `<span class="json-bracket">${bracket[0]}${bracket[1]}</span>`;

      let html = `<span class="json-toggle" onclick="this.classList.toggle('collapsed'); this.nextElementSibling.style.display = this.classList.contains('collapsed') ? 'none' : ''">▶</span>`;
      html += `<span class="json-bracket">${bracket[0]}</span>`;
      html += `<span class="json-children" style="display:inline">`;

      const items = isArr ? val : Object.entries(val);
      items.forEach((item, i) => {
        const k = isArr ? i : item[0];
        const v = isArr ? item : item[1];
        if (i > 0) html += `<span class="json-comma">,</span>`;
        html += `<div class="json-entry" style="padding-left:${(depth + 1) * 20}px">`;
        if (!isArr) {
          html += `<span class="json-key">"${escapeHtml(k)}"</span><span class="json-colon">: </span>`;
        }
        html += buildNode(v, k, depth + 1);
        html += `</div>`;
      });

      html += `</span>`;
      html += `<span class="json-bracket">${bracket[1]}</span>`;
      return html;
    }
    return String(val);
  }

  return buildNode(data);
}

function escapeHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Diff 预览 ────────────────────────────────────────

/**
 * 使用 diff-match-patch 计算两段文本的行级差异
 * 并返回带 HTML 着色的对比结果
 */
function computeDiff(oldText, newText) {
  if (typeof dmp === 'undefined') {
    return { html: '<p style="color:#888">Diff 库未加载</p>', hasDiff: false };
  }
  const dmpInstance = new dmp.diff_match_patch();
  const diffs = dmpInstance.diff_main(oldText, newText);
  dmpInstance.diff_cleanupSemantic(diffs);

  let html = '';
  let hasDiff = false;
  for (const [op, text] of diffs) {
    if (op === 0) {
      html += text.split('\n').map(line => escapeHtml(line)).join('\n');
    } else if (op === 1) {
      hasDiff = true;
      html += '<span class="diff-added">' + text.split('\n').map(line => escapeHtml(line)).join('\n') + '</span>';
    } else if (op === -1) {
      hasDiff = true;
      html += '<span class="diff-removed">' + text.split('\n').map(line => escapeHtml(line)).join('\n') + '</span>';
    }
  }
  return { html: html.replace(/\n/g, '<br>'), hasDiff };
}

// ── 辅助函数 ─────────────────────────────────────────

function showMsg(key, text, color) {
  const msg = document.getElementById('msg-' + key);
  if (msg) {
    msg.textContent = text;
    msg.style.color = color || '#888';
  }
}

// 保留旧的 textarea 保存方式作为降级
async function saveConfigLegacy(key) {
  const textarea = document.getElementById('edit-' + key);
  if (!textarea) return;
  const ip = textarea.dataset.ip;
  const msg = document.getElementById('msg-' + key);

  msg.textContent = '保存中...';
  msg.style.color = '#888';
  try {
    const val = JSON.parse(textarea.value);
    const r = await fetch(`/api/proxy/${ip}/config/${key}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(val),
    });
    msg.textContent = '✅ 保存成功';
    msg.style.color = '#1b7a1b';
  } catch (e) {
    msg.textContent = '❌ ' + e.message;
    msg.style.color = '#c41e1e';
  }
}
