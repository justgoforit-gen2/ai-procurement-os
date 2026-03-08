"""Playwright test: 拠点フィルタで「本社（東京）」を選択したときの挙動を確認"""
import sys
from playwright.sync_api import sync_playwright

PORT = 8502
URL = f"http://localhost:{PORT}"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(URL)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)

    # --- スクリーンショット: 初期状態 ---
    page.screenshot(path="/tmp/honsha_01_initial.png", full_page=False)
    print("[OK] 初期スクリーンショット保存")

    # --- コンソールエラーを収集 ---
    errors = []
    page.on("console", lambda msg: errors.append(f"[{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)

    # --- サイドバーの「拠点」multiselect を探す ---
    # Streamlit multiselect は data-testid="stMultiSelect" を持つ
    multiselects = page.locator("[data-testid='stMultiSelect']").all()
    print(f"[OK] multiselect 数: {len(multiselects)}")

    # 各 multiselect のラベルを表示
    label_texts = []
    for ms in multiselects:
        try:
            label = ms.locator("label").first.inner_text(timeout=2000)
            label_texts.append(label)
        except Exception:
            label_texts.append("(no label)")
    print(f"[OK] ラベル一覧: {label_texts}")

    # 「拠点」の multiselect を探す
    site_ms = None
    for ms, label in zip(multiselects, label_texts):
        if "拠点" in label:
            site_ms = ms
            print(f"[OK] 拠点 multiselect 発見: '{label}'")
            break

    if site_ms is None:
        print("[--] 拠点 multiselect が見つかりません")
        browser.close()
        sys.exit(1)

    # --- 拠点 multiselect をクリックしてドロップダウンを開く ---
    bb = site_ms.bounding_box()
    print(f"[OK] 拠点 bounding_box: {bb}")
    page.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2)
    page.wait_for_timeout(800)
    page.screenshot(path="/tmp/honsha_02_dropdown.png", full_page=False)
    print("[OK] ドロップダウンスクリーンショット保存")

    # --- オプション一覧を取得 ---
    options = page.locator("[role='option']").all()
    if not options:
        options = page.locator("[data-baseweb='menu'] li").all()
    print(f"[OK] オプション数: {len(options)}")
    option_texts = [o.inner_text(timeout=1000) for o in options]
    print(f"[OK] オプション: {option_texts}")

    # --- 「本社（東京）」を選択 ---
    honsha_opt = None
    for opt, txt in zip(options, option_texts):
        if "本社" in txt:
            honsha_opt = opt
            print(f"[OK] 「本社」オプション発見: '{txt}'")
            break

    if honsha_opt is None:
        print("[--] 「本社」オプションが見つかりません。利用可能なオプション:", option_texts)
        browser.close()
        sys.exit(1)

    honsha_opt.click()
    page.wait_for_timeout(2000)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)

    page.screenshot(path="/tmp/honsha_03_after_select.png", full_page=True)
    print("[OK] 選択後スクリーンショット保存")

    # --- エラーメッセージを探す ---
    error_boxes = page.locator("[data-testid='stException'], [data-testid='stAlert'], .stException").all()
    print(f"[OK] エラーボックス数: {len(error_boxes)}")
    for i, eb in enumerate(error_boxes):
        try:
            txt = eb.inner_text(timeout=2000)
            print(f"[ERROR BOX {i}] {txt[:500]}")
        except Exception as e:
            print(f"[ERROR BOX {i}] テキスト取得失敗: {e}")

    # --- ページ全体のテキストからエラーキーワードを探す ---
    body_text = page.locator("body").inner_text(timeout=5000)
    for keyword in ["Error", "Exception", "Traceback", "KeyError", "ValueError", "AttributeError", "TypeError"]:
        if keyword in body_text:
            idx = body_text.index(keyword)
            snippet = body_text[max(0, idx-50):idx+300]
            print(f"\n[FOUND '{keyword}']\n{snippet}\n")
            break

    # --- コンソールエラー ---
    if errors:
        print(f"\n[CONSOLE ERRORS] {len(errors)} 件:")
        for e in errors:
            print(f"  {e}")
    else:
        print("[OK] コンソールエラーなし")

    # --- Tab6 (Supplier Map) に移動して確認 ---
    tabs = page.locator("[data-testid='stTab']").all()
    print(f"\n[OK] タブ数: {len(tabs)}")
    tab_texts = [t.inner_text(timeout=1000) for t in tabs]
    print(f"[OK] タブ: {tab_texts}")

    for tab, txt in zip(tabs, tab_texts):
        if "Map" in txt or "Supplier" in txt or "マップ" in txt or "地図" in txt:
            tab.click()
            page.wait_for_timeout(2000)
            page.screenshot(path="/tmp/honsha_04_supplier_map.png", full_page=True)
            print(f"[OK] Tab '{txt}' スクリーンショット保存")
            # エラー再チェック
            error_boxes2 = page.locator("[data-testid='stException'], [data-testid='stAlert']").all()
            for i, eb in enumerate(error_boxes2):
                try:
                    print(f"[ERROR IN MAP TAB {i}] {eb.inner_text(timeout=2000)[:500]}")
                except Exception:
                    pass
            break

    browser.close()
    print("\n[DONE] テスト完了")
