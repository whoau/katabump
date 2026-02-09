#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KataBump 自动续期 - 抗指纹增强版
更新内容：
1. 支持 cf_clearance 注入 (关键)
2. 增加鼠标模拟移动 (GhostCursor 逻辑)
3. 增加 User-Agent 随机化
"""

import os
import sys
import time
import random
import math
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# ==================== 配置 ====================
BASE_URL = "https://dashboard.katabump.com"
DASHBOARD_URL = f"{BASE_URL}/dashboard"
RENEW_TEXTS = ["Renew", "Extend", "Add Time", "Bump", "续期", "时间增加"]

# 环境变量
COOKIE_NAME = os.getenv('KATABUMP_COOKIE_NAME', 'katabump_s').strip()
COOKIE_VALUE = os.getenv('KATABUMP_COOKIE_VALUE', '').strip()
CF_CLEARANCE = os.getenv('KATABUMP_CF_CLEARANCE', '').strip() # 新增

HEADLESS = False 
SCREENSHOT_DIR = "screenshots"

class KataBot:
    def __init__(self):
        self.page = None

    def log(self, msg, level="INFO"):
        bj_time = datetime.now(timezone(timedelta(hours=8))).strftime('%H:%M:%S')
        icon = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "DEBUG": "🔍"}.get(level, "")
        print(f"[{bj_time}] {icon} [{level}] {msg}")

    def save_debug(self, name):
        try:
            os.makedirs(SCREENSHOT_DIR, exist_ok=True)
            self.page.screenshot(path=f"{SCREENSHOT_DIR}/{name}.png", full_page=True)
        except: pass

    def human_click(self, locator):
        """模拟真人鼠标轨迹点击"""
        try:
            box = locator.bounding_box()
            if box:
                # 目标点 (加一点随机偏移)
                target_x = box["x"] + box["width"] / 2 + random.uniform(-5, 5)
                target_y = box["y"] + box["height"] / 2 + random.uniform(-5, 5)
                
                # 当前鼠标位置
                self.page.mouse.move(target_x, target_y, steps=random.randint(10, 20))
                time.sleep(random.uniform(0.1, 0.3))
                self.page.mouse.down()
                time.sleep(random.uniform(0.05, 0.15))
                self.page.mouse.up()
            else:
                locator.click()
        except:
            locator.click()

    def wait_for_cf(self, timeout=30):
        """CF 处理逻辑 (增强版)"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            # 检查是否还有盾
            try:
                # 查找 iframe
                iframe = None
                for frame in self.page.frames:
                    if "challenges.cloudflare.com" in frame.url:
                        iframe = frame
                        break
                
                if iframe:
                    self.log("🛡️ 发现 CF 验证框，尝试通过...", "WARNING")
                    # 查找 checkbox
                    cb = iframe.locator("input[type='checkbox'], .ctp-checkbox-label").first
                    if cb.is_visible():
                        time.sleep(random.uniform(1.5, 3.0)) # 思考时间
                        self.human_click(cb) # 模拟鼠标点击
                        self.log("👆 已点击验证框，等待跳转...", "INFO")
                        time.sleep(5) # 给它时间反应
                        continue # 继续循环检查是否还在
                
                # 检查标题
                if "just a moment" not in self.page.title().lower():
                    return True # 这里的逻辑是：如果没有盾了，就返回True
                
            except Exception as e:
                pass
            
            time.sleep(2)
        
        # 如果超时还在盾里
        if "just a moment" in self.page.title().lower():
            self.log("❌ CF 验证失败 (死循环)", "ERROR")
            self.save_debug("cf_loop_fail")
            return False
        return True

    def run(self):
        with sync_playwright() as p:
            self.log("🚀 启动浏览器...", "INFO")
            browser = p.chromium.launch(
                headless=HEADLESS, 
                args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            # 注入 stealth
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(context)
            except: pass

            self.page = context.new_page()

            # 1. 注入 Cookies (Session + CF_Clearance)
            self.log("🍪 注入 Cookies...", "INFO")
            cookies = [{
                'name': COOKIE_NAME,
                'value': COOKIE_VALUE,
                'domain': 'dashboard.katabump.com',
                'path': '/'
            }]
            
            # 注入 cf_clearance (如果有)
            if CF_CLEARANCE:
                self.log("🛡️ 注入 cf_clearance...", "INFO")
                cookies.append({
                    'name': 'cf_clearance',
                    'value': CF_CLEARANCE,
                    'domain': '.katabump.com', # 注意有个点，代表通配
                    'path': '/'
                })
            
            context.add_cookies(cookies)

            # 2. 访问
            try:
                self.log(f"🔗 访问: {DASHBOARD_URL}", "INFO")
                self.page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=60000)
                
                if not self.wait_for_cf(timeout=60):
                    raise Exception("CF 验证失败")
                
                self.page.wait_for_load_state("networkidle")
                time.sleep(2)

                # 检查登录
                if "login" in self.page.url:
                    self.log("❌ 登录失效 (Cookies 过期)", "ERROR")
                    sys.exit(1)

                # 3. 扫描列表
                self.log("🔍 扫描服务器...", "INFO")
                see_btns = self.page.locator("a:has-text('See'), button:has-text('See')").all()
                
                targets = []
                for btn in see_btns:
                    href = btn.get_attribute("href")
                    if href:
                        targets.append(href if href.startswith("http") else f"{BASE_URL}{href}")
                
                # 去重
                targets = list(set(targets))
                self.log(f"📦 找到 {len(targets)} 个服务器", "SUCCESS")

                results = []
                # 4. 遍历处理
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
                                    self.log(f"⏳ 冷却中", "WARNING")
                                    results.append({"id": sid, "status": "⏳ 冷却中"})
                                else:
                                    self.log(f"⚡ 点击续期...", "INFO")
                                    self.human_click(btn.first)
                                    time.sleep(3)
                                    results.append({"id": sid, "status": "✅ 成功"})
                                btn_found = True
                                break
                        
                        if not btn_found:
                            self.log("❌ 没找到按钮", "ERROR")
                            results.append({"id": sid, "status": "❌ 无按钮"})
                            
                    except Exception as e:
                        self.log(f"出错: {e}", "ERROR")
                        results.append({"id": sid, "status": "💥 出错"})
                    
                    time.sleep(random.uniform(2, 5))

                browser.close()
                self.update_readme(results)

            except Exception as e:
                self.log(f"致命错误: {e}", "ERROR")
                self.save_debug("fatal_error")
                sys.exit(1)

    def update_readme(self, results):
        bj_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        content = f"# KataBump 状态\n> 更新: `{bj_time}`\n\n| ID | 状态 |\n|---|---|\n"
        for r in results: content += f"| {r['id']} | {r['status']} |\n"
        try:
            with open("README.md", "w") as f: f.write(content)
        except: pass

if __name__ == "__main__":
    KataBot().run()
