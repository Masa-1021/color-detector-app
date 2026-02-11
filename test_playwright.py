#!/usr/bin/env python3
"""
Circle Detector - Playwright E2E テスト
"""

import json
import sys
from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:5000"
RESULTS = []


def log(test_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append((test_name, passed, detail))
    print(f"  [{status}] {test_name}" + (f" - {detail}" if detail else ""))


def run_tests():
    print("=" * 60)
    print("Circle Detector - Playwright E2E テスト")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        # ------------------------------------------------------------------
        # 1. ページ読み込み
        # ------------------------------------------------------------------
        print("\n--- 1. ページ読み込み ---")
        response = page.goto(BASE_URL)
        log("ページアクセス (200)", response.status == 200, f"status={response.status}")

        title = page.title()
        log("タイトル確認", "Circle Detector" in title, f"title={title}")

        header = page.locator(".app-title").text_content()
        log("ヘッダー表示", "Circle Detector" in header, f"header={header}")

        mode_label = page.locator("#mode-label").text_content()
        log("編集モード表示", "編集" in mode_label, f"mode={mode_label}")

        # ------------------------------------------------------------------
        # 2. 基本設定 UI
        # ------------------------------------------------------------------
        print("\n--- 2. 基本設定 UI ---")

        sta_select = page.locator("#sta-no1-select")
        log("STA_NO1セレクト表示", sta_select.is_visible())

        send_mode = page.locator("#send-mode-select")
        log("送信モードセレクト表示", send_mode.is_visible())

        # ------------------------------------------------------------------
        # 3. API テスト - Config
        # ------------------------------------------------------------------
        print("\n--- 3. API テスト ---")

        config_res = page.evaluate("() => fetch('/api/config').then(r => r.json())")
        log("GET /api/config", "station" in config_res, f"keys={list(config_res.keys())}")

        # ------------------------------------------------------------------
        # 4. 円の追加 (API経由)
        # ------------------------------------------------------------------
        print("\n--- 4. 円の追加 ---")

        add_circle_res = page.evaluate("""
            () => fetch('/api/circles', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: 'テスト円1', center_x: 100, center_y: 100, radius: 30})
            }).then(r => r.json())
        """)
        log("POST /api/circles (円1)", add_circle_res.get("success") is True,
            f"id={add_circle_res.get('id')}")
        circle1_id = add_circle_res.get("id")

        add_circle_res2 = page.evaluate("""
            () => fetch('/api/circles', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: 'テスト円2', center_x: 250, center_y: 150, radius: 25})
            }).then(r => r.json())
        """)
        log("POST /api/circles (円2)", add_circle_res2.get("success") is True,
            f"id={add_circle_res2.get('id')}")
        circle2_id = add_circle_res2.get("id")

        circles_res = page.evaluate("() => fetch('/api/circles').then(r => r.json())")
        log("GET /api/circles", len(circles_res) >= 2, f"count={len(circles_res)}")

        # ------------------------------------------------------------------
        # 5. 色の追加
        # ------------------------------------------------------------------
        print("\n--- 5. 色の追加 ---")

        add_color_res = page.evaluate(f"""
            () => fetch('/api/circles/{circle1_id}/colors', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    name: '赤', h_center: 0, h_range: 10,
                    s_min: 100, s_max: 255, v_min: 100, v_max: 255
                }})
            }}).then(r => r.json())
        """)
        log("POST /api/circles/{id}/colors (赤)", add_color_res.get("success") is True)

        add_color_res2 = page.evaluate(f"""
            () => fetch('/api/circles/{circle1_id}/colors', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    name: '緑', h_center: 60, h_range: 10,
                    s_min: 100, s_max: 255, v_min: 100, v_max: 255
                }})
            }}).then(r => r.json())
        """)
        log("POST /api/circles/{id}/colors (緑)", add_color_res2.get("success") is True)

        circle_detail = page.evaluate(f"() => fetch('/api/circles/{circle1_id}').then(r => r.json())")
        color_count = len(circle_detail.get("colors", []))
        log("円の色数確認", color_count == 2, f"colors={color_count}")

        # ------------------------------------------------------------------
        # 6. グループの追加
        # ------------------------------------------------------------------
        print("\n--- 6. グループの追加 ---")

        add_group_res = page.evaluate("""
            () => fetch('/api/groups', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    name: 'パトライト1', sta_no2: 'LINE01', sta_no3: 'EQUIP01', default_value: 0
                })
            }).then(r => r.json())
        """)
        log("POST /api/groups", add_group_res.get("success") is True,
            f"id={add_group_res.get('id')}")
        group_id = add_group_res.get("id")

        # 円をグループに追加
        assign_res1 = page.evaluate(f"""
            () => fetch('/api/groups/{group_id}/circles/{circle1_id}', {{
                method: 'POST'
            }}).then(r => r.json())
        """)
        log("円1をグループに追加", assign_res1.get("success") is True)

        assign_res2 = page.evaluate(f"""
            () => fetch('/api/groups/{group_id}/circles/{circle2_id}', {{
                method: 'POST'
            }}).then(r => r.json())
        """)
        log("円2をグループに追加", assign_res2.get("success") is True)

        group_detail = page.evaluate(f"() => fetch('/api/groups/{group_id}').then(r => r.json())")
        log("グループの円数確認", len(group_detail.get("circle_ids", [])) == 2,
            f"circle_ids={group_detail.get('circle_ids')}")

        # ------------------------------------------------------------------
        # 7. ルールの追加
        # ------------------------------------------------------------------
        print("\n--- 7. ルールの追加 ---")

        add_rule_res = page.evaluate(f"""
            () => fetch('/api/rules', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    group_id: {group_id},
                    priority: 100,
                    type: 'single',
                    conditions: [{{circle_id: {circle1_id}, color: '赤', blinking: false}}],
                    value: 10
                }})
            }}).then(r => r.json())
        """)
        log("POST /api/rules (単一ルール)", add_rule_res.get("success") is True,
            f"id={add_rule_res.get('id')}")

        add_rule_res2 = page.evaluate(f"""
            () => fetch('/api/rules', {{
                method: 'POST',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    group_id: {group_id},
                    priority: 90,
                    type: 'composite',
                    conditions: [
                        {{circle_id: {circle1_id}, color: '赤', blinking: false}},
                        {{circle_id: {circle2_id}, color: '緑', blinking: false}}
                    ],
                    value: 30
                }})
            }}).then(r => r.json())
        """)
        log("POST /api/rules (複合ルール)", add_rule_res2.get("success") is True,
            f"id={add_rule_res2.get('id')}")

        rules_res = page.evaluate("() => fetch('/api/rules').then(r => r.json())")
        log("GET /api/rules", len(rules_res) >= 2, f"count={len(rules_res)}")

        # ------------------------------------------------------------------
        # 8. 設定保存・再読み込み
        # ------------------------------------------------------------------
        print("\n--- 8. 設定保存 ---")

        save_res = page.evaluate("() => fetch('/api/config', {method:'POST'}).then(r => r.json())")
        log("POST /api/config (保存)", save_res.get("success") is True)

        # ------------------------------------------------------------------
        # 9. ステータス確認
        # ------------------------------------------------------------------
        print("\n--- 9. ステータスAPI ---")

        status_res = page.evaluate("() => fetch('/api/status').then(r => r.json())")
        log("GET /api/status", "running" in status_res, f"running={status_res.get('running')}")
        log("ステータス: 未実行", status_res.get("running") is False)

        # ------------------------------------------------------------------
        # 9b. MQTT API
        # ------------------------------------------------------------------
        print("\n--- 9b. MQTT API ---")

        mqtt_res = page.evaluate("() => fetch('/api/mqtt').then(r => r.json())")
        log("GET /api/mqtt", "broker" in mqtt_res and "connected" in mqtt_res,
            f"broker={mqtt_res.get('broker')}, connected={mqtt_res.get('connected')}")

        mqtt_update_res = page.evaluate("""
            () => fetch('/api/mqtt', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({broker: 'test-broker', port: 1884, topic: 'test/topic'})
            }).then(r => r.json())
        """)
        log("PUT /api/mqtt (設定更新)", mqtt_update_res.get("success") is True)

        # 設定が反映されたか確認
        mqtt_res2 = page.evaluate("() => fetch('/api/mqtt').then(r => r.json())")
        log("MQTT設定確認 (broker)", mqtt_res2.get("broker") == "test-broker",
            f"broker={mqtt_res2.get('broker')}")

        # 元に戻す
        page.evaluate("""
            () => fetch('/api/mqtt', {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({broker: 'localhost', port: 1883, topic: 'equipment/status'})
            }).then(r => r.json())
        """)

        # ------------------------------------------------------------------
        # 10. UI要素の確認
        # ------------------------------------------------------------------
        print("\n--- 10. UI要素の確認 ---")

        # リロードして設定を反映
        page.reload()
        page.wait_for_load_state("networkidle")

        # 実行ボタン
        run_btn = page.locator("#btn-toggle-mode")
        log("実行ボタン表示", run_btn.is_visible())
        log("実行ボタンテキスト", "実行" in run_btn.text_content(), f"text={run_btn.text_content()}")

        # 円追加ボタン（円設定タブ内）
        page.click('[data-tab="tab-circle"]')
        page.wait_for_timeout(300)
        add_btn = page.locator('#circle-editor-content button:has-text("円追加")')
        log("円追加ボタン表示", add_btn.count() > 0)

        # MQTT badge
        mqtt_badge = page.locator("#mqtt-badge")
        log("MQTTバッジ表示", mqtt_badge.is_visible())

        # フッター
        footer = page.locator(".app-footer")
        log("フッター表示", footer.is_visible())

        # 設定保存ボタン
        save_btn = page.locator("text=設定保存")
        log("設定保存ボタン表示", save_btn.is_visible())

        # ------------------------------------------------------------------
        # 11. レスポンシブ確認 (スマホ)
        # ------------------------------------------------------------------
        print("\n--- 11. レスポンシブ（スマホ）---")

        page.set_viewport_size({"width": 375, "height": 812})
        page.wait_for_timeout(500)

        tab_nav = page.locator(".tab-nav")
        tab_visible = tab_nav.is_visible()
        log("タブナビゲーション表示", tab_visible)

        # PC に戻す
        page.set_viewport_size({"width": 1280, "height": 800})
        page.wait_for_timeout(300)

        # ------------------------------------------------------------------
        # 12. スクリーンショット
        # ------------------------------------------------------------------
        print("\n--- 12. スクリーンショット ---")

        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        ss_path = "/home/sano/color_detector_app/docs/screenshot_edit_mode.png"
        page.screenshot(path=ss_path, full_page=True)
        log("編集モード スクリーンショット", True, ss_path)

        # ------------------------------------------------------------------
        # 13. 円の更新・削除テスト
        # ------------------------------------------------------------------
        print("\n--- 13. 更新・削除テスト ---")

        update_res = page.evaluate(f"""
            () => fetch('/api/circles/{circle1_id}', {{
                method: 'PUT',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{name: '更新済み円'}})
            }}).then(r => r.json())
        """)
        log("PUT /api/circles (更新)", update_res.get("success") is True,
            f"name={update_res.get('circle', {}).get('name')}")

        # 色の更新
        update_color_res = page.evaluate(f"""
            () => fetch('/api/circles/{circle1_id}/colors/赤', {{
                method: 'PUT',
                headers: {{'Content-Type': 'application/json'}},
                body: JSON.stringify({{
                    name: '赤', h_center: 5, h_range: 15,
                    s_min: 80, s_max: 255, v_min: 80, v_max: 255
                }})
            }}).then(r => r.json())
        """)
        log("PUT /api/circles/{id}/colors/赤 (更新)", update_color_res.get("success") is True)

        # 更新後の確認
        circle_after = page.evaluate(f"() => fetch('/api/circles/{circle1_id}').then(r => r.json())")
        updated_color = next((c for c in circle_after.get("colors", []) if c["name"] == "赤"), None)
        log("色の更新確認 (h_center=5)", updated_color and updated_color.get("h_center") == 5,
            f"h_center={updated_color.get('h_center') if updated_color else 'N/A'}")

        # 色の削除
        del_color_res = page.evaluate(f"""
            () => fetch('/api/circles/{circle1_id}/colors/緑', {{
                method: 'DELETE'
            }}).then(r => r.json())
        """)
        log("DELETE /api/circles/{id}/colors/緑", del_color_res.get("success") is True)

        # ルールの削除
        rule_id = add_rule_res2.get("id")
        del_rule_res = page.evaluate(f"""
            () => fetch('/api/rules/{rule_id}', {{method: 'DELETE'}}).then(r => r.json())
        """)
        log("DELETE /api/rules/{id}", del_rule_res.get("success") is True)

        # ------------------------------------------------------------------
        # 14. カメラステータス
        # ------------------------------------------------------------------
        # ------------------------------------------------------------------
        # 14b. Oracle DB パスワード表示/非表示テスト
        # ------------------------------------------------------------------
        print("\n--- 14b. Oracle DBパスワード表示/非表示 ---")

        # 接続設定タブに切り替え
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="tab-connection"]')
        page.wait_for_timeout(500)

        # パスワード欄の初期状態: type=password, 実パスワードが入っている
        pw_input = page.locator('#oracle-password-input')
        pw_type_before = pw_input.get_attribute('type')
        pw_value_before = pw_input.input_value()
        log("パスワード初期状態: type=password",
            pw_type_before == 'password',
            f"type={pw_type_before}")
        log("パスワード初期状態: 実パスワードが入っている",
            len(pw_value_before) > 0 and pw_value_before != '********',
            f"value length={len(pw_value_before)}")

        # 「表示」ボタンをクリック → type=text, 実パスワードが見える
        toggle_btn = pw_input.locator('..').locator('button.btn-pw-toggle')
        toggle_btn.click()
        page.wait_for_timeout(200)

        pw_type_after = pw_input.get_attribute('type')
        pw_value_after = pw_input.input_value()
        btn_text_after = toggle_btn.text_content().strip()
        log("表示ボタン押下後: type=text",
            pw_type_after == 'text',
            f"type={pw_type_after}")
        log("表示ボタン押下後: 実パスワードが表示される",
            pw_value_after == pw_value_before and pw_value_after != '********',
            f"value='{pw_value_after}'")
        log("表示ボタン押下後: ボタン文字=非表示",
            btn_text_after == '非表示',
            f"text='{btn_text_after}'")

        # 「非表示」ボタンをクリック → type=password に戻る
        toggle_btn.click()
        page.wait_for_timeout(200)

        pw_type_hidden = pw_input.get_attribute('type')
        pw_value_hidden = pw_input.input_value()
        btn_text_hidden = toggle_btn.text_content().strip()
        log("非表示ボタン押下後: type=password",
            pw_type_hidden == 'password',
            f"type={pw_type_hidden}")
        log("非表示ボタン押下後: 値が保持されている",
            pw_value_hidden == pw_value_before,
            f"value preserved={pw_value_hidden == pw_value_before}")
        log("非表示ボタン押下後: ボタン文字=表示",
            btn_text_hidden == '表示',
            f"text='{btn_text_hidden}'")

        # ------------------------------------------------------------------
        # 14c. Oracle DB 接続テスト
        # ------------------------------------------------------------------
        print("\n--- 14c. Oracle DB 接続テスト ---")

        # 接続テストボタンをクリック
        test_btn = page.locator('button:has-text("接続テスト")')
        test_btn.click()

        # 結果を待つ
        result_el = page.locator('#oracle-test-result')
        page.wait_for_timeout(5000)
        test_result_text = result_el.text_content().strip()
        log("接続テスト: 成功メッセージ",
            '接続成功' in test_result_text,
            f"result='{test_result_text}'")

        # ------------------------------------------------------------------
        # 15. カメラステータス
        # ------------------------------------------------------------------
        print("\n--- 15. カメラAPI ---")

        cam_status = page.evaluate("() => fetch('/api/camera/status').then(r => r.json())")
        log("GET /api/camera/status", "running" in cam_status,
            f"running={cam_status.get('running')}")

        # ------------------------------------------------------------------
        # クリーンアップ
        # ------------------------------------------------------------------
        browser.close()

    # ------------------------------------------------------------------
    # 結果サマリー
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    passed = sum(1 for _, p, _ in RESULTS if p)
    failed = sum(1 for _, p, _ in RESULTS if not p)
    total = len(RESULTS)
    print(f"結果: {passed}/{total} PASS, {failed}/{total} FAIL")

    if failed > 0:
        print("\n失敗テスト:")
        for name, p, detail in RESULTS:
            if not p:
                print(f"  - {name}: {detail}")

    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_tests())
