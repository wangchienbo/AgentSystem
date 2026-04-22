"""Iteration 8 E2E Tests - Governance Integration

验证 Phase I 治理模块的端到端集成：
1. 权限检查接入主路径
2. 审计日志框架
3. 成本配额模型
"""

import pytest
from pathlib import Path
from datetime import UTC, datetime

from app.governance.audit_logger import AuditLogger
from app.governance.cost_quota import CostQuotaManager, QuotaConfig, QuotaExceededError
from app.governance.policy_authority_service import PolicyAuthorityService
from app.services.runtime_state_store import RuntimeStateStore


class TestAuditLogger:
    """测试审计日志功能"""

    def test_audit_logger_initialization(self, tmp_path: Path) -> None:
        """审计日志初始化"""
        log_dir = tmp_path / "audit_logs"
        logger = AuditLogger(log_dir=str(log_dir))
        assert logger._log_dir.exists()
        assert logger._log_file.parent == log_dir

    def test_audit_logger_logs_success(self, tmp_path: Path) -> None:
        """记录成功的审计日志"""
        log_dir = tmp_path / "audit_logs"
        logger = AuditLogger(log_dir=str(log_dir))
        
        # 记录成功操作
        logger.log(
            action="create_app",
            user_id="user123",
            target_id="app:test-app",
            details={"reason": "user request"},
            result="success"
        )
        
        # 验证日志文件存在
        assert logger._log_file.exists()

    def test_audit_logger_logs_failure(self, tmp_path: Path) -> None:
        """记录失败的审计日志"""
        log_dir = tmp_path / "audit_logs"
        logger = AuditLogger(log_dir=str(log_dir))
        
        # 记录失败操作
        logger.log(
            action="start_app",
            user_id="user123",
            target_id="app:test-app",
            details={"error": "app not found"},
            result="failure",
            error_message="App does not exist"
        )
        
        # 验证日志文件存在
        assert logger._log_file.exists()


class TestCostQuotaManager:
    """测试成本配额管理"""

    def test_quota_manager_initialization(self) -> None:
        """配额管理器初始化"""
        config = QuotaConfig(
            llm_call_hourly=100,
            llm_call_daily=1000,
            tool_call_hourly=200,
            tool_call_daily=2000,
            app_create_daily=10,
            app_modify_daily=50,
            app_delete_daily=5
        )
        manager = CostQuotaManager(config=config)
        assert manager._config.llm_call_hourly == 100

    def test_quota_check_and_consume_success(self) -> None:
        """配额检查成功"""
        config = QuotaConfig(app_create_daily=5)
        manager = CostQuotaManager(config=config)
        
        # 消耗配额
        result = manager.check_and_consume("app_create", "user123")
        assert result is True

    def test_quota_check_exceeded(self) -> None:
        """配额超出"""
        config = QuotaConfig(app_create_daily=2)
        manager = CostQuotaManager(config=config)
        
        # 消耗 2 次
        manager.check_and_consume("app_create", "user123")
        manager.check_and_consume("app_create", "user123")
        
        # 第 3 次应该失败
        with pytest.raises(QuotaExceededError) as exc_info:
            manager.check_and_consume("app_create", "user123")
        
        assert exc_info.value.quota_type == "app_create"
        assert exc_info.value.limit == 2


class TestPolicyAuthorityService:
    """测试权限审批服务"""

    def test_policy_authority_initialization(self, tmp_path: Path) -> None:
        """权限服务初始化"""
        store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
        service = PolicyAuthorityService(store=store)
        assert service is not None

    def test_policy_authority_enforce(self, tmp_path: Path) -> None:
        """权限检查"""
        store = RuntimeStateStore(base_dir=str(tmp_path / "runtime"))
        service = PolicyAuthorityService(store=store)
        
        # 设置策略
        from app.models.policy_authority import AuthorityPolicyRecord
        policy = AuthorityPolicyRecord(
            scope="app_create",
            require_reviewer=False,
            allow_automatic=True,
            require_reason=False
        )
        service.set_policy(policy)
        
        # 执行权限检查
        result = service.enforce(
            scope="app_create",
            reviewer="system",
            reason="automated test",
            automatic=True
        )
        assert result.allowed is True


class TestGovernanceIntegration:
    """治理服务集成测试"""

    def test_governance_services_in_runtime(self, tmp_path: Path) -> None:
        """测试运行时治理服务集成"""
        from app.bootstrap.runtime import build_runtime
        
        services = build_runtime(
            runtime_store_base_dir=str(tmp_path / "runtime"),
            app_data_base_dir=str(tmp_path / "namespaces")
        )
        
        # 验证治理服务已注入
        assert "audit_logger" in services
        assert "cost_quota_manager" in services
        assert "policy_authority" in services

    def test_app_management_worker_with_governance(self, tmp_path: Path) -> None:
        """测试 AppManagementWorker 集成治理服务"""
        from app.bootstrap.runtime import build_runtime
        from app.system.workers.app_management_worker import AppManagementWorker
        
        services = build_runtime(
            runtime_store_base_dir=str(tmp_path / "runtime"),
            app_data_base_dir=str(tmp_path / "namespaces")
        )
        
        # 验证 AppManagementWorker 已接收治理服务
        app_mgmt: AppManagementWorker = services["app_mgmt_worker"]
        assert app_mgmt._audit_logger is not None
        assert app_mgmt._cost_quota_manager is not None
        assert app_mgmt._policy_authority_service is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
