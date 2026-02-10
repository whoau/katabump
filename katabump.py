#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KataBump 自动续期 - 指定登录页版
URL: https://dashboard.katabump.com/auth/login
功能：
1. 访问指定登录页
2. 输入邮箱密码登录
3. 遍历服务器并续期
4. 强力抗 Cloudflare
"""

import os
import sys
import time
import random
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ==================== 配置 ====================
BASE_URL = "https://dashboard.katabump.com"
# 你指定的登录页
LOGIN_URL = "https://dashboard.katabump.com/auth/login"
DASHBOARD_URL = f"{BASE_URL}/dashboard"

# 续期按钮文本 (根据实际页面调整)
RENEW_TEXTS = ["Renew", "Extend", "Add Time", "Bump", "续期", "时间增加"]

# 环境变量
LOGIN_EMAIL = os.getenv('KATABUMP_EMAIL', '').strip()
LOGIN_PASSWORD = os.getenv('KATABUMP_PASSWORD', '').strip()
# 可选：CF通行证 (仅用于过5秒盾，不是登录Cookie)
CF_CLEARANCE = os.getenv('KATABUMP_CF_CLEARANCE', '').strip()

HEADLESS = False 
SCREENSHOT_DIR = "screenshots"

class KataBot:
    def __init__(self):
        self.page = None

    def log(self, msg, level="INFO"):
        bj_time = datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌"}.get(level, "")
        print(f"[{bj_time}] {icon} [{level}] {msg}")

    def save_debug(self, name):
        try:
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            self.page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
        except: pass

    def human_type(self, selector, text):
        """模拟真人打字"""
        try:
            self.page.wait_for_selector(selector, timeout=5000)
            self.page.focus(selector)
            for char in text:
                self.page.keyboard.type(char, delay=random.randint(50, 150))
            time.sleep(random.uniform(0.5, 1.0))
        except Exception as e:
            self.log(f"输入失败 ({selector}): {e}", "ERROR")

    def wait_for_cf(self, timeout=30):
        """过 Cloudflare 5秒盾"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            title = self.page.title().lower()
            if "just a moment" not in title and "attention required" not in title:
                return True
            try:
                for frame in self.page.frames:
                    cb = frame.locator("input[type='checkbox'], .ctp-checkbox-label").first
                    if cb.is_visible():
                        self.log("👆 点击 CF 验证框...", "INFO")
                        time.sleep(1)
                        cb.click()
                        time.sleep(2)
            except: pass
            time.sleep(2)
        return False

    def login(self):
        """执行账号密码登录"""
        self.log(f"正在访问登录页: {LOGIN_URL}", "INFO")
        
        try:
            # 1. 访问指定的登录页
            self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            
            # 处理 CF
            if not self.wait_for_cf(timeout=60):
                self.log("❌ 无法通过 CF 防护", "ERROR")
                return False

            self.page.wait_for_load_state("networkidle")

            # 2. 寻找输入框
            # 兼容常见的 name 属性
            email_sel = "input[name='email'], input[type='email']"
            pass_sel = "input[name='password'], input[type='password']"
            
            if self.page.locator(email_sel).count() > 0:
                self.log("找到登录表单，输入账号密码...", "INFO")
                
                # 输入
                self.human_type(email_sel, LOGIN_EMAIL)
                self.human_type(pass_sel, LOGIN_PASSWORD)
                
                # 3. 提交
                submit_btn = self.page.locator("button[type='submit'], input[type='submit']").first
                if submit_btn.is_visible():
                    self.log("点击登录按钮...", "INFO")
                    submit_btn.click()
                    
                    # 等待跳转
                    self.page.wait_for_load_state("networkidle")
                    self.wait_for_cf()
                    time.sleep(5) # 多等一会，确保跳转完成
                    
                    # 4. 验证结果
                    # 如果 URL 变了，或者包含 dashboard，或者没有 login，就算成功
                    current_url = self.page.url
                    if "login" not in current_url or "dashboard" in current_url:
                        self.log("✅ 登录成功！", "SUCCESS")
                        return True
                    else:
                        # 检查错误提示
                        error_msg = self.page.locator(".alert-danger, .error, .text-red-500").first
                        if error_msg.is_visible():
                            self.log(f"❌ 登录失败提示: {error_msg.inner_text()}", "ERROR")
                        else:
                            self.log(f"❌ 登录失败，仍停留在: {current_url}", "ERROR")
                        self.save_debug("login_fail")
                        return False
            else:
                self.log("❌ 未找到邮箱/密码输入框，页面结构可能变化", "ERROR")
                self.save_debug("no_login_form")
                return False

        except Exception as e:
            self.log(f"登录过程出错: {e}", "ERROR")
            return False

    def process_renewal(self):
        """处理续期逻辑"""
        # 有时候登录后会自动跳转 Dashboard，有时候不会，这里强制访问一次
        if "dashboard" not in self.page.url:
            self.log(f"🔗 前往 Dashboard: {DASHBOARD_URL}", "INFO")
            self.page.goto(DASHBOARD_URL, wait_until="networkidle")
            self.wait_for_cf()
        
        try:
            # 二次检查是否掉线
            if "login" in self.page.url:
                self.log("❌ 访问 Dashboard 时被重定向回登录页", "ERROR")
                return []

            self.log("🔍 扫描服务器列表...", "INFO")
            # 查找 'See' 按钮
            see_btns = self.page.locator("a:has-text('See'), button:has-text('See')").all()
            
            targets = []
            for btn in see_btns:
                href = btn.get_attribute("href")
                if href: targets.append(href if href.startswith("http") else f"{BASE_URL}{href}")
            
            # 去重
            targets = list(set(targets))
            
            if not targets:
                self.log("⚠️ 未找到任何服务器 (列表为空?)", "WARNING")
                self.save_debug("no_servers")
                # 尝试打印页面内容的一小部分用于调试
                # print(self.page.content()[:500])
                return []

            self.log(f"📦 发现 {len(targets)} 个服务器", "SUCCESS")
            results = []

            for url in targets:
                sid = url.split("/")[-1]
                self.log(f"--- 处理: {sid} ---", "INFO")
                try:
                    self.page.goto(url, wait_until="domcontentloaded")
                    self.wait_for_cf()
                    self.page.wait_for_load_state("networkidle")
                    
                    btn_found = False
                    for txt in RENEW_TEXTS:
                        btn = self.page.locator(f"button:has-text('{txt}'), a.btn:has-text('{txt}')")
                        if btn.count() > 0:
                            if btn.first.is_disabled():
                                self.log("⏳ 冷却中/不可用", "WARNING")
                                results.append({"id": sid, "status": "⏳ 冷却中"})
                            else:
                                self.log(f"⚡ 点击 '{txt}'...", "INFO")
                                btn.first.click()
                                time.sleep(3)
                                results.append({"id": sid, "status": "✅ 成功"})
                            btn_found = True
                            break
                    
                    if not btn_found:
                        results.append({"id": sid, "status": "❌ 无按钮"})
                
                except Exception as e:
                    self.log(f"出错: {e}", "ERROR")
                    results.append({"id": sid, "status": "💥 出错"})
                
                time.sleep(2)
            
            return results

        except Exception as e:
            self.log(f"Dashboard 处理出错: {e}", "ERROR")
            return []

    def update_readme(self, results):
        bj_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        content = f"# KataBump 状态\n> 更新: `{bj_time}`\n\n| ID | 状态 |\n|---|---|\n"
        if not results: content += "| - | 无数据 |\n"
        for r in results: content += f"| {r['id']} | {r['status']} |\n"
        try:
            with open("README.md", "w") as f: f.write(content)
        except: pass

    def run(self):
        if not LOGIN_EMAIL or not LOGIN_PASSWORD:
            self.log("未设置邮箱或密码，请检查 Secrets", "ERROR")
            sys.exit(1)

        with sync_playwright() as p:
            # 启动浏览器 (有头模式 + 反检测)
            browser = p.chromium.launch(
                headless=HEADLESS, 
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(context)
            except: pass
            
            # (可选) 注入 CF Clearance 仅用于过盾
            if CF_CLEARANCE:
                context.add_cookies([{
                    'name': 'cf_clearance', 'value': CF_CLEARANCE,
                    'domain': '.katabump.com', 'path': '/'
                }])

            self.page = context.new_page()

            # 1. 执行登录
            if self.login():
                # 2. 登录成功，执行续期
                results = self.process_renewal()
                self.update_readme(results)
            else:
                sys.exit(1)

            browser.close()

if __name__ == "__main__":
    KataBot().run()
