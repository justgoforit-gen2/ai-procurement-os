"""
Playwright動作確認スクリプト: RFQ Workflow System
http://localhost:8510 が起動済みの前提で実行する
"""
import sys
from playwright.sync_api import sync_playwright, expect

BASE_URL = "http://localhost:8510"
PASS = "[PASS]"
FAIL = "[FAIL]"

results = []

def check(label: str, ok: bool, detail: str = ""):
    icon = PASS if ok else FAIL
    msg = f"{icon} {label}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    results.append((label, ok))

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_default_timeout(15000)

    # ── 1. トップページ読込 ────────────────────────────────────────────
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    title = page.title()
    check("ページタイトル", "RFQ" in title, title)

    # ── 2. サイドバーにロール選択がある ───────────────────────────────
    page.wait_for_selector("[data-testid='stSidebar']")
    sidebar_text = page.locator("[data-testid='stSidebar']").inner_text()
    check("サイドバー: ロール選択", "ロール" in sidebar_text)
    check("サイドバー: テナント表示", "Demo Company" in sidebar_text)

    # ── 3. タブが4つある ──────────────────────────────────────────────
    tabs = page.locator("[data-baseweb='tab']").all()
    check("メインタブ数 = 4", len(tabs) == 4, f"found {len(tabs)}")

    tab_labels = [t.inner_text() for t in tabs]
    check("ダッシュボードタブ", any("ダッシュボード" in t for t in tab_labels))
    check("RFQ作成タブ",       any("RFQ作成" in t for t in tab_labels))
    check("案件一覧タブ",       any("案件一覧" in t for t in tab_labels))
    check("案件詳細タブ",       any("案件詳細" in t for t in tab_labels))

    # ── 4. ダッシュボード: KPIメトリクスが表示される ──────────────────
    # st.metric のラベルは [data-testid='stMetric'] または div[data-testid]
    page.wait_for_timeout(3000)
    # メトリクスを複数のセレクタで探す
    m1 = page.locator("[data-testid='stMetric']").all()
    m2 = page.locator("[data-testid='metric-container']").all()
    metrics = m1 if m1 else m2
    check("KPIメトリクス 5個以上", len(metrics) >= 5, f"found {len(metrics)}")

    # ── 5. ダッシュボード: エラーがない ───────────────────────────────
    page_text = page.inner_text("body")
    no_error = "OperationalError" not in page_text and "Traceback" not in page_text
    check("ダッシュボード: エラーなし", no_error)

    # ── 6. RFQ作成タブに移動 ──────────────────────────────────────────
    rfq_tab = next((t for t in tabs if "RFQ作成" in t.inner_text()), None)
    if rfq_tab:
        rfq_tab.click()
        page.wait_for_load_state("networkidle")

        page_text2 = page.inner_text("body")
        check("RFQ作成タブ: 予算入力フィールド", "予算上限" in page_text2)
        check("RFQ作成タブ: カテゴリ大分類", "大分類" in page_text2)
        check("RFQ作成タブ: サプライヤー選定", "サプライヤー" in page_text2)
        check("RFQ作成タブ: 仕様書アップロード", "仕様書" in page_text2)
        check("RFQ作成タブ: NDA自動添付", "NDA" in page_text2)
        check("RFQ作成タブ: エラーなし",
              "OperationalError" not in page_text2 and "Traceback" not in page_text2)

    # ── 7. 案件一覧タブ ───────────────────────────────────────────────
    list_tab = next((t for t in page.locator("[data-baseweb='tab']").all() if "案件一覧" in t.inner_text()), None)
    if list_tab:
        list_tab.click()
        page.wait_for_load_state("networkidle")
        page_text3 = page.inner_text("body")
        check("案件一覧タブ: エラーなし",
              "OperationalError" not in page_text3 and "Traceback" not in page_text3)

    # ── 8. 案件詳細タブ ───────────────────────────────────────────────
    detail_tab = next((t for t in page.locator("[data-baseweb='tab']").all() if "案件詳細" in t.inner_text()), None)
    if detail_tab:
        detail_tab.click()
        page.wait_for_load_state("networkidle")
        page_text4 = page.inner_text("body")
        check("案件詳細タブ: エラーなし",
              "OperationalError" not in page_text4 and "Traceback" not in page_text4)

    # ── スクリーンショット ────────────────────────────────────────────
    page.goto(BASE_URL)
    page.wait_for_load_state("networkidle")
    page.screenshot(path="test_rfq_screenshot_dashboard.png", full_page=False)
    print(f"\nScreenshot saved: test_rfq_screenshot_dashboard.png")

    browser.close()

# ── 結果サマリ ──────────────────────────────────────────────────────────
print("\n" + "="*50)
passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
print(f"Results: {passed} passed, {failed} failed / {len(results)} total")
if failed > 0:
    print("FAILED tests:")
    for label, ok in results:
        if not ok:
            print(f"  {FAIL} {label}")
    sys.exit(1)
else:
    print("All tests passed!")
