#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KataBump 自动续期脚本 - 终极抗 CF 版
功能：
1. 强力绕过 Cloudflare (使用 stealth + xvfb)
2. 自动遍历 Dashboard 列表中的 "See" 按钮
3. 进入详情页点击续期
4. 自动更新 README
"""

import os
import sys
import time
import random
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ==================== 配置 ====================
BASE_URL = "https://dashboard.katabump.com"
DASHBOARD_URL = f"{BASE_URL}/dashboard"

# 续期按钮可能的文本 (根据实际网页调整)
RENEW_TEXTS = ["Renew", "Extend", "Add Time", "Bump", "续期", "时间增加", "시간 추가"]

# 环境变量
COOKIE_NAME = os.getenv('KATABUMP_COOKIE_NAME', 'laravel_session').strip()
COOKIE_VALUE = os.getenv('KATABUMP_COOKIE_VALUE', '').strip()

# 调试设置
HEADLESS = False  # 必须为 False 才能配合 xvfb 绕过 CF
SCREENSHOT_DIR = "screenshots"

class KataBot:
    def __init__(self):
        self.page = None
        self.log_msgs = []

    def log(self, msg, level="INFO"):
        """日志输出"""
        bj_time = datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "DEBUG": "🔍"}.get(level, "")
        log_line = f"[{bj_time}] {icon} [{level}] {msg}"
        print(log_line)
        self.log_msgs.append(log_line)

    def save_debug(self, name):
        """保存截图"""
        try:
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            self.page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
            self.log(f"已截图: {name}.png", "DEBUG")
        except: pass

    def wait_for_cf(self, timeout=30):
        """核心：Cloudflare 智能处理逻辑"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            title = self.page.title().lower()
            content = self.page.content().lower()
            
            # 检测是否在 CF 验证页
            if "just a moment" in title or "challenges.cloudflare.com" in content or "checking your browser" in content:
                self.log("🛡️ 检测到 Cloudflare 盾，正在尝试绕过...", "WARNING")
                
                # 尝试查找 iframe 里的复选框并点击
                try:
                    for frame in self.page.frames:
                        cb = frame.locator("input[type='checkbox'], .ctp-checkbox-label").first
                        if cb.is_visible():
                            self.log("👆 点击 CF 验证框...", "INFO")
                            cb.click()
                            time.sleep(2)
                except: pass
                
                time.sleep(3)
            else:
                # 已经通过或不在 CF 页
                return True
        
        self.log("❌ Cloudflare 验证超时！", "ERROR")
        self.save_debug("cf_timeout")
        return False

    def init_browser(self, p):
        """初始化浏览器 (带 stealth 反检测)"""
        self.log("🚀 启动浏览器...")
        browser = p.chromium.launch(
            headless=HEADLESS, # GitHub Actions 里配合 xvfb 必须设为 False
            args=[
                "--no-sandbox", 
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
        )
        
        self.page = context.new_page()
        
        # 注入 playwright-stealth (最强反检测)
        try:
            from playwright_stealth import stealth_sync
            stealth_sync(self.page)
            self.log("✅ 反检测模块加载成功", "INFO")
        except ImportError:
            self.log("⚠️ 未安装 playwright-stealth，使用简易反检测", "WARNING")
            self.page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        return browser, context

    def run(self):
        if not COOKIE_VALUE:
            self.log("未设置 KATABUMP_COOKIE_VALUE，请检查 Secrets", "ERROR")
            sys.exit(1)

        with sync_playwright() as p:
            browser, context = self.init_browser(p)
            
            # 1. 注入 Cookie
            self.log("🍪 注入登录 Cookie...", "INFO")
            context.add_cookies([{
                'name': COOKIE_NAME,
                'value': COOKIE_VALUE,
                'domain': 'dashboard.katabump.com', 
                'path': '/'
            }])

            results = []

            try:
                # 2. 访问 Dashboard (列表页)
                self.log(f"🔗 正在访问: {DASHBOARD_URL}", "INFO")
                self.page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=60000)
                
                # 处理 CF
                if not self.wait_for_cf(timeout=60):
                    raise Exception("无法通过 CF 防护")

                # 等待页面加载
                self.page.wait_for_load_state("networkidle")
                time.sleep(2)

                # 检查登录状态
                if "login" in self.page.url or self.page.locator("text=Login").count() > 0:
                    self.log("❌ Cookie 已失效，重定向到了登录页", "ERROR")
                    self.save_debug("login_failed")
                    sys.exit(1)

                # 3. 扫描列表，提取 "See" 按钮链接
                self.log("🔍 扫描服务器列表...", "INFO")
                
                # 查找 Action 列下的 See 按钮/链接
                # 假设它是 <a> 标签或者 <button>
                see_elements = self.page.locator("a:has-text('See'), button:has-text('See')").all()
                
                target_urls = []
                for el in see_elements:
                    try:
                        href = el.get_attribute("href")
                        if href:
                            full_url = href if href.startswith("http") else f"{BASE_URL}{href}"
                            if full_url not in target_urls:
                                target_urls.append(full_url)
                    except: pass
                
                # 如果没找到，尝试另一种可能：直接点击 See 按钮跳转
                # 但最好是收集 URL 逐个访问，更稳定
                
                if not target_urls:
                    self.log("⚠️ 未找到任何 'See' 按钮 (列表为空?)", "WARNING")
                    self.save_debug("no_servers")
                else:
                    self.log(f"📦 发现 {len(target_urls)} 个服务器，准备处理...", "SUCCESS")

                # 4. 遍历每个服务器详情页
                for i, url in enumerate(target_urls):
                    server_id = url.split("/")[-1]
                    self.log(f"--- 正在处理 [{i+1}/{len(target_urls)}] ID: {server_id} ---", "INFO")
                    
                    try:
                        # 访问详情页
                        self.page.goto(url, wait_until="domcontentloaded")
                        self.wait_for_cf() # 每个页面都检查一下盾
                        self.page.wait_for_load_state("networkidle")
                        
                        # 查找续期按钮
                        btn_found = False
                        for txt in RENEW_TEXTS:
                            btn = self.page.locator(f"button:has-text('{txt}'), a.btn:has-text('{txt}')")
                            if btn.count() > 0:
                                if btn.first.is_disabled():
                                    self.log(f"⏳ 按钮 '{txt}' 冷却中", "WARNING")
                                    results.append({"id": server_id, "status": "⏳ 冷却中"})
                                else:
                                    self.log(f"⚡ 点击 '{txt}' 按钮...", "INFO")
                                    btn.first.click()
                                    time.sleep(3)
                                    self.log("✅ 点击完成", "SUCCESS")
                                    results.append({"id": server_id, "status": "✅ 成功"})
                                btn_found = True
                                break
                        
                        if not btn_found:
                            self.log("❌ 未找到续期按钮", "ERROR")
                            self.save_debug(f"no_btn_{server_id}")
                            results.append({"id": server_id, "status": "❌ 未找到按钮"})

                    except Exception as e:
                        self.log(f"💥 处理出错: {e}", "ERROR")
                        results.append({"id": server_id, "status": "💥 异常"})
                    
                    # 随机等待，模拟人类
                    time.sleep(random.uniform(2, 5))

            except Exception as e:
                self.log(f"脚本运行崩溃: {e}", "ERROR")
                self.save_debug("crash")
            finally:
                browser.close()
                self.update_readme(results)

    def update_readme(self, results):
        """更新 README 报告"""
        bj_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        content = f"# KataBump 续期报告\n\n> 更新时间: `{bj_time}` (北京)\n\n| 服务器ID | 状态 |\n|---|---|\n"
        
        if not results:
            content += "| 无 | 未发现服务器或运行出错 |\n"
        else:
            for r in results:
                content += f"| `{r['id']}` | {r['status']} |\n"
        
        content += "\n---\n*By GitHub Actions w/ Anti-CF Tech*\n"
        
        try:
            with open("README.md", "w", encoding="utf-8") as f:
                f.write(content)
            self.log("📄 README.md 已更新", "SUCCESS")
        except: pass

if __name__ == "__main__":
    KataBot().run()
