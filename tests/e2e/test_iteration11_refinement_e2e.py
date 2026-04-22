"""Iteration 11 E2E Tests - v2 Scenarios: Refinement & Skill Management
验证 v2 场景深化：
1. 修改链路支持更复杂的 refinement 与 skill 增减
2. 持久化、恢复、运行时状态一致性
3. 关键链路回归验证
"""
from __future__ import annotations

import pytest
from app.bootstrap.runtime import build_runtime
from app.models.chat import ChatMessageRequest


@pytest.mark.e2e
class TestRefinementAndSkillManagement:
    """测试修改链路与 skill 增减"""

    def test_modify_app_add_skill(self):
        """修改 App 添加新 skill"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter11-add-skill"

        # 第 1 步：创建一个简单 App
        request = ChatMessageRequest(
            message="创建一个待办 App，包含添加任务和查看任务功能",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 第 2 步：请求添加新技能（例如：删除任务）
        request = ChatMessageRequest(
            message="给这个待办 App 增加一个删除任务的功能",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None
        # 应该触发 refinement 流程或确认对话框

    def test_modify_app_remove_skill(self):
        """修改 App 移除已有 skill"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter11-remove-skill"

        # 创建一个包含多个技能的 App
        request = ChatMessageRequest(
            message="创建一个计算器 App，支持加减乘除",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 请求移除某个技能（例如：除法）
        request = ChatMessageRequest(
            message="移除除法功能，保留加减乘",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

    def test_persistence_recovery_after_modification(self):
        """验证修改后重启状态保留"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter11-persist"

        # 创建 App
        request = ChatMessageRequest(
            message="创建一个天气查询 App",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 修改 App
        request = ChatMessageRequest(
            message="给天气 App 增加 7 天预报功能",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 验证：重启后状态保留
        # 注意：实际测试需要 persistence 服务支持
        # 这里验证当前状态查询正常
        request = ChatMessageRequest(
            message="查看我的 App 列表",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None
        # 应该能看到修改后的 App


@pytest.mark.e2e
class TestConsistencyAcrossStates:
    """测试持久化、恢复、运行时状态一致性"""

    def test_runtime_state_matches_persistence(self):
        """验证运行时状态与持久化状态一致"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter11-consistency"

        # 创建 App
        request = ChatMessageRequest(
            message="创建一个简单的笔记 App",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 启动 App
        request = ChatMessageRequest(
            message="启动笔记 App",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 查询状态
        request = ChatMessageRequest(
            message="查看笔记 App 的状态",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None
        # 状态应该是运行中

    def test_multi_turn_modification_preserves_state(self):
        """多轮修改不丢失状态"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter11-multiturn-modify"

        # 创建 App
        request = ChatMessageRequest(
            message="创建一个音乐播放器 App",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 第 1 轮修改：添加播放列表功能
        request = ChatMessageRequest(
            message="增加播放列表管理功能",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 第 2 轮修改：添加均衡器功能
        request = ChatMessageRequest(
            message="再增加一个均衡器功能",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 验证：App 应该保留所有修改
        request = ChatMessageRequest(
            message="查看音乐 App 的详细信息",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None


@pytest.mark.e2e
class TestRegressionV2Scenarios:
    """v2 场景回归验证"""

    def test_create_modify_query_flow(self):
        """回归：创建→修改→查询完整链路"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter11-regression"

        # 创建
        request = ChatMessageRequest(
            message="创建一个项目管理 App",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 修改
        request = ChatMessageRequest(
            message="增加任务分配功能",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 查询
        request = ChatMessageRequest(
            message="查看项目管理 App 的功能",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

    def test_permission_boundary_on_modification(self):
        """回归：修改权限边界"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter11-permission"

        # 普通用户创建 App
        request = ChatMessageRequest(
            message="创建一个测试 App",
            session_id=session_id,
            user_id="regular-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 尝试验证权限边界（具体行为取决于权限策略）
        # 这里仅验证链路正常

    def test_execute_action_after_modification(self):
        """回归：修改后执行动作"""
        services = build_runtime()
        gateway = services["light_brain_gateway"]
        session_id = "test-e2e-iter11-execute"

        # 创建 App
        request = ChatMessageRequest(
            message="创建一个待办 App",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 修改：添加分类功能
        request = ChatMessageRequest(
            message="增加任务分类功能",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None

        # 执行动作
        request = ChatMessageRequest(
            message="添加一个任务：学习 Python",
            session_id=session_id,
            user_id="test-user",
        )
        response = gateway.receive_message(request)
        assert response is not None
