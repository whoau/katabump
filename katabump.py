#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KataBump 自动续期 - 强力登录修复版
更新内容：
1. 引入 playwright-stealth 防止被检测
2. 增加鼠标拟人轨迹 (CF 极度依赖鼠标移动检测)
3. 保持双重点击续期策略
"""

import os
import sys
import time
import random
import math
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ==================== 配置 ====================
BASE_URL = "https://dashboard.katabump.com"
LOGIN_URL = f"{BASE_URL}/auth/login"
DASHBOARD_URL = f"{BASE_URL}/dashboard"

# 续期按钮文本
RENEW_TEXTS = ["Renew", "Extend", "Add Time", "Bump", "续期", "时间增加"]

# 环境变量
LOGIN_EMAIL = os.getenv('KATABUMP_EMAIL', '').strip()
LOGIN_PASSWORD = os.getenv('KATABUMP_PASSWORD', '').strip()
CF_CLEARANCE = os.getenv('KATABUMP_CF_CLEARANCE', '').strip()

# 服务器运行建议设为 True，本地调试设为 False
HEADLESS = os.getenv('HEADLESS', 'false').lower() == 'true'
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

    # --- 关键：模拟真人鼠标移动 ---
    def mouse_move_human(self):
        """模拟真人鼠标随机移动，骗过 CF"""
        try:
            width = self.page.viewport_size['width']
            height = self.page.viewport_size['height']
            for _ in range(random.randint(3, 7)):
                x = random.randint(0, width)
                y = random.randint(0, height)
                self.page.mouse.move(x, y, steps=random.randint(5, 10))
                time.sleep(random.uniform(0.05, 0.2))
        except: pass

    def human_type(self, selector, text):
        """模拟真人打字"""
        try:
            self.page.wait_for_selector(selector, timeout=10000)
            self.page.focus(selector)
            for char in text:
                self.page.keyboard.type(char, delay=random.randint(50, 150))
            time.sleep(random.uniform(0.5, 1.0))
        except Exception as e:
            self.log(f"输入失败 {selector}: {e}", "WARNING")

    def check_cf(self):
        """检测并尝试通过 CF 盾"""
        try:
            title = self.page.title().lower()
            if "just a moment" in title or "attention required" in title:
                self.log("🛡️ 检测到 Cloudflare，启动对抗...", "WARNING")
                self.mouse_move_human() # 疯狂晃动鼠标
                time.sleep(2)
                
                # 尝试点击 iframe 里的勾选框
                frames = self.page.frames
                for frame in frames:
                    if "challenges" in frame.url or "turnstile" in frame.url:
                        try:
                            box = frame.locator("input[type='checkbox']").first
                            if box.is_visible():
                                box.hover() # 先悬停
                                time.sleep(0.5)
                                box.click()
                                self.log("👆 点击了 CF 验证框", "INFO")
                                time.sleep(3)
                        except: pass
                return True
        except: pass
        return False

    def login(self):
        self.log(f"正在访问登录页...", "INFO")
        try:
            self.page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            
            # 进页面先动鼠标
            self.mouse_move_human()
            
            # 等待可能的 CF
            for _ in range(5):
                if self.check_cf(): time.sleep(3)
                else: break

            # 检查是否已经在登录页
            try:
                self.page.wait_for_selector("input[name='email']", timeout=15000)
            except:
                self.log("❌ 登录页加载失败或被 CF 拦截", "ERROR")
                self.save_debug("login_blocked")
                return False

            self.log("输入账号密码...", "INFO")
            self.human_type("input[name='email']", LOGIN_EMAIL)
            self.human_type("input[name='password']", LOGIN_PASSWORD)
            
            # 点击登录按钮
            btn = self.page.locator("button[type='submit']").first
            if btn.is_visible():
                self.mouse_move_human()
                btn.hover()
                time.sleep(0.5)
                btn.click()
                self.log("点击登录...", "INFO")
                
                # 登录后的等待，处理可能的 CF
                try: 
                    self.page.wait_for_load_state("networkidle", timeout=30000)
                except: pass
                
                self.check_cf()
                time.sleep(5)
                
                if "/auth/login" not in self.page.url:
                    self.log("✅ 登录成功！", "SUCCESS")
                    return True
            
            self.log("❌ 登录失败 (仍在登录页)", "ERROR")
            self.save_debug("login_fail")
            return False
        except Exception as e:
            self.log(f"登录过程出错: {e}", "ERROR")
            self.save_debug("login_error")
            return False

    def process_renewal(self):
        results = []
        try:
            if "dashboard" not in self.page.url:
                self.page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
                self.check_cf()

            # 查找 'See' 按钮 (查看服务器详情)
            selector = "a:has-text('See'), button:has-text('See')"
            try: self.page.wait_for_selector(selector, timeout=20000)
            except:
                self.log("⚠️ 未找到 'See' 按钮 (可能无服务器)", "WARNING")
                return []

            count = self.page.locator(selector).count()
            self.log(f"📦 发现 {count} 个服务器", "SUCCESS")

            for i in range(count):
                self.log(f"--- 处理第 {i+1} 个服务器 ---", "INFO")
                
                # 确保回到 Dashboard
                if "dashboard" not in self.page.url:
                    self.page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
                    self.check_cf()
                    time.sleep(2)
                
                # 点击 See
                see_btn = self.page.locator(selector).nth(i)
                if not see_btn.is_visible(): continue
                
                try:
                    see_btn.click()
                    self.page.wait_for_load_state("domcontentloaded", timeout=60000)
                    self.check_cf()
                except: pass

                try: sid = self.page.url.split("id=")[1].split("&")[0]
                except: sid = f"Server_{i+1}"

                # 寻找续期按钮
                btn_found = False
                for txt in RENEW_TEXTS:
                    # 查找包含特定文本的按钮或链接
                    btn = self.page.locator(f"button:has-text('{txt}'), a.btn:has-text('{txt}')")
                    try: btn.first.wait_for(state="visible", timeout=3000)
                    except: pass

                    if btn.count() > 0:
                        btn_el = btn.first
                        if btn_el.is_disabled():
                            self.log(f"[{sid}] 按钮禁用 (冷却中)", "WARNING")
                            results.append({"id": sid, "status": "⏳ 冷却中"})
                        else:
                            # =================================================
                            # 核心策略：双重点击 + CF检测
                            # =================================================
                            
                            # 1. 第一次点击
                            self.log(f"[{sid}] ⚡ 第 1 次点击 '{txt}'...", "INFO")
                            try: btn_el.click(timeout=5000)
                            except: pass
                            
                            # 等待 CF 可能出现
                            self.log(f"[{sid}] 等待 5 秒 (检测跳转/CF)...", "INFO")
                            time.sleep(5)
                            self.check_cf()
                            
                            # 2. 第二次点击 (如果按钮还在)
                            if btn_el.is_visible() and btn_el.is_enabled():
                                self.log(f"[{sid}] ⚡ 第 2 次点击 (补刀)...", "INFO")
                                try: btn_el.click(timeout=5000)
                                except: pass
                                time.sleep(5)

                            # 3. 结果检测
                            page_content = self.page.content().lower()
                            
                            if "successfully" in page_content or "success" in page_content:
                                self.log(f"[{sid}] ✅ 续期成功！", "SUCCESS")
                                results.append({"id": sid, "status": "✅ 成功"})
                            
                            elif "can't renew" in page_content or "wait until" in page_content:
                                msg = "未到期/冷却中"
                                self.log(f"[{sid}] ⏳ {msg}", "WARNING")
                                results.append({"id": sid, "status": f"⏳ {msg}"})
                            
                            else:
                                self.log(f"[{sid}] ❓ 未知状态 (可能已成功)", "INFO")
                                results.append({"id": sid, "status": "❓ 未知"})

                        btn_found = True
                        break
                
                if not btn_found:
                    # 检查是否因为已经是 "未到期" 状态导致没有按钮
                    if "can't renew" in self.page.content().lower() or "wait until" in self.page.content().lower():
                        self.log(f"[{sid}] ⏳ 页面提示未到期", "WARNING")
                        results.append({"id": sid, "status": "⏳ 未到期"})
                    else:
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
        if not results: content += "| - | 登录失败或无数据 |\n"
        for r in results: content += f"| {r['id']} | {r['status']} |\n"
        try:
            with open("README.md", "w") as f: f.write(content)
        except: pass

    def run(self):
        if not LOGIN_EMAIL or not LOGIN_PASSWORD:
            self.log("未设置账号密码环境变量", "ERROR")
            sys.exit(1)
            
        with sync_playwright() as p:
            self.log("启动浏览器...", "INFO")
            # 关键启动参数
            browser = p.chromium.launch(
                headless=HEADLESS, 
                args=[
                    "--no-sandbox", 
                    "--disable-blink-features=AutomationControlled", # 隐藏自动化特征
                    "--disable-infobars"
                ]
            )
            
            # 使用 stealth 插件配置上下文
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            
            # ★ 尝试加载 Stealth 插件 (绕过 CF 检测的核心) ★
            try:
                from playwright_stealth import stealth_sync
                stealth_sync(context)
                self.log("已启用 Stealth 模式", "INFO")
            except ImportError:
                self.log("未安装 playwright-stealth，建议 pip install playwright-stealth", "WARNING")

            # 注入 cf_clearance (必须是有效值)
            if CF_CLEARANCE: 
                context.add_cookies([{'name': 'cf_clearance', 'value': CF_CLEARANCE, 'domain': '.katabump.com', 'path': '/'}])
            
            self.page = context.new_page()
            self.page.set_default_timeout(60000)

            if self.login():
                results = self.process_renewal()
                self.update_readme(results)
            else:
                self.update_readme([]) # 记录失败
                sys.exit(1)
            
            browser.close()

if __name__ == "__main__":
    KataBot().run()
