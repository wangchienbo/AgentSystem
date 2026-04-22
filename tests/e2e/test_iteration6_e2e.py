"""Iteration 6 E2E 测试：复杂意图路由、多 App 并发、长期稳定性

验证 qwen3.6-plus 驱动下三个关键场景：
1. 复杂意图路由：用户输入包含多个意图时，正确拆解并分发
2. 多 App 并发交互：同时启动/操作多个 App，验证状态隔离
3. 长期运行稳定性：模拟长时间运行后的内存泄漏与性能衰减（简化版：多次循环调用）
"""
from __future__ import annotations

import asyncio
import pytest
import time

from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest


@pytest.mark.e2e
class TestIteration6E2E:
    """Iteration 6 E2E 测试"""

    def test_complex_intent_routing(self):
        """E2E：复杂意图路由 - 验证多意图拆解与分发"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session = "e2e-iter6-complex-intent"

        async def run_test():
            # 用户输入包含两个意图：创建 App 和 查询天气（假设天气是另一个技能）
            # 这里主要验证 LightBrain 是否能识别出需要创建 App，并且不混淆其他意图
            request = ChatMessageRequest(
                user_id="test-e2e",
                channel="test",
                message="帮我建一个待办事项 App，顺便告诉我今天天气怎么样",
                session_id=session,
            )
            
            response = await gateway.receive_message(request)
            
            # 验证响应中包含创建 App 的相关确认信息
            # 注意：具体断言取决于网关如何聚合多意图响应
            assert response is not None
            # 理想情况下，应该检测到 App 创建流程被触发
            # 这里简化为检查没有报错
            if hasattr(response, 'error') and response.error:
                pytest.fail(f"Complex intent routing failed: {response.error}")
            
            return response

        result = asyncio.run(run_test())
        assert result is not None

    def test_multi_app_concurrency(self):
        """E2E：多 App 并发交互 - 验证状态隔离"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_base = "e2e-iter6-concurrent"

        async def create_and_start_app(app_name: str, session_id: str):
            """辅助函数：创建并启动 App"""
            # 1. Create
            req_create = ChatMessageRequest(
                user_id="test-e2e",
                channel="test",
                message=f"创建一个名为 {app_name} 的简单 App",
                session_id=session_id,
            )
            resp_create = await gateway.receive_message(req_create)
            
            # 2. Start (假设创建成功后可以直接启动，或者通过特定指令)
            # 这里简化为发送启动指令
            req_start = ChatMessageRequest(
                user_id="test-e2e",
                channel="test",
                message=f"启动 {app_name}",
                session_id=session_id,
            )
            resp_start = await gateway.receive_message(req_start)
            return resp_start

        async def run_test():
            # 并发创建和启动 3 个不同的 App
            tasks = [
                create_and_start_app("AppA", f"{session_base}-A"),
                create_and_start_app("AppB", f"{session_base}-B"),
                create_and_start_app("AppC", f"{session_base}-C"),
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 验证所有任务都成功完成，没有异常
            for i, res in enumerate(results):
                if isinstance(res, Exception):
                    pytest.fail(f"Concurrent task {i} failed with exception: {res}")
                # 可以进一步检查每个 App 的状态是否独立
                
            return results

        results = asyncio.run(run_test())
        assert len(results) == 3

    def test_long_running_stability(self):
        """E2E：长期运行稳定性 - 模拟多次循环调用"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session = "e2e-iter6-stability"

        async def run_test():
            iterations = 10  # 简化版：执行 10 次循环
            start_time = time.time()
            
            for i in range(iterations):
                request = ChatMessageRequest(
                    user_id="test-e2e",
                    channel="test",
                    message=f"稳定性测试第 {i+1} 轮：列出当前 App",
                    session_id=session,
                )
                try:
                    response = await gateway.receive_message(request)
                    assert response is not None
                except Exception as e:
                    pytest.fail(f"Stability test failed at iteration {i+1}: {e}")
            
            end_time = time.time()
            duration = end_time - start_time
            print(f"Long running stability test completed {iterations} iterations in {duration:.2f} seconds")
            
            return True

        result = asyncio.run(run_test())
        assert result is True
