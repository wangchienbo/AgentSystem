"""Pipeline Orchestrator — 管道编排器

负责：
1. 按模板顺序执行模块
2. 处理模块间依赖（前序模块的输出自动传递给后续模块）
3. 进度记录和错误处理
4. 提供流式进度事件（供 UI 展示）
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """管道编排器"""

    def __init__(self):
        self._modules: dict[str, "BaseModule"] = {}

    def register(self, module: "BaseModule"):
        """注册一个模块"""
        self._modules[module.name] = module
        logger.info("Pipeline 模块注册: %s — %s", module.name, module.description)

    def get_step_names(self, template: str) -> list[str]:
        """获取管道模板的步骤顺序"""
        from .base import PIPELINE_TEMPLATES
        names = PIPELINE_TEMPLATES.get(template)
        if names is None:
            raise ValueError(f"未知管道模板: {template}，可用: {list(PIPELINE_TEMPLATES.keys())}")
        return names

    def list_templates(self) -> dict[str, list[str]]:
        from .base import PIPELINE_TEMPLATES
        return dict(PIPELINE_TEMPLATES)

    def list_modules(self) -> list[dict]:
        return [
            {"name": m.name, "desc": m.description, "modifies_storage": m.modifies_storage}
            for m in self._modules.values()
        ]

    async def run(
        self,
        template: str,
        ctx: "PipelineContext",
        progress_callback=None,
    ) -> "PipelineContext":
        """执行管道

        Args:
            template: 管道模板名称
            ctx: 管道上下文（已初始化）
            progress_callback: 可选，每步完成后的回调 (module_name, status, summary)
        """
        step_names = self.get_step_names(template)
        logger.info("Pipeline 启动: template=%s, steps=%s", template, step_names)

        for idx, name in enumerate(step_names):
            module = self._modules.get(name)
            if module is None:
                err = f"模块未注册: {name}"
                logger.error(err)
                ctx.record_step(name, "error", err)
                raise RuntimeError(err)

            logger.info("  [%d/%d] %s — %s", idx + 1, len(step_names), name, module.description)
            ctx.record_step(name, "running", f"正在{module.description}...")
            if progress_callback:
                progress_callback(name, "running", module.description)

            try:
                ctx = await module.execute(ctx)

                # 如果模块修改了 storage，刷新上下文中的小说数据
                if module.modifies_storage:
                    ctx.refresh_novel()

                # 更新进度
                ctx.record_step(name, "done", f"{module.description}完成")
                if progress_callback:
                    progress_callback(name, "done", module.description)

            except Exception as e:
                import traceback
                logger.error("Pipeline 步骤失败 %s: %s\n%s", name, e, traceback.format_exc())
                ctx.record_step(name, "error", f"{module.description}失败: {str(e)}")
                if progress_callback:
                    progress_callback(name, "error", str(e))
                raise

        logger.info("Pipeline 完成: template=%s, %d steps", template, len(step_names))
        return ctx


# 全局编排器实例（实际在 bootstrap 时注册模块）
_orchestrator = PipelineOrchestrator()


def get_orchestrator() -> PipelineOrchestrator:
    return _orchestrator
