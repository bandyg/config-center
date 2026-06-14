/**
 * Unit tests for Kiosk Loading Manager
 * Run: npx vitest run tests/loading.test.js
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// jsdom environment required
// Load the source as global
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'loading.js'), 'utf-8');

function loadModule() {
  // reset DOM
  document.body.innerHTML = '';
  // eval in current global context
  eval(src);
  return global.Loading;
}

describe('Kiosk Loading Manager', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('1) start() 唤起遮罩，进入 loading 状态', () => {
    const L = loadModule();
    expect(L._isActive()).toBe(false);
    L.start();
    expect(L._isActive()).toBe(true);
    const ov = document.getElementById('kiosk-loading-overlay');
    expect(ov).toBeTruthy();
    expect(ov.getAttribute('data-state')).toBe('loading');
  });

  it('2) track() 一个 promise，resolve 后销毁遮罩', async () => {
    const L = loadModule();
    const p = new Promise((res) => setTimeout(res, 100));
    L.track(p);
    expect(L._isActive()).toBe(true);
    expect(L._getCount()).toBe(1);
    vi.advanceTimersByTime(100);
    await Promise.resolve();
    await Promise.resolve();
    expect(L._getCount()).toBe(0);
    expect(L._isActive()).toBe(false);
  });

  it('3) 多接口并行：所有都完成后才销毁', async () => {
    const L = loadModule();
    const p1 = new Promise((res) => setTimeout(res, 100));
    const p2 = new Promise((res) => setTimeout(res, 200));
    const p3 = new Promise((res) => setTimeout(res, 300));
    L.track(p1); L.track(p2); L.track(p3);
    expect(L._getCount()).toBe(3);

    vi.advanceTimersByTime(150);
    await Promise.resolve(); await Promise.resolve();
    expect(L._getCount()).toBe(2);
    expect(L._isActive()).toBe(true);

    vi.advanceTimersByTime(100);
    await Promise.resolve(); await Promise.resolve();
    expect(L._getCount()).toBe(1);
    expect(L._isActive()).toBe(true);

    vi.advanceTimersByTime(100);
    await Promise.resolve(); await Promise.resolve();
    expect(L._getCount()).toBe(0);
    expect(L._isActive()).toBe(false);
  });

  it('4) 单接口 reject 也能正常销毁（不算入错误模式）', async () => {
    const L = loadModule();
    const p = Promise.reject(new Error('boom'));
    L.track(p);
    expect(L._isActive()).toBe(true);
    await Promise.resolve();
    await Promise.resolve();
    expect(L._getCount()).toBe(0);
    expect(L._isActive()).toBe(false);
    expect(L._isError()).toBe(false);
  });

  it('5) 5 秒超时自动关闭并显示错误', () => {
    const L = loadModule();
    // 永不 resolve
    const p = new Promise(() => {});
    L.track(p);
    expect(L._isActive()).toBe(true);
    vi.advanceTimersByTime(4999);
    expect(L._isActive()).toBe(true);
    vi.advanceTimersByTime(2);
    expect(L._isError()).toBe(true);
    expect(L._isActive()).toBe(false);
    const errMsg = document.querySelector('.kiosk-loading-error-msg').textContent;
    expect(errMsg).toContain('超时');
  });

  it('6) error() 立即进入错误模式', () => {
    const L = loadModule();
    L.start();
    L.error('自定义错误');
    expect(L._isError()).toBe(true);
    const errMsg = document.querySelector('.kiosk-loading-error-msg').textContent;
    expect(errMsg).toBe('自定义错误');
  });

  it('7) 错误模式下 start() 不重新唤起（避免覆盖错误信息）', () => {
    const L = loadModule();
    L.start();
    L.error('X');
    L.start();
    // 仍处于错误模式
    expect(L._isError()).toBe(true);
    const errMsg = document.querySelector('.kiosk-loading-error-msg').textContent;
    expect(errMsg).toBe('X');
  });

  it('8) done() 立即销毁（即便 count 不为 0）', () => {
    const L = loadModule();
    L.track(new Promise(() => {}));
    L.track(new Promise(() => {}));
    expect(L._getCount()).toBe(2);
    L.done();
    expect(L._isActive()).toBe(false);
  });

  it('9) 错误提示上的"关闭"按钮可手动清除', () => {
    const L = loadModule();
    L.error('X');
    const btn = document.querySelector('.kiosk-loading-retry');
    btn.click();
    // 关闭后错误模式解除（下次 start 可重新进入）
    expect(L._isError()).toBe(false);
  });

  it('10) 超时后新增的 track() 不会复活 loading', () => {
    const L = loadModule();
    L.track(new Promise(() => {}));
    vi.advanceTimersByTime(5000);
    expect(L._isError()).toBe(true);
    L.track(Promise.resolve());
    // 仍处于错误模式
    expect(L._isError()).toBe(true);
  });
});
