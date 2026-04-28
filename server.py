#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
copy-board 服务器
- GET  /           -> 前端展示页
- GET  /admin      -> 管理后台（需密码）
- GET  /api/items  -> 获取所有条目 JSON
- POST /api/items  -> 新增条目
- PUT  /api/items/<id> -> 修改条目
- DELETE /api/items/<id> -> 删除条目
- POST /api/login  -> 验证管理员密码
"""

import json
import os
import uuid
import hashlib
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

# ========== 配置 ==========
PORT = int(os.environ.get("PORT", "8899"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "items.json")
MAX_BODY_SIZE = 1024 * 1024  # 1MB
# ==========================

# File I/O lock for thread safety
_data_lock = threading.Lock()


def read_data():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[WARN] Data file corrupted: {e}, returning empty list")
        # Backup corrupted file
        backup_file = DATA_FILE + ".corrupted." + datetime.now().strftime("%Y%m%d%H%M%S")
        try:
            os.rename(DATA_FILE, backup_file)
            print(f"[INFO] Corrupted file backed up to: {backup_file}")
        except Exception:
            pass
        return []


def write_data(items):
    # Ensure directory exists
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    # Atomic write: write to temp file then rename
    temp_file = DATA_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, DATA_FILE)


def get_next_id(items):
    if not items:
        return 1
    return max(item["id"] for item in items) + 1


# ========== HTML 页面 ==========

INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="format-detection" content="telephone=no">
<title>小红书素材文案</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", sans-serif;
    background: #fff5f7;
    min-height: 100vh;
    padding-bottom: env(safe-area-inset-bottom);
  }

  /* 顶部 */
  .header {
    background: linear-gradient(160deg, #ff6b9d 0%, #ff9ebf 60%, #ffb8d0 100%);
    padding: 22px 16px 18px;
    text-align: center;
    position: relative;
    overflow: hidden;
  }
  .header::before {
    content: '';
    position: absolute;
    width: 140px; height: 140px;
    background: rgba(255,255,255,0.12);
    border-radius: 50%;
    top: -50px; right: -30px;
    pointer-events: none;
  }
  .header-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: relative;
    z-index: 1;
  }
  .header-title-block { flex: 1; text-align: center; }
  .header-tag {
    display: inline-block;
    background: rgba(255,255,255,0.28);
    color: #fff;
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 6px;
    letter-spacing: 1px;
  }
  .header h1 {
    font-size: 20px;
    font-weight: 700;
    color: #fff;
    letter-spacing: 1px;
    text-shadow: 0 1px 6px rgba(180,60,90,0.18);
  }
  .header p {
    font-size: 12px;
    color: rgba(255,255,255,0.88);
    margin-top: 4px;
  }
  /* 换一条按钮 */
  .btn-change {
    background: rgba(255,255,255,0.22);
    border: 1.5px solid rgba(255,255,255,0.5);
    color: #fff;
    font-size: 12px;
    font-weight: 600;
    padding: 7px 12px;
    border-radius: 20px;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    white-space: nowrap;
    transition: background 0.15s;
    flex-shrink: 0;
  }
  .btn-change:active { background: rgba(255,255,255,0.38); }
  .btn-change.spinning { opacity: 0.6; pointer-events: none; }
  /* 剩余数量 */
  .count-badge {
    background: rgba(255,255,255,0.22);
    border: 1.5px solid rgba(255,255,255,0.4);
    color: rgba(255,255,255,0.9);
    font-size: 11px;
    padding: 5px 10px;
    border-radius: 20px;
    flex-shrink: 0;
    min-width: 52px;
    text-align: center;
  }

  /* 主区域 */
  .main { padding: 16px 14px 100px; }

  /* 卡片 */
  .card {
    background: #fff;
    border-radius: 22px;
    padding: 20px 18px 18px;
    box-shadow: 0 6px 24px rgba(255,107,157,0.12), 0 1px 4px rgba(0,0,0,0.04);
    position: relative;
    overflow: hidden;
    animation: slideUp 0.35s cubic-bezier(.34,1.56,.64,1);
  }
  @keyframes slideUp {
    from { opacity: 0; transform: translateY(22px) scale(0.97); }
    to   { opacity: 1; transform: translateY(0) scale(1); }
  }
  .card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 4px;
    background: linear-gradient(90deg, #ff6b9d, #ffb347, #ff6b9d);
    background-size: 200% 100%;
    animation: shimmer 3s linear infinite;
  }
  @keyframes shimmer {
    0% { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  /* 步骤引导 */
  .steps {
    display: flex;
    gap: 8px;
    margin-bottom: 18px;
    margin-top: 4px;
  }
  .step {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    padding: 10px 6px 8px;
    border-radius: 14px;
    background: #fff5f9;
    border: 1.5px solid #ffd6e7;
    transition: all 0.2s;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
  }
  .step.active {
    background: linear-gradient(135deg, #fff0f5, #ffe4ef);
    border-color: #ff9ebf;
    box-shadow: 0 2px 10px rgba(255,107,157,0.15);
    transform: translateY(-1px);
  }
  .step.done {
    background: linear-gradient(135deg, #f0fff6, #e4ffee);
    border-color: #7ee8a2;
  }
  .step-num {
    width: 24px; height: 24px;
    border-radius: 50%;
    background: #ffd6e7;
    color: #d94f7e;
    font-size: 12px; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.2s;
  }
  .step.active .step-num {
    background: linear-gradient(135deg, #ff6b9d, #ff9ebf);
    color: #fff;
  }
  .step.done .step-num {
    background: linear-gradient(135deg, #52c98b, #7ee8a2);
    color: #fff;
  }
  .step-label { font-size: 11px; color: #b06080; font-weight: 500; text-align: center; line-height: 1.3; }
  .step.active .step-label { color: #d94f7e; }
  .step.done .step-label { color: #3a9e6a; }

  /* 连接线 */
  .step-connector {
    width: 20px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    padding-top: 2px;
    color: #ffc0d5;
    font-size: 14px;
  }

  /* 内容展示 */
  .card-title {
    font-size: 17px;
    font-weight: 700;
    color: #2d1a24;
    margin-bottom: 12px;
    line-height: 1.5;
    padding-bottom: 12px;
    border-bottom: 1px dashed #ffd6e7;
  }
  .card-content {
    font-size: 14px;
    color: #5a3d4a;
    line-height: 1.85;
    white-space: pre-wrap;
    word-break: break-all;
    margin-bottom: 6px;
  }
  .location-tag {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: #fff0f5;
    border: 1px solid #ffd6e7;
    color: #d94f7e;
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 20px;
    margin-top: 10px;
  }

  /* 操作按钮区 */
  .actions { margin-top: 18px; display: flex; flex-direction: column; gap: 10px; }
  .btn-step {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    width: 100%; padding: 13px;
    border: none; border-radius: 40px;
    font-size: 15px; font-weight: 600;
    cursor: pointer; -webkit-tap-highlight-color: transparent;
    transition: transform 0.1s, opacity 0.1s, box-shadow 0.2s;
    letter-spacing: 0.5px;
  }
  .btn-step:active { transform: scale(0.97); opacity: 0.88; }
  .btn-step.pink {
    background: linear-gradient(135deg, #ff6b9d 0%, #ff9ebf 100%);
    color: #fff;
    box-shadow: 0 4px 16px rgba(255,107,157,0.35);
  }
  .btn-step.green {
    background: linear-gradient(135deg, #52c98b 0%, #7ee8a2 100%);
    color: #fff;
    box-shadow: 0 4px 16px rgba(82,201,139,0.35);
  }
  .btn-step.gray {
    background: #f7e8ef;
    color: #c080a0;
    box-shadow: none;
  }
  .btn-step.disabled { opacity: 0.45; pointer-events: none; }

  /* 进度提示 */
  .progress-hint {
    text-align: center;
    font-size: 13px;
    color: #e8a0bc;
    padding: 10px 0 4px;
  }
  .progress-hint b { color: #d94f7e; }

  /* 完成状态 */
  .done-card {
    text-align: center;
    padding: 50px 20px 40px;
    animation: slideUp 0.4s ease;
  }
  .done-icon { font-size: 56px; margin-bottom: 16px; }
  .done-title { font-size: 18px; font-weight: 700; color: #2d1a24; margin-bottom: 8px; }
  .done-sub { font-size: 14px; color: #b06080; line-height: 1.7; }
  .done-tips {
    background: #fff0f5;
    border-radius: 14px;
    padding: 14px 16px;
    margin-top: 20px;
    text-align: left;
  }
  .done-tips-title { font-size: 13px; font-weight: 700; color: #d94f7e; margin-bottom: 8px; }
  .done-tips li { font-size: 13px; color: #7a4d61; line-height: 1.8; list-style: none; padding-left: 4px; }
  .done-tips li::before { content: "🌸 "; }
  .btn-next {
    display: flex; align-items: center; justify-content: center; gap: 6px;
    width: 100%; margin-top: 20px; padding: 13px;
    background: linear-gradient(135deg, #ff6b9d 0%, #ff9ebf 100%);
    color: #fff; border: none; border-radius: 40px;
    font-size: 15px; font-weight: 600; cursor: pointer;
    box-shadow: 0 4px 16px rgba(255,107,157,0.35);
    -webkit-tap-highlight-color: transparent;
  }

  /* 空态 */
  .empty { text-align: center; padding: 70px 20px; color: #e8a0bc; font-size: 15px; }
  .empty-icon { font-size: 52px; margin-bottom: 14px; }
  .empty-title { font-size: 17px; font-weight: 700; color: #d94f7e; margin-bottom: 8px; }
  .empty-sub { font-size: 13px; color: #b06080; line-height: 1.7; }

  /* Toast */
  .toast {
    position: fixed; bottom: 70px; left: 50%;
    transform: translateX(-50%) translateY(16px);
    background: rgba(255,107,157,0.93);
    color: #fff; padding: 10px 24px; border-radius: 30px;
    font-size: 14px; font-weight: 500;
    pointer-events: none; opacity: 0;
    transition: all 0.25s cubic-bezier(.34,1.56,.64,1);
    z-index: 999; white-space: nowrap;
    box-shadow: 0 4px 16px rgba(255,107,157,0.3);
  }
  .toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
</style>
</head>
<body>

<div class="header">
  <div class="header-top">
    <div class="count-badge" id="countBadge">···</div>
    <div class="header-title-block">
      <div class="header-tag">✨ 小红书素材</div>
      <h1>🌸 文案素材库</h1>
    </div>
    <button class="btn-change" id="btnChange" onclick="changeItem()">🔄 换一条</button>
  </div>
  <p style="margin-top:8px;position:relative;z-index:1;">按步骤复制，直接去发帖吧～</p>
</div>

<div class="main" id="main">
  <div class="empty"><div class="empty-icon">🌸</div>加载中...</div>
</div>

<div class="toast" id="toast"></div>

<script>
const LOCATION = '📍 白月清川国风妆造工作室';
let currentItem = null;
let step = 0; // 0=未开始, 1=已复制标题, 2=已复制文案(销毁完成)

/* ---- 工具 ---- */
function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
async function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
  } else {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;width:1px;height:1px';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
}
function showToast(msg, duration=2400) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}
function setCount(n) {
  const b = document.getElementById('countBadge');
  b.textContent = n === null ? '···' : (n + ' 条');
}

/* ---- 加载随机素材 ---- */
async function loadRandom(excludeId) {
  step = 0;
  currentItem = null;
  const mainEl = document.getElementById('main');
  mainEl.innerHTML = '<div class="empty"><div class="empty-icon">🌸</div>加载中...</div>';

  try {
    const url = excludeId != null ? '/zhongcao/api/random?exclude=' + excludeId : '/zhongcao/api/random';
    const res = await fetch(url);
    const data = await res.json();
    setCount(data.total != null ? data.total : null);

    if (!data.item) {
      showEmpty();
      return;
    }
    currentItem = data.item;
    renderCard();
  } catch(e) {
    mainEl.innerHTML = '<div class="empty"><div class="empty-icon">😢</div><div class="empty-title">加载失败</div><div class="empty-sub">请刷新重试</div></div>';
  }
}

function showEmpty() {
  setCount(0);
  document.getElementById('main').innerHTML = `
    <div class="empty">
      <div class="empty-icon">🌷</div>
      <div class="empty-title">素材已全部用完啦</div>
      <div class="empty-sub">感谢你的支持，新素材补充中～<br>记得关注我们的小红书哦！</div>
    </div>`;
  document.getElementById('btnChange').classList.add('disabled');
}

/* ---- 渲染卡片 ---- */
function renderCard() {
  const item = currentItem;
  const mainEl = document.getElementById('main');
  // 文案末尾加位置
  const fullContent = item.content + '\\n\\n' + LOCATION;

  mainEl.innerHTML = `
    <div class="card" id="card">
      <!-- 步骤引导 -->
      <div class="steps">
        <div class="step ${step===0?'active':step>=1?'done':''}" id="step1">
          <div class="step-num">${step>=1?'✓':'1'}</div>
          <div class="step-label">复制<br>标题</div>
        </div>
        <div class="step-connector">›</div>
        <div class="step ${step===1?'active':step>=2?'done':''}" id="step2">
          <div class="step-num">${step>=2?'✓':'2'}</div>
          <div class="step-label">复制<br>文案</div>
        </div>
        <div class="step-connector">›</div>
        <div class="step ${step===2?'active':''}" id="step3">
          <div class="step-num">3</div>
          <div class="step-label">去小红书<br>发帖！</div>
        </div>
      </div>

      <!-- 内容预览 -->
      <div class="card-title" id="cardTitle">${escHtml(item.title)}</div>
      <div class="card-content" id="cardContent">${escHtml(item.content)}</div>
      <div class="location-tag">📍 白月清川国风妆造工作室</div>

      <!-- 操作按钮 -->
      <div class="actions">
        <button class="btn-step ${step===0?'pink':'gray'}" id="btnStep1" onclick="doCopyTitle()">
          <span>📋</span><span>${step>=1?'✅ 标题已复制':'第一步：复制标题'}</span>
        </button>
        <button class="btn-step ${step===1?'pink':'gray'} ${step<1?'disabled':''}" id="btnStep2" onclick="doCopyContent()">
          <span>📋</span><span>${step>=2?'✅ 文案已复制':'第二步：复制文案+位置'}</span>
        </button>
      </div>

      <p class="progress-hint" id="progressHint">${
        step===0 ? '👆 先把标题复制，粘贴到小红书标题框，再回来复制文案' :
        step===1 ? '👆 文案复制好了，记得加上店铺位置（白月清川国风妆造工作室）' :
        '🎉 两步完成！去小红书发帖吧～'
      }</p>
    </div>`;
}

/* ---- 步骤一：复制标题 ---- */
async function doCopyTitle() {
  if (!currentItem || step !== 0) return;
  try {
    await copyText(currentItem.title);
    step = 1;
    renderCard();
    showToast('可以去小红书粘贴标题啦，记得回来粘贴文案哦');
  } catch(e) {
    showToast('❌ 复制失败，请长按手动复制');
  }
}

/* ---- 步骤二：复制文案（附位置），然后销毁 ---- */
async function doCopyContent() {
  if (!currentItem || step !== 1) return;
  const fullContent = currentItem.content + '\\n\\n' + LOCATION;
  try {
    await copyText(fullContent);
    // 通知后端销毁
    const id = currentItem.id;
    fetch('/zhongcao/api/use/' + id, { method: 'POST' }).catch(()=>{});
    step = 2;
    showDone();
    showToast('可以去小红书粘贴正文啦，一定要记得在下方添加店铺位置！（搜：白月清川国风妆造工作室）', 3200);
  } catch(e) {
    showToast('❌ 复制失败，请长按手动复制');
  }
}

/* ---- 完成页 ---- */
function showDone() {
  document.getElementById('main').innerHTML = `
    <div class="done-card">
      <div class="done-icon">🎉</div>
      <div class="done-title">大功告成！去发帖吧～</div>
      <div class="done-sub">标题 & 文案已分别复制到剪贴板<br>打开小红书，粘贴发布即可 🌸</div>
      <div class="done-tips">
        <div class="done-tips-title">📱 发帖小贴士</div>
        <ul>
          <li>先粘贴标题到小红书标题框</li>
          <li>再返回复制文案，粘贴到正文</li>
          <li>加上你的美美照片，发布！</li>
          <li>地点已自动带入：白月清川国风妆造工作室</li>
        </ul>
      </div>
      <button class="btn-next" onclick="loadRandom(null)">🌷 再来一条新素材</button>
    </div>`;
}

/* ---- 换一条 ---- */
function changeItem() {
  const btn = document.getElementById('btnChange');
  btn.classList.add('spinning');
  const excludeId = currentItem ? currentItem.id : null;
  loadRandom(excludeId).finally(() => {
    setTimeout(() => btn.classList.remove('spinning'), 400);
  });
}

/* ---- 初始化 ---- */
loadRandom(null);
</script>
</body>
</html>"""


ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>小红书素材管理</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
    background: #fff5f7;
    min-height: 100vh;
  }
  .header {
    background: linear-gradient(160deg, #ff6b9d 0%, #ff9ebf 100%);
    padding: 14px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky; top: 0; z-index: 10;
    box-shadow: 0 2px 10px rgba(255,107,157,0.25);
  }
  .header h1 { font-size: 17px; font-weight: 700; color: #fff; }
  .header a {
    font-size: 13px; color: rgba(255,255,255,0.9);
    text-decoration: none;
    background: rgba(255,255,255,0.2);
    padding: 5px 12px; border-radius: 20px;
  }

  /* 登录 */
  .login-wrap {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; min-height: 88vh; padding: 20px;
    background: linear-gradient(160deg, #fff0f5 0%, #ffe8f0 100%);
  }
  .login-box {
    background: #fff; border-radius: 24px; padding: 32px 24px;
    width: 100%; max-width: 360px;
    box-shadow: 0 8px 32px rgba(255,107,157,0.18);
  }
  .login-logo { text-align: center; font-size: 44px; margin-bottom: 8px; }
  .login-box h2 { text-align: center; font-size: 20px; margin-bottom: 4px; color: #2d1a24; font-weight: 700; }
  .login-sub { text-align: center; font-size: 13px; color: #e8a0bc; margin-bottom: 24px; }
  .form-item { margin-bottom: 14px; }
  .form-item label { display: block; font-size: 13px; color: #b06080; margin-bottom: 5px; font-weight: 500; }
  .form-item input, .form-item textarea {
    width: 100%; padding: 12px 14px;
    border: 1.5px solid #ffd6e7; border-radius: 12px;
    font-size: 15px; outline: none; transition: border-color 0.2s;
    font-family: inherit; color: #2d1a24;
    background: #fff9fb;
  }
  .form-item input:focus, .form-item textarea:focus {
    border-color: #ff6b9d;
    background: #fff;
    box-shadow: 0 0 0 3px rgba(255,107,157,0.10);
  }
  .form-item textarea { min-height: 110px; resize: vertical; }

  .btn {
    width: 100%; padding: 13px;
    background: linear-gradient(135deg, #ff6b9d 0%, #ff9ebf 100%);
    color: #fff; border: none; border-radius: 40px;
    font-size: 16px; font-weight: 600; cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    box-shadow: 0 4px 14px rgba(255,107,157,0.32);
    transition: opacity 0.15s, transform 0.1s;
    letter-spacing: 0.5px;
  }
  .btn:active { opacity: 0.85; transform: scale(0.98); }
  .btn.danger {
    background: linear-gradient(135deg, #ff6b6b 0%, #ffa0a0 100%);
    box-shadow: 0 4px 14px rgba(255,107,107,0.25);
  }
  .btn.small { font-size: 13px; padding: 7px 14px; width: auto; border-radius: 20px; }
  .btn.ghost {
    background: #fff0f5; color: #ff6b9d; border: 1.5px solid #ffd6e7;
    box-shadow: none;
  }

  /* 后台主体 */
  #main { display: none; }
  .add-section {
    background: #fff; margin: 12px 12px 8px; border-radius: 20px; padding: 18px 16px;
    box-shadow: 0 4px 16px rgba(255,107,157,0.10);
  }
  .add-section h3 { font-size: 15px; font-weight: 700; margin-bottom: 14px; color: #d94f7e; }
  .item-list { padding: 0 12px 80px; }
  .section-title { font-size: 13px; color: #e8a0bc; padding: 10px 4px 8px; font-weight: 500; }

  .item-card {
    background: #fff; border-radius: 18px; padding: 16px; margin-bottom: 10px;
    box-shadow: 0 3px 12px rgba(255,107,157,0.09);
    border-left: 4px solid #ffb3ce;
    position: relative;
  }
  .item-card .title { font-size: 15px; font-weight: 700; color: #2d1a24; margin-bottom: 6px; }
  .item-card .content {
    font-size: 13px; color: #7a4d61; line-height: 1.65;
    white-space: pre-wrap; word-break: break-all;
    max-height: 72px; overflow: hidden;
  }
  .item-actions { display: flex; gap: 8px; margin-top: 12px; }

  /* 弹窗 */
  .modal-mask {
    display: none; position: fixed; inset: 0;
    background: rgba(100,20,50,0.35); z-index: 100;
    align-items: flex-end; justify-content: center;
    backdrop-filter: blur(2px);
  }
  .modal-mask.show { display: flex; }
  .modal {
    background: #fff; border-radius: 24px 24px 0 0; padding: 22px 16px 44px;
    width: 100%; max-width: 600px; max-height: 90vh; overflow-y: auto;
    box-shadow: 0 -4px 30px rgba(255,107,157,0.15);
  }
  .modal h3 { font-size: 16px; font-weight: 700; margin-bottom: 16px; color: #d94f7e; }
  .modal-actions { display: flex; gap: 10px; margin-top: 14px; }

  .err { color: #ff6b9d; font-size: 13px; margin-top: 8px; }

  /* 批量导入 */
  .import-section {
    background: linear-gradient(135deg, #fff0f8 0%, #ffe8f3 100%);
    margin: 12px 12px 8px; border-radius: 20px; padding: 18px 16px;
    box-shadow: 0 4px 16px rgba(255,107,157,0.10);
    border: 2px dashed #ffd6e7;
  }
  .import-section h3 { font-size: 15px; font-weight: 700; margin-bottom: 12px; color: #d94f7e; }
  .import-section .file-input-wrap {
    position: relative; overflow: hidden; display: inline-block; width: 100%;
  }
  .import-section input[type="file"] {
    position: absolute; left: 0; top: 0; opacity: 0; width: 100%; height: 100%; cursor: pointer;
  }
  .import-section .file-btn {
    display: block; width: 100%; padding: 14px;
    background: #fff; border: 2px dashed #ffb3ce; border-radius: 14px;
    text-align: center; color: #d94f7e; font-size: 14px; font-weight: 500;
    transition: all 0.2s; cursor: pointer;
  }
  .import-section .file-btn:hover { background: #fff5f9; border-color: #ff6b9d; }
  .import-section .file-name { font-size: 12px; color: #b06080; margin-top: 8px; text-align: center; }
  .import-progress { margin-top: 12px; }
  .import-progress-bar {
    height: 8px; background: #ffe8f0; border-radius: 4px; overflow: hidden;
  }
  .import-progress-bar-inner {
    height: 100%; background: linear-gradient(90deg, #ff6b9d, #ff9ebf);
    width: 0%; transition: width 0.3s ease; border-radius: 4px;
  }
  .import-progress-text { font-size: 12px; color: #b06080; margin-top: 6px; text-align: center; }
  .import-result { margin-top: 10px; font-size: 13px; line-height: 1.7; }
  .import-result .ok { color: #52c98b; }
  .import-result .fail { color: #ff6b6b; }
  .import-hint {
    font-size: 12px; color: #c080a0; margin-top: 10px;
    background: rgba(255,255,255,0.6); padding: 10px 12px; border-radius: 10px;
  }
  .import-hint code { background: #ffe8f0; padding: 1px 5px; border-radius: 4px; font-size: 11px; }
</style>
<script src="https://cdn.sheetjs.com/xlsx-0.20.1/package/dist/xlsx.full.min.js"></script>
</head>
<body>

<!-- 登录页 -->
<div id="loginPage">
  <div class="login-wrap">
    <div class="login-box">
      <div class="login-logo">🌸</div>
      <h2>素材管理后台</h2>
      <p class="login-sub">小红书文案管理专用</p>
      <div class="form-item">
        <label>管理员密码</label>
        <input type="password" id="pwdInput" placeholder="请输入密码～" onkeydown="if(event.key==='Enter')doLogin()">
      </div>
      <p class="err" id="loginErr"></p>
      <br>
      <button class="btn" onclick="doLogin()">🔑 登录后台</button>
    </div>
  </div>
</div>

<!-- 主界面 -->
<div id="main">
  <div class="header">
    <h1>🌸 素材管理</h1>
    <a href="/zhongcao/">查看前端 →</a>
  </div>

  <!-- 新增表单 -->
  <div class="add-section">
    <h3>✨ 新增文案素材</h3>
    <div class="form-item">
      <label>标题</label>
      <input type="text" id="newTitle" placeholder="写个吸引眼球的标题～">
    </div>
    <div class="form-item">
      <label>文案内容</label>
      <textarea id="newContent" placeholder="输入正文文案，支持换行…"></textarea>
    </div>
    <p class="err" id="addErr"></p>
    <button class="btn" onclick="addItem()">🌷 保存发布</button>
  </div>

  <!-- 批量导入 -->
  <div class="import-section">
    <h3>📥 批量导入素材（Excel）</h3>
    <div class="file-input-wrap">
      <div class="file-btn" id="fileBtn">点击选择 .xlsx 文件</div>
      <input type="file" id="importFile" accept=".xlsx,.xls" onchange="onFileSelected(this)">
    </div>
    <p class="file-name" id="fileName"></p>
    <button class="btn" id="btnImport" onclick="doBatchImport()" style="margin-top:10px;display:none;">📥 开始导入</button>
    <div class="import-progress" id="importProgress" style="display:none;">
      <div class="import-progress-bar"><div class="import-progress-bar-inner" id="progressBar"></div></div>
      <p class="import-progress-text" id="progressText">准备导入...</p>
    </div>
    <div class="import-result" id="importResult"></div>
    <div class="import-hint">
      💡 Excel 格式要求：<br>
      • 第 1 列：<code>序号</code>（不导入，仅参考）<br>
      • 第 2 列：<code>标题</code>（必填）<br>
      • 第 3 列：<code>正文</code>（必填）<br>
      • 从第 2 行开始读取（第 1 行为表头）
    </div>
  </div>

  <!-- 列表 -->
  <div class="item-list">
    <p class="section-title" id="listCount">加载中…</p>
    <div id="itemListEl"></div>
  </div>
</div>

<!-- 编辑弹窗 -->
<div class="modal-mask" id="editModal">
  <div class="modal">
    <h3>✏️ 编辑文案</h3>
    <input type="hidden" id="editId">
    <div class="form-item">
      <label>标题</label>
      <input type="text" id="editTitle" placeholder="标题">
    </div>
    <div class="form-item">
      <label>文案内容</label>
      <textarea id="editContent" placeholder="内容"></textarea>
    </div>
    <p class="err" id="editErr"></p>
    <div class="modal-actions">
      <button class="btn ghost" style="flex:1" onclick="closeEdit()">取消</button>
      <button class="btn" style="flex:2" onclick="saveEdit()">💾 保存</button>
    </div>
  </div>
</div>

<script>
let token = sessionStorage.getItem('admin_token') || '';

async function doLogin() {
  const pwd = document.getElementById('pwdInput').value.trim();
  if (!pwd) { document.getElementById('loginErr').textContent = '请输入密码'; return; }
  const res = await fetch('/zhongcao/api/login', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({password: pwd})
  });
  const data = await res.json();
  if (data.ok) {
    token = data.token;
    sessionStorage.setItem('admin_token', token);
    showMain();
  } else {
    document.getElementById('loginErr').textContent = '密码错误';
  }
}

function showMain() {
  document.getElementById('loginPage').style.display = 'none';
  document.getElementById('main').style.display = 'block';
  loadItems();
}

// 如果已有token，直接尝试加载
if (token) {
  fetch('/zhongcao/api/items').then(r => r.ok ? showMain() : null);
}

async function loadItems() {
  const res = await fetch('/zhongcao/api/items');
  const items = await res.json();
  document.getElementById('listCount').textContent = `共 ${items.length} 条文案`;
  const el = document.getElementById('itemListEl');
  if (!items.length) { el.innerHTML = '<p style="text-align:center;color:#999;padding:30px">暂无内容</p>'; return; }
  el.innerHTML = items.map(item => `
    <div class="item-card">
      <div class="title">${escHtml(item.title)}</div>
      <div class="content">${escHtml(item.content)}</div>
      <div class="item-actions">
        <button class="btn small" onclick="openEdit(${item.id})">✏️ 编辑</button>
        <button class="btn small danger" onclick="deleteItem(${item.id})">🗑 删除</button>
      </div>
    </div>
  `).join('');
}

async function addItem() {
  const title = document.getElementById('newTitle').value.trim();
  const content = document.getElementById('newContent').value.trim();
  document.getElementById('addErr').textContent = '';
  if (!title) { document.getElementById('addErr').textContent = '请填写标题'; return; }
  if (!content) { document.getElementById('addErr').textContent = '请填写内容'; return; }
  const res = await fetch('/zhongcao/api/items', {
    method: 'POST',
    headers: {'Content-Type':'application/json','X-Token':token},
    body: JSON.stringify({title, content})
  });
  const data = await res.json();
  if (data.ok) {
    document.getElementById('newTitle').value = '';
    document.getElementById('newContent').value = '';
    loadItems();
  } else {
    document.getElementById('addErr').textContent = data.error || '保存失败';
  }
}

let currentItems = [];
async function openEdit(id) {
  const res = await fetch('/zhongcao/api/items');
  const items = await res.json();
  const item = items.find(i => i.id === id);
  if (!item) return;
  document.getElementById('editId').value = id;
  document.getElementById('editTitle').value = item.title;
  document.getElementById('editContent').value = item.content;
  document.getElementById('editErr').textContent = '';
  document.getElementById('editModal').classList.add('show');
}

function closeEdit() {
  document.getElementById('editModal').classList.remove('show');
}

async function saveEdit() {
  const id = parseInt(document.getElementById('editId').value);
  const title = document.getElementById('editTitle').value.trim();
  const content = document.getElementById('editContent').value.trim();
  document.getElementById('editErr').textContent = '';
  if (!title) { document.getElementById('editErr').textContent = '标题不能为空'; return; }
  if (!content) { document.getElementById('editErr').textContent = '内容不能为空'; return; }
  const res = await fetch('/zhongcao/api/items/' + id, {
    method: 'PUT',
    headers: {'Content-Type':'application/json','X-Token':token},
    body: JSON.stringify({title, content})
  });
  const data = await res.json();
  if (data.ok) { closeEdit(); loadItems(); }
  else { document.getElementById('editErr').textContent = data.error || '保存失败'; }
}

async function deleteItem(id) {
  if (!confirm('确认删除这条文案？')) return;
  const res = await fetch('/zhongcao/api/items/' + id, {
    method: 'DELETE',
    headers: {'X-Token': token}
  });
  const data = await res.json();
  if (data.ok) loadItems();
  else alert(data.error || '删除失败');
}

/* ---- 批量导入 ---- */
let pendingRows = [];

function onFileSelected(input) {
  const file = input.files[0];
  if (!file) return;
  document.getElementById('fileName').textContent = '已选择: ' + file.name;
  document.getElementById('btnImport').style.display = 'block';
  document.getElementById('importResult').innerHTML = '';
  document.getElementById('importProgress').style.display = 'none';
  pendingRows = [];

  const reader = new FileReader();
  reader.onload = function(e) {
    try {
      const data = new Uint8Array(e.target.result);
      const workbook = XLSX.read(data, { type: 'array' });
      const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
      const jsonData = XLSX.utils.sheet_to_json(firstSheet, { header: 1 });

      // 跳过表头（第1行），从第2行开始
      pendingRows = [];
      for (let i = 1; i < jsonData.length; i++) {
        const row = jsonData[i];
        if (!row || row.length < 2) continue;
        // 第2列=标题(索引1)，第3列=正文(索引2)
        const title = String(row[1] || '').trim();
        const content = String(row[2] || '').trim();
        if (title && content) {
          pendingRows.push({ title, content, rowNum: i + 1 });
        }
      }

      document.getElementById('importResult').innerHTML =
        `<span class="ok">✅ 解析成功，共 ${pendingRows.length} 条有效数据</span>`;
    } catch (err) {
      document.getElementById('importResult').innerHTML =
        `<span class="fail">❌ 解析失败: ${escHtml(err.message)}</span>`;
      pendingRows = [];
    }
  };
  reader.readAsArrayBuffer(file);
}

async function doBatchImport() {
  if (!pendingRows.length) {
    alert('没有可导入的数据，请先选择 Excel 文件');
    return;
  }
  if (!token) {
    alert('请先登录管理后台');
    return;
  }

  const btn = document.getElementById('btnImport');
  btn.disabled = true;
  btn.textContent = '⏳ 导入中...';

  const progressWrap = document.getElementById('importProgress');
  const progressBar = document.getElementById('progressBar');
  const progressText = document.getElementById('progressText');
  const resultEl = document.getElementById('importResult');
  progressWrap.style.display = 'block';

  let successCount = 0;
  let failCount = 0;
  const failDetails = [];

  for (let i = 0; i < pendingRows.length; i++) {
    const { title, content, rowNum } = pendingRows[i];
    const pct = Math.round(((i + 1) / pendingRows.length) * 100);
    progressBar.style.width = pct + '%';
    progressText.textContent = `正在导入 ${i + 1}/${pendingRows.length} ...`;

    try {
      const res = await fetch('/zhongcao/api/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Token': token },
        body: JSON.stringify({ title, content })
      });
      const data = await res.json();
      if (data.ok) {
        successCount++;
      } else {
        failCount++;
        failDetails.push(`第${rowNum}行: ${escHtml(data.error || '未知错误')}`);
      }
    } catch (e) {
      failCount++;
      failDetails.push(`第${rowNum}行: 网络错误`);
    }

    // 每导入一条休息 100ms，避免请求过快
    if (i < pendingRows.length - 1) {
      await new Promise(r => setTimeout(r, 100));
    }
  }

  progressBar.style.width = '100%';
  progressText.textContent = `导入完成！成功 ${successCount} 条，失败 ${failCount} 条`;

  let html = `<span class="ok">✅ 成功 ${successCount} 条</span>`;
  if (failCount > 0) {
    html += `　<span class="fail">❌ 失败 ${failCount} 条</span><br><br>失败明细：<br>` +
      failDetails.map(d => `<span class="fail">• ${d}</span>`).join('<br>');
  }
  resultEl.innerHTML = html;

  btn.disabled = false;
  btn.textContent = '📥 开始导入';
  pendingRows = [];

  // 刷新列表
  loadItems();
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
</script>
</body>
</html>"""


import random as _random

# ========== 请求处理 ==========

VALID_TOKENS = set()


def make_token(password):
    return hashlib.sha256((password + "salt_copyboard").encode()).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} - {format % args}")

    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def check_token(self):
        token = self.headers.get("X-Token", "")
        return token in VALID_TOKENS

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_SIZE:
            raise ValueError(f"Request body too large: {length} bytes")
        if length:
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ValueError(f"Invalid JSON: {e}")
        return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,X-Token")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self.send_html(INDEX_HTML)
        elif path == "/admin":
            self.send_html(ADMIN_HTML)
        elif path == "/api/items":
            with _data_lock:
                items = read_data()
            self.send_json(200, items)
        elif path == "/api/random":
            with _data_lock:
                items = read_data()
            total = len(items)
            if not items:
                self.send_json(200, {"item": None, "total": 0})
                return
            # 排除指定ID（换一条时用）
            qs = parse_qs(parsed.query)
            exclude_id = None
            if "exclude" in qs:
                try:
                    exclude_id = int(qs["exclude"][0])
                except Exception:
                    pass
            pool = [i for i in items if i["id"] != exclude_id]
            if not pool:
                pool = items  # 只剩一条时不排除
            item = _random.choice(pool)
            self.send_json(200, {"item": item, "total": total})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            parts = path.strip("/").split("/")

            if path == "/api/login":
                body = self.read_body()
                pwd = body.get("password", "")
                if pwd == ADMIN_PASSWORD:
                    token = make_token(pwd)
                    VALID_TOKENS.add(token)
                    self.send_json(200, {"ok": True, "token": token})
                else:
                    self.send_json(401, {"ok": False, "error": "密码错误"})

            elif path == "/api/items":
                if not self.check_token():
                    self.send_json(403, {"ok": False, "error": "请先登录"})
                    return
                body = self.read_body()
                title = body.get("title", "").strip()
                content = body.get("content", "").strip()
                if not title or not content:
                    self.send_json(400, {"ok": False, "error": "标题和内容不能为空"})
                    return
                if len(title) > 200:
                    self.send_json(400, {"ok": False, "error": "标题不能超过200字"})
                    return
                if len(content) > 5000:
                    self.send_json(400, {"ok": False, "error": "内容不能超过5000字"})
                    return
                with _data_lock:
                    items = read_data()
                    new_item = {
                        "id": get_next_id(items),
                        "title": title,
                        "content": content,
                        "created_at": datetime.now().isoformat(timespec="seconds")
                    }
                    items.append(new_item)
                    write_data(items)
                self.send_json(200, {"ok": True, "item": new_item})

            elif len(parts) == 3 and parts[0] == "api" and parts[1] == "use":
                # /api/use/<id> — 用户已复制，销毁该条目（无需管理员token）
                try:
                    item_id = int(parts[2])
                except ValueError:
                    self.send_json(400, {"ok": False, "error": "无效ID"})
                    return
                with _data_lock:
                    items = read_data()
                    new_items = [i for i in items if i["id"] != item_id]
                    if len(new_items) == len(items):
                        self.send_json(404, {"ok": False, "error": "条目不存在"})
                        return
                    write_data(new_items)
                self.send_json(200, {"ok": True, "remaining": len(new_items)})

            else:
                self.send_response(404)
                self.end_headers()
        except ValueError as e:
            self.send_json(400, {"ok": False, "error": str(e)})

    def do_PUT(self):
        try:
            parsed = urlparse(self.path)
            parts = parsed.path.strip("/").split("/")
            # /api/items/<id>
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "items":
                if not self.check_token():
                    self.send_json(403, {"ok": False, "error": "请先登录"})
                    return
                try:
                    item_id = int(parts[2])
                except ValueError:
                    self.send_json(400, {"ok": False, "error": "无效ID"})
                    return
                body = self.read_body()
                title = body.get("title", "").strip()
                content = body.get("content", "").strip()
                if not title or not content:
                    self.send_json(400, {"ok": False, "error": "标题和内容不能为空"})
                    return
                if len(title) > 200:
                    self.send_json(400, {"ok": False, "error": "标题不能超过200字"})
                    return
                if len(content) > 5000:
                    self.send_json(400, {"ok": False, "error": "内容不能超过5000字"})
                    return
                with _data_lock:
                    items = read_data()
                    found = False
                    for item in items:
                        if item["id"] == item_id:
                            item["title"] = title
                            item["content"] = content
                            item["updated_at"] = datetime.now().isoformat(timespec="seconds")
                            found = True
                            break
                    if not found:
                        self.send_json(404, {"ok": False, "error": "条目不存在"})
                        return
                    write_data(items)
                self.send_json(200, {"ok": True})
            else:
                self.send_response(404)
                self.end_headers()
        except ValueError as e:
            self.send_json(400, {"ok": False, "error": str(e)})

    def do_DELETE(self):
        try:
            parsed = urlparse(self.path)
            parts = parsed.path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "api" and parts[1] == "items":
                if not self.check_token():
                    self.send_json(403, {"ok": False, "error": "请先登录"})
                    return
                try:
                    item_id = int(parts[2])
                except ValueError:
                    self.send_json(400, {"ok": False, "error": "无效ID"})
                    return
                with _data_lock:
                    items = read_data()
                    new_items = [i for i in items if i["id"] != item_id]
                    if len(new_items) == len(items):
                        self.send_json(404, {"ok": False, "error": "条目不存在"})
                        return
                    write_data(new_items)
                self.send_json(200, {"ok": True})
            else:
                self.send_response(404)
                self.end_headers()
        except ValueError as e:
            self.send_json(400, {"ok": False, "error": str(e)})


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"✅ 服务已启动")
    print(f"   前端展示: http://localhost:{PORT}/")
    print(f"   管理后台: http://localhost:{PORT}/admin")
    print(f"   管理密码: {ADMIN_PASSWORD}")
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
