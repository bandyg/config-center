/* Kiosk Loading Manager
 * 状态机：idle → loading → (done | error)
 * 用法：
 *   Loading.start()   - 唤起遮罩
 *   Loading.track(p)  - 注册 Promise（成功/失败/超时都会解除）
 *   Loading.done()    - 立即销毁
 *   Loading.error(msg)- 销毁并显示错误
 */
(function (global) {
  const TIMEOUT_MS = 5000;

  const state = {
    active: false,
    count: 0,            // 未完成请求数
    timer: null,         // 超时定时器
    errorMode: false,
  };

  let overlayEl = null;
  let textEl = null;
  let spinnerEl = null;
  let errorEl = null;

  function ensureDOM() {
    if (overlayEl) return;
    overlayEl = document.createElement('div');
    overlayEl.id = 'kiosk-loading-overlay';
    overlayEl.setAttribute('data-state', 'idle');
    overlayEl.innerHTML =
      '<div class="kiosk-loading-box">' +
      '<div class="kiosk-loading-spinner"></div>' +
      '<div class="kiosk-loading-text">加载中，请稍候...</div>' +
      '<div class="kiosk-loading-error" style="display:none">' +
      '<div class="kiosk-loading-error-icon">⚠️</div>' +
      '<div class="kiosk-loading-error-msg"></div>' +
      '<button class="kiosk-loading-retry">关闭</button>' +
      '</div>' +
      '</div>';
    document.body.appendChild(overlayEl);
    textEl = overlayEl.querySelector('.kiosk-loading-text');
    spinnerEl = overlayEl.querySelector('.kiosk-loading-spinner');
    errorEl = overlayEl.querySelector('.kiosk-loading-error');
    overlayEl.querySelector('.kiosk-loading-retry').addEventListener('click', function () {
      hideAll();
    });
  }

  function showOverlay() {
    ensureDOM();
    state.active = true;
    state.errorMode = false;
    overlayEl.setAttribute('data-state', 'loading');
    overlayEl.style.display = 'flex';
    spinnerEl.style.display = 'block';
    textEl.style.display = 'block';
    textEl.textContent = '加载中，请稍候...';
    errorEl.style.display = 'none';
  }

  function hideAll() {
    state.active = false;
    state.count = 0;
    if (state.timer) { clearTimeout(state.timer); state.timer = null; }
    if (overlayEl) overlayEl.style.display = 'none';
    state.errorMode = false;
  }

  function startTimeout() {
    if (state.timer) clearTimeout(state.timer);
    state.timer = setTimeout(function () {
      // 超时：把残留请求都关掉
      state.count = 0;
      errorMode('请求超时（已等待 5 秒），请检查网络或服务状态');
    }, TIMEOUT_MS);
  }

  function errorMode(msg) {
    state.errorMode = true;
    state.active = false;            // 错误模式下不视为"loading"
    if (state.timer) { clearTimeout(state.timer); state.timer = null; }
    ensureDOM();
    overlayEl.setAttribute('data-state', 'error');
    spinnerEl.style.display = 'none';
    textEl.style.display = 'none';
    errorEl.style.display = 'block';
    errorEl.querySelector('.kiosk-loading-error-msg').textContent = msg;
  }

  const Loading = {
    start: function () {
      if (state.errorMode) return;        // 错误模式下不重新唤起
      showOverlay();
      startTimeout();
    },
    /** 注册一个 Promise；resolve / reject / 5s 超时都会让 count-1 */
    track: function (promise) {
      if (state.errorMode) return Promise.resolve();   // 错误模式：直接返回
      ensureDOM();
      state.count += 1;
      if (!state.active) showOverlay();
      startTimeout();
      // 用 Promise.resolve 把任何值包成 promise（统一处理）
      const p = Promise.resolve(promise);
      const done = function () {
        state.count -= 1;
        if (state.count <= 0 && !state.errorMode) {
          hideAll();
        }
      };
      p.then(done, done);
      return p;
    },
    done: function () {
      hideAll();
    },
    error: function (msg) {
      errorMode(msg || '操作失败');
    },
    // 给单测用
    _state: state,
    _isActive: function () { return state.active; },
    _isError: function () { return state.errorMode; },
    _getCount: function () { return state.count; },
    TIMEOUT_MS: TIMEOUT_MS,
  };

  global.Loading = Loading;
})(typeof window !== 'undefined' ? window : globalThis);
