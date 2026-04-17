# Phase N.4：App 进程隔离 + 自注册

## 目标
把"每个 App 独立子进程"从概念推进到可运行的第一版。

## 执行清单

### N4-01 定义 App 进程启动协议
- [x] 确定子进程入口脚本（app.runtime.app_bootstrap + subprocess.Popen）
- [x] 定义进程间通信协议（JSON over stdin/stdout）
- [x] 定义进程启动参数格式（APP_INSTANCE_ID, APP_VERSION 等环境变量）

### N4-02 实现 App Process Launcher
- [x] AppProcessManager 管理子进程生命周期
- [x] 子进程继承 App 上下文（env 注入）
- [x] 父进程跟踪子进程 PID + 状态

### N4-03 App 进程自注册
- [x] 子进程启动时自动向 RuntimeCenter 注册
- [x] 心跳机制：子进程定期写入 runtime_center.json
- [x] 父进程探活：os.kill(pid, 0) + poll()

### N4-04 进程间通信最小闭环
- [x] AppProcessIPC: JSON 请求/响应通过 stdin/stdout
- [x] 超时机制（默认 30s）
- [x] 崩溃检测 + 状态标记

### N4-05 端到端验证
- [x] 启动 App → 独立进程运行 → 查询状态 → 停止 → 清理
- [x] 崩溃自动检测（crash_count 累计）
- [x] 多进程隔离验证（crash 一个不影响其他）

---

## 当前状态
Phase N.3 已完成，基础 subprocess 能力已落地（N3-08）。