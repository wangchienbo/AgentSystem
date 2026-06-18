"""Step: Editorial Review — 章节质量审核与修正（读者视角版）

在叙事合成之后执行，模拟读者阅读体验进行质量评估：

评估维度（读者视角）：
1. 阅读流畅度 — 节奏自然？句子通顺？读起来卡不卡？
2. 代入感 — 视角一致？能代入主角处境？
3. 剧情推进 — 这章读完有"事情变了"的感觉吗？
4. 角色真实 — 角色的言行/情绪像正常人吗？
5. 对话质量 — 对话自然？还是信息播报？
6. 章节结构 — 开头抓人？中间起伏？结尾悬念？
|7. 红线/出戏 — 有现代词汇、上帝视角、看穿剧情？
|8. 设定一致性 — 文中细节是否与小说专属设定自洽？倒计时、天赋、角色知识边界等不能违反规则

评分不合格时 -> 触发叙事层重生成，附带详细审核反馈
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..base import BaseModule, PipelineContext
from ..prompt_loader import load_prompt

logger = logging.getLogger(__name__)

# ─── 快速规则检查（无需LLM） ────────────────────────────────

BANNED_TERMS = {
    # 技术词汇
    "黑盒", "测试", "接口", "只读", "阈值", "频率", "触发词",
    "能耗", "探测", "接驳", "协议", "线程", "缓存", "带宽",
    "数据", "算法", "逻辑", "编程", "代码", "程序", "函数",
    "变量", "参数", "量化", "数值", "脱敏", "校验",
    "检测到", "测出", "测评",
    # 系统类词汇（在叙事正文中不应出现）
    "后台静默", "神经接口", "识海脉冲", "视觉皮层",
    # 现代职场/黑话
    "滚雪球", "闭环", "赋能", "颗粒度",
}

# 评估维度名称（用于评分输出）
DIMENSIONS = [
    "阅读流畅度",
    "代入感",
    "剧情推进",
    "角色真实",
    "对话质量",
    "章节结构",
    "红线/出戏",
    "设定一致性",
]

# 重生成阈值
PASS_THRESHOLD = 6.5       # 整体评分 >= 6.5 才通过
MIN_PLOT_SCORE = 3         # 剧情推进 >= 3
MIN_REDLINE_SCORE = 3      # 红线/出戏 >= 3
MIN_STRUCTURE_SCORE = 3    # 章节结构 >= 3（检测节奏跳脱）
MIN_CONSISTENCY_SCORE = 3  # 设定一致性 >= 3（检测设定违反）
MIN_DIALOGUE_SCORE = 3     # 对话质量 >= 3（检测无对话）
MIN_DIALOGUE_COUNT = 2     # 每章至少2段真人对话（代码级硬检查）
MAX_REGENERATIONS = 2      # 最多重生成2次


# ─── 审核提示词模板 ────────────────────────────────────────

REVIEW_SYSTEM_PROMPT = load_prompt("editorial_review", "review_criteria.md")
class EditorialReviewModule(BaseModule):
    """⑦ 章节质量审核：读者视角评估 + 低分触发重生成"""

    @property
    def name(self) -> str:
        return "editorial_review"

    @property
    def description(self) -> str:
        return "📝 章节质量审核与修正"

    @property
    def modifies_storage(self) -> bool:
        return True  # 可能修正章节内容

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        narrative_out = ctx.get_output("narrative", {})
        content = narrative_out.get("content", "")

        if not content:
            logger.warning("审核跳过：叙事输出为空")
            return ctx

        chapter_number = narrative_out.get("chapter_number", 0)
        title = narrative_out.get("title", "")
        logger.info("开始审核第%d章「%s」（%d字）", chapter_number, title, len(content))

        # ─── 第1步：快速规则检查（红线词 + 段落 + 对话基础） ───
        rule_issues = self._rule_based_check(content, chapter_number)

        # ─── 第2步：LLM 读者视角评估 ──────────────────────────
        evaluation = await self._llm_evaluate_chapter(ctx, content, chapter_number, title)

        # 合并规则检查结果到评估中
        if rule_issues:
            evaluation.setdefault("rule_issues", rule_issues)
            if "suggestions" not in evaluation:
                evaluation["suggestions"] = []
            for iss in rule_issues:
                evaluation["suggestions"].append(f"[规则] {iss['type']}: {iss['detail']}")

        # ─── 第3步：判断是否通过 ──────────────────────────────
        is_pass = self._evaluate_pass(evaluation, ctx.regeneration_count)

        # 整理输出
        result = {
            "word_count": len(content),
            "evaluation": evaluation,
            "is_pass": is_pass,
            "needs_regeneration": not is_pass,
        }

        if is_pass:
            logger.info(
                "✅ 第%d章审核通过: overall=%.1f, 维度=%s",
                chapter_number,
                evaluation.get("overall", 0),
                {k: v for k, v in evaluation.get("scores", {}).items() if v is not None},
            )
        else:
            logger.warning(
                "❌ 第%d章审核未通过: overall=%.1f, 维度=%s",
                chapter_number,
                evaluation.get("overall", 0),
                evaluation.get("scores", {}),
            )
            # 构造重生成反馈并触发回退
            ctx.regeneration_feedback = self._format_feedback(evaluation, rule_issues)
            ctx.needs_regeneration = True
            logger.info("🔄 已设置重生成反馈（第%d次）", ctx.regeneration_count + 1)

        # 如果通过且有规则问题，做轻量修正
        if is_pass and rule_issues:
            content = self._apply_quick_fixes(content, rule_issues)
            self._update_chapter(ctx, chapter_number, content)
            logger.info("章节 %d 已修正（规则修复）", chapter_number)
        elif is_pass:
            # 没发现问题——仍然需要标记为已审
            logger.info("章节 %d 审核通过，无需修改", chapter_number)

        ctx.set_output(self.name, result)
        return ctx

    # ─── 规则检查 ────────────────────────────────────────────

    def _rule_based_check(self, content: str, chapter_number: int = 1) -> list[dict]:
        issues = []

        # 0. 分离穿越前/后段落（第一章穿越前是现代场景，不应拦截现代词汇）
        # 穿越标记：再睁眼/醒来/失去意识/睁开眼 等
        prologue_end = 0
        for marker in ["再睁眼", "猛地睁开眼", "睁开眼", "醒来", "失去意识", "断了线"]:
            idx = content.find(marker)
            if 0 < idx < 600:
                prologue_end = idx
                break
        post_prologue = content[prologue_end:] if prologue_end else content

        # 0.5. 第一章穿越前导语存在性检查（严格版）
        if chapter_number == 1:
            # 检测穿越前导语：标记词前必须有现代场景特征
            has_prologue = False
            if prologue_end > 80:  # 标记词前至少有80字
                before_marker = content[:prologue_end]
                modern_markers = ["机房", "触电", "排插", "铜线", "电流", "加班", "凌晨",
                                  "运维", "键盘", "指示灯", "电脑", "手机", "公司",
                                  "办公室", "地铁", "出租屋", "公寓", "现代", "地球"]
                found_modern = [m for m in modern_markers if m in before_marker]
                if found_modern:
                    has_prologue = True
            if not has_prologue:
                issues.append({
                    "type": "缺少穿越前导语",
                    "severity": "critical",
                    "detail": "第一章缺少穿越前场景（机房/触电/穿越前导语）。"
                              "必须以现代场景开头（200-400字），再过渡到穿越后。"
                              "当前内容直接从异世界开始，缺少穿越触发事件。",
                })

        # 1. 红线词检测（仅检查穿越后部分）
        found_terms = []
        for term in BANNED_TERMS:
            pattern = re.compile(re.escape(term))
            matches = pattern.findall(post_prologue)
            if matches:
                found_terms.append(term)

        if found_terms:
            context_lines = []
            for term in found_terms:
                for m in re.finditer(re.escape(term), content):
                    start = max(0, m.start() - 20)
                    end = min(len(content), m.end() + 20)
                    ctx_str = content[start:end].replace("\n", " ")
                    context_lines.append(f"  「{term}」出现在: ...{ctx_str}...")
            issues.append({
                "type": "红线词",
                "severity": "high",
                "detail": f"发现 {len(found_terms)} 个红线词",
                "items": list(found_terms),
                "contexts": context_lines,
            })

        # 2. 段落长度检查
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        long_paras = []
        for i, para in enumerate(paragraphs):
            if len(para) > 300:
                long_paras.append({
                    "index": i,
                    "length": len(para),
                    "preview": para[:80] + "...",
                })
        if long_paras:
            issues.append({
                "type": "段落超长",
                "severity": "medium",
                "detail": f"发现 {len(long_paras)} 个超长段落（>300字）",
                "items": long_paras,
            })

        # 3. 抽卡事件检查（时间感知，非强制每章）
        draw_panels = re.findall(r'【第\d+次抽卡[｜|]完成】', content)
        talent_mentions = re.findall(r'【新增天赋[｜|](.+?)】', content)
        # 不强制每章必须有抽卡——由系统根据时间流逝判断
        # 但如果有新天赋，必须有抽卡面板

        # 4. 禁止倒计时数字（事件驱动模式不应有具体倒计时）
        countdown_matches = re.findall(r'下次抽取[｜|]\s*\d{2}:\d{2}:\d{2}', content)
        if countdown_matches:
            issues.append({
                "type": "不应显示倒计时",
                "severity": "medium",
                "detail": f"文中出现了具体倒计时数字（{countdown_matches[0]}）。"
                          f"事件驱动模式下，面板不显示具体倒计时。",
            })

        # 5. 天赋来源检查
        if talent_mentions and not draw_panels:
            issues.append({
                "type": "天赋无抽卡展示",
                "severity": "critical",
                "detail": f"文中出现了新增天赋（{', '.join(talent_mentions)}），但没有对应的抽卡面板展示。"
                          f"每个新天赋必须通过抽卡面板展示给读者。",
            })

        # 6. 对话数量硬检查（代码级，不依赖LLM）
        # 兼容「」中文引号 和 "" 英文引号
        cn_dialogue = len(re.findall(r'「[^」]+」', content))
        en_dialogue = len(re.findall(r'"([^"]{4,})"', content))
        # 说/道/问/喊 等引导的对话（无引号时）
        bare_dialogue = len(re.findall(r'[说道问喊叫吼骂嚷][：:]\s*["\u201c]?([^"\u201d\n]{4,})["\u201d]?', content))
        dialogue_count = cn_dialogue + en_dialogue
        if dialogue_count < MIN_DIALOGUE_COUNT:
            issues.append({
                "type": "对话不足",
                "severity": "critical",
                "detail": f"本章只有 {dialogue_count} 段真人对话（「」={cn_dialogue}, \"\"={en_dialogue}），要求至少 {MIN_DIALOGUE_COUNT} 段。"
                          f"每章必须有角色之间的真实对话，不能全程独白或旁白。",
            })
        # 检查是否有天赋名称出现在文中但没有【新增天赋】标记
        known_talents = set()
        for m in re.finditer(r'【(?:新增|当前)天赋[｜|](.+?)】', content):
            for t in m.group(1).split('、'):
                known_talents.add(t.strip())
        # 检查是否有天赋被使用但不在已知列表中（粗略检测：中文书名号内的天赋名）
        talent_usage = re.findall(r'【(.+?)】', content)
        for tu in talent_usage:
            if tu in known_talents:
                continue
            # 简单启发式：如果看起来像天赋名（2-4个汉字，非系统关键词）
            if 2 <= len(tu) <= 4 and tu not in ['万界抽卡系统｜已绑定', '下次抽取']:
                # 可能是未展示的天赋
                pass  # 太容易误报，交给 LLM 判断

        return issues

    # ─── LLM 读者视角评估 ────────────────────────────────────

    async def _llm_evaluate_chapter(
        self,
        ctx: PipelineContext,
        content: str,
        chapter_number: int,
        chapter_title: str,
    ) -> dict:
        """用LLM模拟读者视角评估章节质量"""
        client = ctx.get_llm_client("novel_writer")
        if not client:
            logger.warning("LLM客户端不可用，使用默认通过")
            return self._default_pass_eval()

        # 获取章节规划（大纲对比用）
        plan = ctx.get_output("chapter_plan", {})
        plan_title = plan.get("title", chapter_title)
        plan_summary = plan.get("summary", "无详细大纲")

        # 获取上一章内容（用于连续性评估）
        novel = ctx.novel
        prev_chapter_content = ""
        if novel and hasattr(novel, "chapters") and novel.chapters:
            prev = novel.chapters[-1] if len(novel.chapters) >= 1 else None
            if prev and prev.number != chapter_number:
                prev_chapter_content = (prev.content or "")[-500:]

        lines = [
            "## 当前章节信息",
            f"第{chapter_number}章：{chapter_title}",
            f"大纲规划：{plan_summary}",
            "",
        ]
        if prev_chapter_content:
            lines.append("## 上一章结尾（连续性参考）")
            lines.append(prev_chapter_content[:400])
            lines.append("")

        # 注入小说专属设定（供设定一致性检查）
        custom_prompt = getattr(novel, "custom_prompt", "") or ""
        if custom_prompt:
            lines.append("## 小说专属设定/写作指令")
            lines.append(custom_prompt)
            lines.append("")

        # 注入场景人群数据（供人群一致性检查）
        loop_data = ctx.get_output("scene_loop", {})
        scenes_data = loop_data.get("scenes") or ctx.get_output("scene_build", {}).get("scenes", [])
        if scenes_data:
            lines.append("## 本章场景人群信息（用于检查叙事中人群是否蒸发）")
            for s in scenes_data:
                crowd = s.get("crowd", "")
                if crowd:
                    lines.append(f"- 场景「{s.get('name', '?')}」：{crowd}")
            lines.append("")

        # 截取关键片段（保留开头和结尾，中间全文给LLM）
        head = content[:500]
        tail = content[-300:] if len(content) > 500 else ""

        lines.append("## 本章全文")
        lines.append(content)
        lines.append("")

        lines.append("## 评估要求")
        lines.append("请从以下维度评估章节质量（0-5分，整数）：")
        for d in DIMENSIONS:
            lines.append(f"- {d}")
        lines.append("")
        lines.append("并给出：")
        lines.append("- overall: 整体满意度 0-10（小数）")
        lines.append("- strengths: 2-3个优点")
        lines.append("- weaknesses: 2-3个缺点")
        lines.append("- suggestions: 2-3条具体修改建议")
        lines.append("- is_pass: 你作为读者是否愿意继续读下去")
        lines.append("")
        lines.append("## 评分标准参考")
        lines.append("【阅读流畅度】")
        lines.append("  5=读起来行云流水，节奏舒服")
        lines.append("  3=基本通顺，偶尔卡顿")
        lines.append("  1=大量病句，读不下去")
        lines.append("")
        lines.append("【代入感】")
        lines.append("  5=完全代入主角，忘了在读小说")
        lines.append("  3=偶尔出戏，但还能继续")
        lines.append("  1=视角混乱，完全出戏")
        lines.append("")
        lines.append("【剧情推进】")
        lines.append("  5=这章读完有重大进展/冲突/转折")
        lines.append("  3=有一些推进但不够劲")
        lines.append("  1=从头到尾没变化，原地打转")
        lines.append("")
        lines.append("【角色真实】")
        lines.append("  5=角色的反应像真实的人，情绪饱满")
        lines.append("  3=基本合理，但缺少情绪波动")
        lines.append("  1=角色像机器人/工具人")
        lines.append("")
        lines.append("【对话质量】")
        lines.append("  5=对话自然，推动剧情，塑造人物")
        lines.append("  3=有对话但不自然")
        lines.append("  1=没有对话或只有系统播报")
        lines.append("")
        lines.append("【章节结构】")
        lines.append("  5=开头钩子+中间起伏+结尾悬念，完美")
        lines.append("  3=有头有尾但平平无奇")
        lines.append("  1=没有开头/结尾，像截断的")
        lines.append("")
        lines.append("【红线/出戏】")
        lines.append("  5=完美，没有任何出戏内容")
        lines.append("  3=少量现代词汇或上帝视角，但不致命")
        lines.append("  1=大量红线词/元叙事/角色看穿剧情")
        lines.append("")
        lines.append("【设定一致性】")
        lines.append("  5=所有细节与小说设定完全自洽，倒计时/天赋/规则无一矛盾")
        lines.append("  3=大部分一致，但有一两处细节与设定小冲突（如倒计时不合理）")
        lines.append("  1=多处严重冲突，明显违反小说专属规则")
        lines.append("")
        lines.append("只输出JSON，不要任何其他内容。")

        user_prompt = "\n".join(lines)

        system_prompt = REVIEW_SYSTEM_PROMPT

        try:
            text, _ = client.chat(
                [{"role": "system", "content": system_prompt},
                 {"role": "user", "content": user_prompt}],
                max_tokens=4000,
                temperature=0.3,
            )
            text = (text or "").strip()

            # 提取 JSON
            result = self._extract_json(text)
            if result and "scores" in result and "overall" in result:
                return result

            logger.warning("LLM评估返回格式异常，使用默认通过")
            return self._default_pass_eval()

        except Exception as e:
            logger.warning("LLM评估失败: %s，使用默认通过", e)
            return self._default_pass_eval()

    def _extract_json(self, text: str) -> dict | None:
        """从LLM回复中提取JSON"""
        import json

        # 尝试直接解析
        text = text.strip()
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # 尝试从代码块中提取
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试找到第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _default_pass_eval(self) -> dict:
        """默认：通过（当LLM不可用时）"""
        return {
            "scores": {d: 4 for d in DIMENSIONS},
            "overall": 7.0,
            "strengths": ["（LLM评估不可用，默认通过）"],
            "weaknesses": [],
            "suggestions": [],
            "is_pass": True,
        }

    # ─── 通过判定 ────────────────────────────────────────────

    def _evaluate_pass(self, evaluation: dict, current_regeneration_count: int) -> bool:
        """根据评估结果判定是否通过"""
        # 如果已经重生了2次，无论如何都要过
        if current_regeneration_count >= MAX_REGENERATIONS:
            logger.info("已达最大重生成次数(%d)，强制通过", MAX_REGENERATIONS)
            return True

        # 检查 critical 级别的规则问题（如缺少穿越前导语）
        rule_issues = evaluation.get("rule_issues", [])
        for iss in rule_issues:
            if iss.get("severity") == "critical":
                logger.warning("❌ 发现严重规则问题: %s", iss.get("type"))
                return False

        overall = evaluation.get("overall", 7.0)
        scores = evaluation.get("scores", {})

        if overall < PASS_THRESHOLD:
            return False

        plot_score = scores.get("剧情推进", 5)
        if plot_score < MIN_PLOT_SCORE:
            return False

        redline_score = scores.get("红线/出戏", 5)
        if redline_score < MIN_REDLINE_SCORE:
            return False

        structure_score = scores.get("章节结构", 5)
        if structure_score < MIN_STRUCTURE_SCORE:
            return False

        consistency_score = scores.get("设定一致性", 5)
        if consistency_score < MIN_CONSISTENCY_SCORE:
            return False

        dialogue_score = scores.get("对话质量", 5)
        if dialogue_score < MIN_DIALOGUE_SCORE:
            return False

        return True

    # ─── 反馈格式化 ──────────────────────────────────────────

    def _format_feedback(self, evaluation: dict, rule_issues: list[dict]) -> str:
        """将评估结果格式化为叙事层可读的重生成反馈"""
        lines = []
        scores = evaluation.get("scores", {})
        overall = evaluation.get("overall", 0)

        lines.append(f"【整体评分】{overall}/10")
        lines.append("")

        lines.append("【维度评分】")
        for d in DIMENSIONS:
            s = scores.get(d, 0)
            mark = "⚠️" if (d == "剧情推进" and s < MIN_PLOT_SCORE) or \
                          (d == "红线/出戏" and s < MIN_REDLINE_SCORE) or \
                          (d == "章节结构" and s < MIN_STRUCTURE_SCORE) or \
                          (d == "设定一致性" and s < MIN_CONSISTENCY_SCORE) or \
                          (isinstance(s, (int, float)) and s < 3) else ""
            lines.append(f"  {d}: {s}/5 {mark}")

        if evaluation.get("weaknesses"):
            lines.append("")
            lines.append("【主要问题】")
            for w in evaluation["weaknesses"][:3]:
                lines.append(f"  ❌ {w}")

        if evaluation.get("suggestions"):
            lines.append("")
            lines.append("【修改建议】")
            for s in evaluation["suggestions"][:4]:
                lines.append(f"  → {s}")

        if rule_issues:
            lines.append("")
            lines.append("【规则检查问题】")
            for iss in rule_issues:
                lines.append(f"  ⚠️ {iss['type']}: {iss['detail']}")

        lines.append("")
        lines.append("⚠️ 本章未能通过质量审核，请根据以上反馈重新生成。务必针对性修正上述问题。")

        return "\n".join(lines)

    # ─── 轻量修正 ────────────────────────────────────────────

    def _apply_quick_fixes(self, content: str, issues: list[dict]) -> str:
        """对有规则问题的内容做轻量修正（不调用LLM）"""
        # 分离穿越前/后（穿越前是现代场景，不应修改）
        prologue_end = 0
        for marker in ["再睁眼", "猛地睁开眼", "睁开眼", "醒来", "失去意识", "断了线"]:
            idx = content.find(marker)
            if 0 < idx < 600:
                prologue_end = idx
                break
        
        prologue = content[:prologue_end] if prologue_end else ""
        post = content[prologue_end:] if prologue_end else content
        
        for iss in issues:
            if iss["type"] == "红线词":
                for term in iss.get("items", []):
                    post = post.replace(term, f"[{term}]")
        
        return prologue + post

    # ─── 章节更新 ────────────────────────────────────────────

    def _update_chapter(self, ctx: PipelineContext, chapter_number: int, content: str):
        novel = ctx.novel
        if not novel or not hasattr(novel, "chapters"):
            return

        chapters = novel.chapters or []
        for ch in chapters:
            if getattr(ch, "number", 0) == chapter_number:
                ch.content = content
                break

        ctx.save_novel()
