"""Concentration タブ確認"""
from playwright.sync_api import sync_playwright

PORT = 8503
URL = f"http://localhost:{PORT}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 950})
    page.goto(URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)

    tabs = page.locator("[data-testid='stTab']").all()
    for tab in tabs:
        if "Concentration" in tab.inner_text(timeout=1000):
            tab.click()
            break
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2500)

    # 全体スクリーンショット
    page.screenshot(path="C:/tmp/concentration_all.png", full_page=False)
    print("[OK] スクリーンショット保存")

    body = page.locator("body").inner_text(timeout=5000)
    if "80%" in body:
        idx = body.index("80%")
        print(f"[OK] {body[max(0,idx-5):idx+100]}")

    browser.close()
