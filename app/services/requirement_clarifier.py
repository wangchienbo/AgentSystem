from __future__ import annotations

import re

from app.models.requirement_spec import RequirementSpec
from app.services.requirement_router import RequirementRouter


class RequirementClarifierService:
    def __init__(self, router: RequirementRouter | None = None) -> None:
        self._router = router or RequirementRouter()

    def clarify(self, text: str) -> RequirementSpec:
        intent = self._router.route(text)
        normalized = intent.normalized_text

        goal = self._extract_goal(text)
        roles = self._extract_roles(normalized)
        inputs = self._extract_inputs(normalized)
        outputs = self._extract_outputs(normalized)
        constraints = self._extract_constraints(normalized)
        permissions = self._extract_permissions(normalized)
        failure_strategy = self._extract_failure_strategy(normalized)
        missing_fields = self._compute_missing_fields(
            requirement_type=intent.requirement_type,
            goal=goal,
            inputs=inputs,
            outputs=outputs,
        )
        recommended_questions = self._build_questions(missing_fields, intent.demonstration_decision)
        readiness = self._determine_readiness(intent.demonstration_decision, missing_fields, constraints)

        notes: list[str] = []
        if intent.requirement_type == "unclear":
            notes.append("当前需求类型仍偏模糊，建议先明确是 app、skill，还是两者组合。")
        if any("权限" in item or "审批" in item for item in constraints):
            notes.append("需求包含治理或权限边界，后续 blueprint 阶段应补充角色与授权规则。")

        return RequirementSpec(
            raw_text=text,
            requirement_type=intent.requirement_type,
            demonstration_decision=intent.demonstration_decision,
            goal=goal,
            roles=roles,
            inputs=inputs,
            outputs=outputs,
            constraints=constraints,
            permissions=permissions,
            failure_strategy=failure_strategy,
            needs_demo=intent.demonstration_decision == "required",
            missing_fields=missing_fields,
            readiness=readiness,
            recommended_questions=recommended_questions,
            extracted_keywords=intent.extracted_keywords,
            notes=notes,
        )

    def extract(self, text: str) -> RequirementSpec:
        return self.clarify(text)

    def readiness(self, text: str) -> dict:
        spec = self.clarify(text)
        return {
            "readiness": spec.readiness,
            "missing_fields": spec.missing_fields,
            "needs_demo": spec.needs_demo,
            "recommended_questions": spec.recommended_questions,
            "requirement_type": spec.requirement_type,
        }

    def _extract_goal(self, text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return ""
        compact = re.sub(r"\s+", " ", stripped)
        return compact[:160]

    def _extract_roles(self, text: str) -> list[str]:
        roles: list[str] = []
        for word in ["客服", "审批人", "管理员", "用户", "处理人", "agent"]:
            if word in text and word not in roles:
                roles.append(word)
        return roles

    def _extract_inputs(self, text: str) -> list[str]:
        candidates: list[str] = []
        if any(word in text for word in ["表单", "输入", "提交", "工单"]):
            candidates.append("user_input")
        if any(word in text for word in ["页面", "点击", "演示"]):
            candidates.append("ui_demonstration")
        if "日志" in text:
            candidates.append("runtime_log")
        return candidates

    def _extract_outputs(self, text: str) -> list[str]:
        candidates: list[str] = []
        if any(word in text for word in ["json", "结构化", "统一"]):
            candidates.append("structured_output")
        if any(word in text for word in ["记录", "日志", "审计"]):
            candidates.append("audit_record")
        if any(word in text for word in ["审批", "处理", "分配"]):
            candidates.append("workflow_action")
        return candidates

    def _extract_constraints(self, text: str) -> list[str]:
        constraints: list[str] = []
        for word in ["失败重试", "权限", "审批", "边界", "workflow", "本地", "联网"]:
            if word in text and word not in constraints:
                constraints.append(word)
        return constraints

    def _extract_permissions(self, text: str) -> list[str]:
        permissions: list[str] = []
        if "权限" in text:
            permissions.append("explicit_permission_model")
        if "审批" in text:
            permissions.append("approval_flow")
        return permissions

    def _extract_failure_strategy(self, text: str) -> str | None:
        if "失败重试" in text or ("失败" in text and "重试" in text):
            return "retry_on_failure"
        if "回滚" in text:
            return "rollback_on_failure"
        return None

    def _compute_missing_fields(
        self,
        requirement_type: str,
        goal: str,
        inputs: list[str],
        outputs: list[str],
    ) -> list[str]:
        missing: list[str] = []
        if not goal:
            missing.append("goal")
        if requirement_type in {"app", "hybrid"} and not outputs:
            missing.append("outputs")
        if requirement_type == "skill" and not inputs:
            missing.append("inputs")
        if requirement_type == "unclear":
            missing.append("artifact_type")
        return missing

    def _build_questions(self, missing_fields: list[str], demo_decision: str) -> list[str]:
        questions: list[str] = []
        field_to_question = {
            "artifact_type": "你要的是一个 app、一个 skill，还是两者组合？",
            "goal": "这个能力最终想解决的核心目标是什么？",
            "inputs": "这个能力的输入来源是什么？",
            "outputs": "你期望它最终输出什么结果？",
        }
        for field in missing_fields:
            question = field_to_question.get(field)
            if question:
                questions.append(question)
        if demo_decision == "required":
            questions.append("这个流程是否方便先做一次演示，让系统抽取页面步骤和规则？")
        return questions

    def _determine_readiness(self, demo_decision: str, missing_fields: list[str], constraints: list[str]) -> str:
        if demo_decision == "required":
            return "needs_demo"
        if any(item in {"权限", "边界"} for item in constraints) and "outputs" in missing_fields:
            return "needs_clarification"
        if missing_fields:
            return "needs_clarification"
        return "ready"
