#!/usr/bin/env python3
"""
AgentSystem 全链路场景测试脚本
测试: 基础对话、App创建、列表查看、生命周期管理等核心场景
"""

import requests
import json
import sys
import time

# 配置
BASE_URL = "http://101.34.58.220"
COOKIES_FILE = "/tmp/test_cookies.txt"

def print_result(name, success, response, expected=None):
    """打印测试结果"""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"\n{status} | {name}")
    if not success:
        print(f"   响应: {response}")
        if expected:
            print(f"   期望: {expected}")
    return success

def run_tests():
    """运行完整测试套件"""
    passed = 0
    failed = 0
    session = requests.Session()
    
    print("=" * 60)
    print("AgentSystem E2E 场景测试")
    print(f"目标: {BASE_URL}")
    print("=" * 60)
    
    # Test 1: 系统状态检查
    print("\n--- Test 1: 系统状态 ---")
    try:
        r = session.get(f"{BASE_URL}/api/status", timeout=10)
        if r.status_code == 200:
            data = r.json()
            success = data.get("status") == "ok"
            if print_result("API 状态检查", success, data, "status='ok'"):
                passed += 1
            else:
                failed += 1
        else:
            print_result("API 状态检查", False, f"HTTP {r.status_code}", "200")
            failed += 1
    except Exception as e:
        print_result("API 状态检查", False, str(e), "无异常")
        failed += 1
    
    # Test 2: 登录
    print("\n--- Test 2: 登录 ---")
    try:
        r = session.post(
            f"{BASE_URL}/login",
            data={"username": "test_user", "password": "test_pass"},
            timeout=10
        )
        # 简化登录可能返回 302 或 200
        success = r.status_code in [200, 302]
        if print_result("用户登录", success, f"HTTP {r.status_code}", "200 或 302"):
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print_result("用户登录", False, str(e), "无异常")
        failed += 1
    
    # Test 3: 基础问候
    print("\n--- Test 3: 基础对话 (问候) ---")
    try:
        r = session.post(
            f"{BASE_URL}/api/chat",
            json={"message": "你好", "session_id": f"test_{int(time.time())}"},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            content = data.get("content", "")
            # 期望包含问候或能力描述，而不是保底回复
            has_greeting = "你好" in content or "Hi" in content or "hello" in content.lower()
            has_fallback = "我还不会处理" in content or "试试说" in content
            success = has_greeting and not has_fallback
            if print_result("问候响应", success, content[:200], "包含问候语"):
                passed += 1
            else:
                failed += 1
        else:
            print_result("问候响应", False, f"HTTP {r.status_code}", "200")
            failed += 1
    except Exception as e:
        print_result("问候响应", False, str(e), "无异常")
        failed += 1
    
    # Test 4: 查询能力
    print("\n--- Test 4: 查询能力 ---")
    try:
        r = session.post(
            f"{BASE_URL}/api/chat",
            json={"message": "你能做什么", "session_id": f"test_{int(time.time())}"},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            content = data.get("content", "")
            has_fallback = "我还不会处理" in content or "试试说" in content
            has_capabilities = "App" in content or "创建" in content or "管理" in content or "能力" in content or "帮助" in content
            success = not has_fallback and has_capabilities
            if print_result("能力查询", success, content[:200], "描述系统能力"):
                passed += 1
            else:
                failed += 1
        else:
            print_result("能力查询", False, f"HTTP {r.status_code}", "200")
            failed += 1
    except Exception as e:
        print_result("能力查询", False, str(e), "无异常")
        failed += 1
    
    # Test 5: 查看 App 列表
    print("\n--- Test 5: 查看 App 列表 ---")
    try:
        r = session.post(
            f"{BASE_URL}/api/chat",
            json={"message": "看看我的 App", "session_id": f"test_{int(time.time())}"},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            content = data.get("content", "")
            has_fallback = "我还不会处理" in content
            success = not has_fallback  # 只要能正常响应就算成功，空列表也是正常
            if print_result("App 列表查询", success, content[:200], "返回 App 列表"):
                passed += 1
            else:
                failed += 1
        else:
            print_result("App 列表查询", False, f"HTTP {r.status_code}", "200")
            failed += 1
    except Exception as e:
        print_result("App 列表查询", False, str(e), "无异常")
        failed += 1
    
    # Test 6: 系统状态查询
    print("\n--- Test 6: 系统状态 ---")
    try:
        r = session.post(
            f"{BASE_URL}/api/chat",
            json={"message": "系统状态", "session_id": f"test_{int(time.time())}"},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            content = data.get("content", "")
            has_fallback = "我还不会处理" in content
            has_status = "状态" in content or "运行" in content or "正常" in content
            success = not has_fallback or has_status
            if print_result("系统状态查询", success, content[:200], "返回系统状态"):
                passed += 1
            else:
                failed += 1
        else:
            print_result("系统状态查询", False, f"HTTP {r.status_code}", "200")
            failed += 1
    except Exception as e:
        print_result("系统状态查询", False, str(e), "无异常")
        failed += 1
    
    # Test 7: 帮助查询
    print("\n--- Test 7: 帮助 ---")
    try:
        r = session.post(
            f"{BASE_URL}/api/chat",
            json={"message": "帮助", "session_id": f"test_{int(time.time())}"},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            content = data.get("content", "")
            has_fallback = "我还不会处理" in content
            has_help = "帮助" in content or "用法" in content or "指令" in content or "可以" in content
            success = not has_fallback and has_help
            if print_result("帮助查询", success, content[:200], "返回帮助信息"):
                passed += 1
            else:
                failed += 1
        else:
            print_result("帮助查询", False, f"HTTP {r.status_code}", "200")
            failed += 1
    except Exception as e:
        print_result("帮助查询", False, str(e), "无异常")
        failed += 1
    
    # 测试总结
    print("\n" + "=" * 60)
    print(f"测试完成: {passed} 通过, {failed} 失败")
    print("=" * 60)
    
    if failed > 0:
        print(f"\n⚠️  有 {failed} 个测试失败，需要修复")
        sys.exit(1)
    else:
        print("\n🎉 所有测试通过！")
        sys.exit(0)

if __name__ == "__main__":
    run_tests()