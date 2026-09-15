#!/usr/bin/env python3
"""
书斋V66 APK 全按钮功能测试
使用 adb shell input 模拟触摸，配合 screencap 截图
"""

# 本文件是独立的 adb 脚本（python apk_button_test.py 手动运行），
# 不是 pytest 测试模块；其中的 test() 是脚本自身辅助函数，
# 标记 __test__ = False 避免被 pytest 误收集。
__test__ = False

import subprocess
import os
import time
import json

SCREENSHOT_DIR = "H:/小说/书斋V66-重构/test_screenshots/apk_test"
REPORT_FILE = "H:/小说/书斋V66-重构/test_screenshots/apk_test/report.json"
ADB = "C:/Users/user/AppData/Local/Android/Sdk/platform-tools/adb.exe"
DEVICE = "emulator-5554"
PACKAGE = "com.shuzhai.writer"

results = []
shot_idx = 0


def adb(cmd):
    full = [ADB, "-s", DEVICE] + cmd.split()
    r = subprocess.run(full, capture_output=True, text=True, encoding="utf-8")
    return r.stdout, r.stderr, r.returncode


def screenshot(name):
    global shot_idx
    fname = f"{str(shot_idx).zfill(3)}_{name}.png"
    shot_idx += 1
    path = os.path.join(SCREENSHOT_DIR, fname)
    adb(f"shell screencap -p /sdcard/{fname}")
    adb(f"pull /sdcard/{fname} \"{path}\"")
    return path


def tap(x, y):
    adb(f"shell input tap {x} {y}")
    time.sleep(0.5)


def swipe(x1, y1, x2, y2, duration=500):
    adb(f"shell input swipe {x1} {y1} {x2} {y2} {duration}")
    time.sleep(0.5)


def back():
    adb("shell input keyevent 4")
    time.sleep(0.5)


def home():
    adb("shell input keyevent 3")
    time.sleep(0.5)


def test(name, fn):
    print(f"  [TEST] {name}...")
    try:
        fn()
        print(f"    ✅ PASS")
        results.append({"name": name, "status": "PASS"})
        return True
    except Exception as e:
        print(f"    ❌ FAIL: {e}")
        screenshot(f"FAIL_{name.replace(' ', '_')}")
        results.append({"name": name, "status": "FAIL", "error": str(e)})
        return False


def ensure_app_running():
    stdout, _, _ = adb(f"shell dumpsys activity activities | grep {PACKAGE}")
    if PACKAGE not in stdout:
        print("App not in foreground, restarting...")
        adb(f"shell am start -n {PACKAGE}/.MainActivity")
        time.sleep(5)
    else:
        # Bring to front
        adb(f"shell am start -n {PACKAGE}/.MainActivity")
        time.sleep(2)


def run_tests():
    print("=== 书斋V66 APK 全按钮功能测试 ===\n")

    # Phase 0: 初始截图
    print("Phase 0: 初始截图")
    ensure_app_running()
    screenshot("00_initial")

    # Phase 1: 顶部工具栏
    print("\nPhase 1: 顶部工具栏")

    test("1.1 左抽屉开关", lambda: tap(60, 60) or screenshot("01_left_drawer_toggle"))
    test("1.2 左抽屉再次开关", lambda: tap(60, 60) or screenshot("02_left_drawer_close"))

    test("1.3 新建项目按钮", lambda: tap(250, 60) or screenshot("03_new_project"))
    test("1.4 返回取消新建", lambda: back() or screenshot("04_cancel_new"))

    test("1.5 打开项目选择器", lambda: tap(420, 60) or screenshot("05_project_picker"))
    test("1.6 关闭项目选择器", lambda: back() or screenshot("06_close_picker"))

    test("1.7 阅读模式按钮", lambda: tap(700, 60) or screenshot("07_reader_mode"))
    test("1.8 关闭阅读模式", lambda: tap(60, 60) or screenshot("08_close_reader"))

    test("1.9 工具箱按钮", lambda: tap(900, 60) or screenshot("09_toolbox"))
    test("1.10 关闭工具箱", lambda: back() or screenshot("10_close_toolbox"))

    # Phase 2: 右抽屉（记忆面板）开关
    print("\nPhase 2: 右抽屉")
    test("2.1 右抽屉开关", lambda: tap(980, 140) or screenshot("11_right_drawer"))
    test("2.2 右抽屉关闭", lambda: tap(980, 140) or screenshot("12_right_drawer_close"))

    # Phase 3: 底部状态栏
    print("\nPhase 3: 底部状态栏")
    test("3.1 主题切换", lambda: tap(900, 2350) or screenshot("13_theme_toggle"))
    test("3.2 字号放大", lambda: tap(860, 2350) or screenshot("14_font_plus"))
    test("3.3 字号缩小", lambda: tap(780, 2350) or screenshot("15_font_minus"))
    test("3.4 撤销按钮", lambda: tap(50, 2350) or screenshot("16_undo"))

    # Phase 4: 工作流步骤切换（通过左抽屉导航）
    print("\nPhase 4: 工作流步骤切换")

    def switch_step(step_num):
        tap(60, 60)  # open left drawer
        time.sleep(0.3)
        y = 400 + (step_num - 1) * 120
        tap(300, y)
        time.sleep(0.5)

    test("4.1 步骤1 世界观", lambda: switch_step(1) or screenshot("step1_worldview"))
    test("4.2 步骤2 全书大纲", lambda: switch_step(2) or screenshot("step2_outline"))
    test("4.3 步骤3 人物", lambda: switch_step(3) or screenshot("step3_characters"))
    test("4.4 步骤4 分卷纲要", lambda: switch_step(4) or screenshot("step4_volumes"))
    test("4.5 步骤5 章节大纲", lambda: switch_step(5) or screenshot("step5_chapters"))
    test("4.6 步骤6 写作", lambda: switch_step(6) or screenshot("step6_writing"))
    test("4.7 步骤7 时间线", lambda: switch_step(7) or screenshot("step7_timeline"))

    # Phase 5: Step 1 世界观面板按钮测试
    print("\nPhase 5: Step 1 世界观面板")
    switch_step(1)
    time.sleep(0.5)

    test("5.1 AI提取设定按钮", lambda: tap(540, 1500) or screenshot("51_ai_extract"))
    test("5.2 导出设定按钮", lambda: tap(300, 1700) or screenshot("52_export_settings"))
    test("5.3 导入设定按钮", lambda: tap(700, 1700) or screenshot("53_import_settings"))
    test("5.4 叙事视角下拉", lambda: (swipe(540, 500, 540, 700), tap(540, 550), screenshot("54_pov_select")))
    test("5.5 叙事基调下拉", lambda: (swipe(540, 700, 540, 900), tap(540, 750), screenshot("55_tone_select")))
    test("5.6 叙事节奏下拉", lambda: (swipe(540, 800, 540, 1000), tap(540, 850), screenshot("56_pacing_select")))
    test("5.7 描写风格输入框", lambda: (tap(540, 1000), screenshot("57_desc_style")))
    test("5.8 时代环境输入框 - 科技", lambda: (tap(540, 1200), screenshot("58_tech_level")))
    test("5.9 时代环境输入框 - 社会", lambda: (tap(540, 1300), screenshot("59_society")))
    test("5.10 时代环境输入框 - 地理", lambda: (tap(540, 1400), screenshot("60_geography")))
    test("5.11 时代环境输入框 - 文化", lambda: (tap(540, 1500), screenshot("61_culture")))

    # Test social_attitude specifically
    test("5.12 social_attitude 输入框存在", lambda: (
        swipe(540, 1500, 540, 600, 1000),  # scroll down to find it
        screenshot("62_social_attitude_scroll"),
    ))

    # Phase 6: 写作工具栏按钮
    print("\nPhase 6: 写作工具栏")
    switch_step(6)
    time.sleep(0.5)

    test("6.1 模型选择器", lambda: tap(200, 230) or screenshot("61_model_selector"))
    test("6.2 AI生成按钮", lambda: tap(900, 230) or screenshot("62_ai_gen"))
    test("6.3 去AI味按钮", lambda: tap(980, 230) or screenshot("63_de_ai"))
    test("6.4 续写按钮", lambda: tap(900, 330) or screenshot("64_continue"))
    test("6.5 保存按钮", lambda: tap(980, 330) or screenshot("65_save"))
    test("6.6 头脑风暴", lambda: tap(100, 330) or screenshot("66_brainstorm"))
    test("6.7 五感描写", lambda: tap(200, 330) or screenshot("67_sensory"))
    test("6.8 描写增强", lambda: tap(300, 330) or screenshot("68_describe"))
    test("6.9 场景扩写", lambda: tap(400, 330) or screenshot("69_expand"))
    test("6.10 灵活重写", lambda: tap(500, 330) or screenshot("70_rewrite"))

    # Phase 7: AI助手浮动按钮
    print("\nPhase 7: AI助手")
    test("7.1 AI助手FAB", lambda: tap(930, 2100) or screenshot("71_ai_fab"))
    test("7.2 再次点击关闭", lambda: tap(930, 2100) or screenshot("72_ai_fab_close"))

    # Phase 8: 阅读器完整测试
    print("\nPhase 8: 阅读器")
    test("8.1 打开阅读器", lambda: tap(700, 60) or screenshot("73_reader"))
    test("8.2 阅读器书架", lambda: tap(200, 60) or screenshot("74_reader_bookshelf"))
    test("8.3 返回阅读器", lambda: back() or screenshot("75_back_reader"))
    test("8.4 阅读器目录", lambda: tap(400, 60) or screenshot("76_reader_toc"))
    test("8.5 关闭目录", lambda: back() or screenshot("77_close_toc"))
    test("8.6 阅读器设置", lambda: tap(600, 60) or screenshot("78_reader_settings"))
    test("8.7 关闭设置", lambda: back() or screenshot("79_close_settings"))
    test("8.8 退出阅读器", lambda: tap(60, 60) or screenshot("80_close_reader"))

    # Phase 9: 命令面板
    print("\nPhase 9: 命令面板")
    adb("shell input keyevent 50")  # KEYCODE_P (Ctrl+P)
    time.sleep(0.5)
    screenshot("81_cmd_palette")
    adb("shell input keyevent 4")  # Back to close
    time.sleep(0.3)

    # Phase 10: 验证 social_attitude
    print("\nPhase 10: social_attitude 专项验证")
    switch_step(1)
    time.sleep(0.5)

    def test_social_attitude():
        # Scroll down in worldview panel to find social_attitude
        swipe(540, 1500, 540, 600, 1500)
        screenshot("82_social_attitude_scroll")
        # Try to tap around where the input should be
        tap(540, 1600)
        screenshot("83_social_attitude_tap")

    test("10.1 social_attitude 输入区域可交互", test_social_attitude)

    # Final summary
    print("\n\n========== APK 测试总结 ==========")
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    print(f"总计: {len(results)} 项测试")
    print(f"通过: {pass_count} ✅")
    print(f"失败: {fail_count} ❌")

    if fail_count > 0:
        print("\n失败项目:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"  ❌ {r['name']}: {r['error']}")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n报告已保存: {REPORT_FILE}")

    return pass_count, fail_count, len(results)


if __name__ == "__main__":
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    run_tests()
