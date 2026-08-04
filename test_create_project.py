"""端到端测试：新建项目 → 保存配置 → 验证状态"""
import sys, time
from playwright.sync_api import sync_playwright

PASS = []
FAIL = []

def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  ✅ {name}")
    else:
        FAIL.append(f"{name}: {detail}")
        print(f"  ❌ {name} — {detail}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    # 捕获 console 错误
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    print("1. 打开页面")
    page.goto("http://localhost:8501")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    check("页面加载无 JS 错误", len(errors) == 0, "; ".join(errors[:3]))

    print("2. 截图：欢迎页")
    page.screenshot(path="/workspace/test_01_welcome.png", full_page=True)

    print("3. 选择「➕ 新建项目…」")
    # 找到侧边栏的 selectbox
    select = page.locator('[data-baseweb="select"]').first
    check("侧边栏 selectbox 存在", select.count() > 0)
    select.click()
    page.wait_for_timeout(500)
    # 点「➕ 新建项目…」
    new_opt = page.locator('li:has-text("新建项目")')
    check("「新建项目」选项存在", new_opt.count() > 0)
    if new_opt.count() > 0:
        new_opt.click()
        page.wait_for_timeout(1500)

    print("4. 输入项目名 test_cloud")
    # 找到 text input
    name_input = page.locator('input[aria-label="项目名 (英文/拼音)"]')
    if name_input.count() == 0:
        # try placeholder
        name_input = page.locator('input[placeholder="my_event"]')
    check("项目名输入框存在", name_input.count() > 0)
    if name_input.count() > 0:
        name_input.fill("test_cloud")
        page.wait_for_timeout(500)

    print("5. 点击「创建项目」")
    create_btn = page.locator('button:has-text("创建项目")')
    check("「创建项目」按钮存在", create_btn.count() > 0)
    if create_btn.count() > 0:
        create_btn.click()
        page.wait_for_timeout(3000)

    print("6. 截图：创建后")
    page.screenshot(path="/workspace/test_02_after_create.png", full_page=True)

    # 检查是否进入了配置 Tab（应该自动看到配置表单）
    config_header = page.locator('text=配置')
    check("创建后进入配置页", config_header.count() > 0)

    print("7. 切到「运行」Tab")
    run_tab = page.locator('button:has-text("运行")')
    if run_tab.count() > 0:
        run_tab.click()
        page.wait_for_timeout(2000)

    page.screenshot(path="/workspace/test_03_run_tab.png", full_page=True)

    # 检查 KPI 卡片
    kpi = page.locator('text=已完成')
    check("运行 Tab 有 KPI 卡片", kpi.count() > 0)

    print("8. 切到「配置」Tab，保存配置")
    cfg_tab = page.locator('button:has-text("配置")')
    if cfg_tab.count() > 0:
        cfg_tab.click()
        page.wait_for_timeout(2000)

    save_btn = page.locator('button:has-text("保存配置")')
    check("「保存配置」按钮存在", save_btn.count() > 0)
    if save_btn.count() > 0:
        save_btn.click()
        page.wait_for_timeout(2000)

    page.screenshot(path="/workspace/test_04_after_save.png", full_page=True)

    # 检查成功提示
    success = page.locator('text=配置已保存')
    check("配置保存成功", success.count() > 0)

    print("9. 检查文件系统")
    import os
    cfg_file = os.path.exists("/workspace/outputs/test_cloud/.state/config.yaml")
    check("config.yaml 文件已创建", cfg_file, str(os.listdir("/workspace/outputs/test_cloud/.state/") if os.path.exists("/workspace/outputs/test_cloud/.state/") else "dir not found"))

    print("10. 切到「项目」Tab")
    proj_tab = page.locator('button:has-text("项目")')
    if proj_tab.count() > 0:
        proj_tab.click()
        page.wait_for_timeout(2000)

    page.screenshot(path="/workspace/test_05_project_tab.png", full_page=True)

    # 检查表格里有 test_cloud
    table_row = page.locator('text=test_cloud')
    check("项目表格里有 test_cloud", table_row.count() > 0)

    print("11. 检查控制台错误")
    check("无页面 JS 错误", len(errors) == 0, "; ".join(errors[:5]))

    browser.close()

print(f"\n{'='*50}")
print(f"通过: {len(PASS)}/{len(PASS)+len(FAIL)}")
if FAIL:
    print("失败:")
    for f in FAIL:
        print(f"  ❌ {f}")
    sys.exit(1)
else:
    print("全部通过!")
