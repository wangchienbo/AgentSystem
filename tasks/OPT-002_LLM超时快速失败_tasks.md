# Task List: OPT-002 - LLM 超时快速失败机制
**状态**: 🟢 执行中
**优先级**: P0 (阻塞解除)
**目标**: LLM 请求超时从 30s+ 降低到 <3s，并给出明确错误指引

## Phase 1: 诊断 (Diagnose)
- [x] T1.1: 确认超时根因 (LLM API 配置/网络问题)
- [ ] T1.2: 定位超时配置代码 (`model_client.py` 或 `config.yaml`)

## Phase 2: 实现 (Implement)
- [ ] T2.1: 修改 `model_client.py` 添加 `timeout=5s` 参数
- [ ] T2.2: 修改错误处理：超时返回明确错误信息 "LLM 配置错误，请检查 config.yaml"
- [ ] T2.3: 添加 `/api/health` 接口，检查 LLM 连通性

## Phase 3: 验证 (Verify)
- [ ] T3.1: 重启服务，发送测试请求
- [ ] T3.2: 验证响应时间 < 3s 且错误信息明确
- [ ] T3.3: 记录修复日志

## Phase 4: 恢复 (Resume)
- [ ] T4.1: LLM 配置修复后，重新激活 OPT-001
- [ ] T4.2: 归档 OPT-002
