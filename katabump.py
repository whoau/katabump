#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KataBump 自动续期 - 抗超时增强版
修复：点击 See 后页面加载超时导致脚本崩溃的问题
策略：放宽页面加载等待条件，超时后尝试强制寻找按钮
"""

import os
import sys
import time
import random
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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
            
            # 等待输入框出现
            try:
                self.page.wait_for_selector("input[name='email']", timeout=10000)
            except:
                self.log("❌ 未找到登录输入框", "ERROR")
                return False

            self.log("输入账号密码...", "INFO")
            self.human_type("input[name='email']", LOGIN_EMAIL)
            self.human_type("input[name='password']", LOGIN_PASSWORD)
            
            btn = self.page.locator("button[type='submit'], input[type='submit']").first
            if btn.is_visible():
                self.log("点击登录...", "INFO")
                btn.click()
                
                # 登录后的等待不需要太严格
                try:
                    self.page.wait_for_load_state("domcontentloaded", timeout=30000)
                except: pass
                
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
        results = []
        
        try:
            # 1. 确保在 Dashboard
            if "dashboard" not in self.page.url:
                self.page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
                self.wait_for_cf()

            # 2. 查找 See 按钮
            selector = "a:has-text('See'), button:has-text('See')"
            try:
                self.page.wait_for_selector(selector, timeout=15000)
            except:
                self.log("⚠️ 未找到 'See' 按钮 (列表为空?)", "WARNING")
                return []

            count = self.page.locator(selector).count()
            self.log(f"📦 发现 {count} 个服务器", "SUCCESS")

            for i in range(count):
                self.log(f"--- 准备处理第 {i+1} 个服务器 ---", "INFO")
                
                # 回到 Dashboard
                if "dashboard" not in self.page.url:
                    self.page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
                    self.wait_for_cf()
                    time.sleep(2)
                
                see_btn = self.page.locator(selector).nth(i)
                if not see_btn.is_visible(): continue
                
                self.log("👆 点击 'See' 按钮...", "INFO")
                
                # ★ 核心修复：点击后不再死等 networkidle ★
                try:
                    # 点击
                    see_btn.click()
                    
                    # 只要 URL 变了，或者 DOM 加载了就算成功，不用等所有资源加载完
                    # 设置 60秒超时，如果超时了被 catch 住，依然尝试去找按钮
                    self.page.wait_for_load_state("domcontentloaded", timeout=60000)
                    self.wait_for_cf()
                    
                except PlaywrightTimeoutError:
                    self.log("⚠️ 页面加载超时，但尝试继续寻找按钮...", "WARNING")
                except Exception as e:
                    self.log(f"跳转异常: {e}", "ERROR")

                # 获取 ID
                try:
                    sid = self.page.url.split("id=")[1].split("&")[0]
                except: sid = f"Server_{i+1}"

                # 寻找续期按钮
                btn_found = False
                for txt in RENEW_TEXTS:
                    btn = self.page.locator(f"button:has-text('{txt}'), a.btn:has-text('{txt}')")
                    
                    # 显式等待按钮出现一小会儿
                    try:
                        btn.first.wait_for(state="visible", timeout=5000)
                    except: pass

                    if btn.count() > 0:
                        if btn.first.is_disabled():
                            self.log(f"[{sid}] ⏳ 冷却中", "WARNING")
                            results.append({"id": sid, "status": "⏳ 冷却中"})
                        else:
                            self.log(f"[{sid}] ⚡ 点击 '{txt}'...", "INFO")
                            try:
                                btn.first.click(timeout=10000)
                                time.sleep(3)
                                self.log(f"[{sid}] ✅ 成功", "SUCCESS")
                                results.append({"id": sid, "status": "✅ 成功"})
                            except Exception as e:
                                self.log(f"[{sid}] 点击失败: {e}", "ERROR")
                        btn_found = True
                        break
                
                if not btn_found:
                    self.log(f"[{sid}] ❌ 未找到续期按钮", "ERROR")
                    self.save_debug(f"no_renew_btn_{i}")
                    results.append({"id": sid, "status": "❌ 无按钮"})
                
                time.sleep(2)

            return results

        except Exception as e:
            self.log(f"处理流程出错: {e}", "ERROR")
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
            # 启动配置：设置全局 60秒超时
            browser = p.chromium.launch(headless=HEADLESS, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(context)
            except: pass
            
            if CF_CLEARANCE: context.add_cookies([{'name': 'cf_clearance', 'value': CF_CLEARANCE, 'domain': '.katabump.com', 'path': '/'}])
            
            self.page = context.new_page()
            self.page.set_default_timeout(60000) # 全局超时设为 60s

            if self.login():
                results = self.process_renewal()
                self.update_readme(results)
            else:
                sys.exit(1)
            
            browser.close()

if __name__ == "__main__":
    KataBot().run()
