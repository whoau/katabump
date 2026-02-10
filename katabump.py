#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KataBump 自动续期 - 点击交互版
逻辑：
1. 登录
2. 在 Dashboard 找到 Action 列的 See 按钮
3. 直接点击进入详情页 (不拼接URL)
4. 点击续期
5. 返回列表处理下一个
"""

import os
import sys
import time
import random
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ==================== 配置 ====================
BASE_URL = "https://dashboard.katabump.com"
LOGIN_URL = "https://dashboard.katabump.com/auth/login"
DASHBOARD_URL = f"{BASE_URL}/dashboard"

# 续期按钮文本
RENEW_TEXTS = ["Renew", "Extend", "Add Time", "Bump", "续期", "时间增加"]

# 环境变量
LOGIN_EMAIL = os.getenv('KATABUMP_EMAIL', '').strip()
LOGIN_PASSWORD = os.getenv('KATABUMP_PASSWORD', '').strip()
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
        try:
            self.page.wait_for_selector(selector, timeout=5000)
            self.page.focus(selector)
            for char in text:
                self.page.keyboard.type(char, delay=random.randint(50, 150))
            time.sleep(random.uniform(0.5, 1.0))
        except: pass

    def wait_for_cf(self, timeout=30):
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
        self.log(f"正在访问登录页: {LOGIN_URL}", "INFO")
        try:
            self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            if not self.wait_for_cf(timeout=60): return False
            self.page.wait_for_load_state("networkidle")

            if self.page.locator("input[name='email']").count() > 0:
                self.log("输入账号密码...", "INFO")
                self.human_type("input[name='email']", LOGIN_EMAIL)
                self.human_type("input[name='password']", LOGIN_PASSWORD)
                
                btn = self.page.locator("button[type='submit'], input[type='submit']").first
                if btn.is_visible():
                    self.log("点击登录...", "INFO")
                    btn.click()
                    self.page.wait_for_load_state("networkidle")
                    self.wait_for_cf()
                    time.sleep(5)
                    
                    if "login" not in self.page.url:
                        self.log("✅ 登录成功！", "SUCCESS")
                        return True
            
            self.log("❌ 登录失败", "ERROR")
            self.save_debug("login_fail")
            return False
        except Exception as e:
            self.log(f"登录出错: {e}", "ERROR")
            return False

    def process_renewal(self):
        """核心逻辑：遍历并点击 See 按钮"""
        results = []
        
        try:
            # 1. 确保在 Dashboard
            if "dashboard" not in self.page.url:
                self.page.goto(DASHBOARD_URL, wait_until="networkidle")
                self.wait_for_cf()

            # 2. 统计有多少个 "See" 按钮
            # 我们不存 URL，存索引，因为页面刷新后元素会失效
            # 查找文本为 "See" 的按钮或链接
            selector = "a:has-text('See'), button:has-text('See')"
            
            # 等待列表加载
            try:
                self.page.wait_for_selector(selector, timeout=10000)
            except:
                self.log("⚠️ 未找到 'See' 按钮 (列表为空?)", "WARNING")
                self.save_debug("no_see_buttons")
                return []

            count = self.page.locator(selector).count()
            self.log(f"📦 发现 {count} 个服务器", "SUCCESS")

            # 3. 循环处理每一个
            for i in range(count):
                self.log(f"--- 准备处理第 {i+1} 个服务器 ---", "INFO")
                
                # 每次循环都要重新定位，因为我们会跳转页面
                # 如果不在 Dashboard，先回去
                if "dashboard" not in self.page.url:
                    self.page.goto(DASHBOARD_URL, wait_until="networkidle")
                    self.wait_for_cf()
                    time.sleep(2)
                
                # 获取第 i 个按钮
                see_btn = self.page.locator(selector).nth(i)
                
                if not see_btn.is_visible():
                    self.log(f"第 {i+1} 个按钮不可见，跳过", "WARNING")
                    continue
                
                # 4. 点击 "See" 进入详情页
                self.log("👆 点击 'See' 按钮...", "INFO")
                see_btn.click()
                
                # 等待跳转
                self.page.wait_for_load_state("domcontentloaded")
                self.wait_for_cf()
                self.page.wait_for_load_state("networkidle")
                time.sleep(2)

                # 获取当前 ID 用于记录
                try:
                    current_url = self.page.url
                    if "id=" in current_url:
                        sid = current_url.split("id=")[1].split("&")[0]
                    else:
                        sid = current_url.split("/")[-1]
                except: sid = f"Server_{i+1}"

                # 5. 在详情页查找续期按钮
                btn_found = False
                for txt in RENEW_TEXTS:
                    btn = self.page.locator(f"button:has-text('{txt}'), a.btn:has-text('{txt}')")
                    if btn.count() > 0:
                        if btn.first.is_disabled():
                            self.log(f"[{sid}] ⏳ 冷却中", "WARNING")
                            results.append({"id": sid, "status": "⏳ 冷却中"})
                        else:
                            self.log(f"[{sid}] ⚡ 点击 '{txt}'...", "INFO")
                            btn.first.click()
                            time.sleep(3)
                            self.log(f"[{sid}] ✅ 成功", "SUCCESS")
                            results.append({"id": sid, "status": "✅ 成功"})
                        btn_found = True
                        break
                
                if not btn_found:
                    self.log(f"[{sid}] ❌ 未找到续期按钮", "ERROR")
                    self.save_debug(f"no_renew_btn_{i}")
                    results.append({"id": sid, "status": "❌ 无按钮"})
                
                # 稍作休息，防止操作过快
                time.sleep(2)

            return results

        except Exception as e:
            self.log(f"处理流程出错: {e}", "ERROR")
            self.save_debug("process_error")
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
        if not LOGIN_EMAIL or not LOGIN_PASSWORD: sys.exit(1)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=HEADLESS, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            context = browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(context)
            except: pass
            if CF_CLEARANCE: context.add_cookies([{'name': 'cf_clearance', 'value': CF_CLEARANCE, 'domain': '.katabump.com', 'path': '/'}])
            
            self.page = context.new_page()

            if self.login():
                results = self.process_renewal()
                self.update_readme(results)
            else:
                sys.exit(1)
            
            browser.close()

if __name__ == "__main__":
    KataBot().run()
