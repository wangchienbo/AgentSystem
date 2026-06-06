# Novel Studio 下一代架构设计

> 综合讨论整理 | 2026-06-05
> 核心转变：从「脚本驱动」到「预测-行动-重预测」闭环

---

## 一、整体架构转变

```
当前架构（脚本驱动）              新架构（预测驱动）
═══════════════════              ═══════════════════
大纲（固定）                      动态大纲（预测模型）
      ↓                               ↑ ↓
角色按大纲演 ← 大纲泄露             角色自由决策 ← 大纲阻断
      ↓                               ↓
写完章节结束                      重预测 → 闭环
```

### 核心原则

| 原则 | 说明 |
|------|------|
| **大纲 = 预测，不是剧本** | 大纲是对后续走向的预测，角色不按大纲演，大纲反过来跟角色走 |
| **角色完全隔离** | 角色决策时不知道大纲存在，只凭人格、记忆、场景感知做决定 |
| **反馈闭环** | 角色行为 → 改变世界状态 → 更新预测 → 影响下一轮场景 |
| **温和引导** | 在更新预测时给方向提示，不强制角色行为 |
| **属性即约束** | 属性从数字翻译为行为描述，模型据此扮演 |

---

## 二、Pipeline：预测-行动-重预测闭环

```
┌────────────────────────────────────────────────────────────┐
│                   第 N 章生成循环                           │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ① 生成/更新大纲 ←─── 缓存的角色能力描述                   │
│     └ 输入：世界状态 + 角色状态 + 已发生事件 + 用户方向提示  │
│     └ 输出：预测（主题、场景序列、关键事件、参与角色）        │
│                                                            │
│  ② 场景序列（基于大纲预测，但大纲不是强约束）                 │
│                                                            │
│  ③ 场景细化（感官细节、角色分配）                            │
│                                                            │
│  ───── 🚫 大纲信息在此阻断 ─────                            │
│                                                            │
│  ④ 角色行为决策 ⭐（核心改动见第三、四节）                   │
│     └ 角色只知道：记忆 + 场景感知 + 其他人言行 + 自身能力    │
│     └ 不知道"剧情需要"自己做什么                             │
│                                                            │
│  ⑤ 更新大纲 ←─── 新增步骤 ⭐                               │
│     └ 对比：角色实际做了什么 vs 预测                         │
│     └ 修正：后续章节走向预测                                │
│     └ 引导：可接受用户方向提示（温和，不强制）                │
│                                                            │
│  ⑥ 叙事合成（用最新大纲做叙事上下文，不覆盖实际事件）          │
│                                                            │
│  ⑦ 记忆更新（角色记忆本次事件）                              │
│                                                            │
│  ─── 第⑤步更新的大纲 → 作为下一轮第①步输入 ───             │
│                 形成闭环                                    │
└────────────────────────────────────────────────────────────┘
```

### 模板定义（更新后）

```python
PIPELINE_TEMPLATES = {
    "write_next_chapter": [
        "chapter_plan",       # ① 生成/更新大纲预测
        "scene_sequence",     # ② 场景序列
        "scene_build",        # ③ 场景细化
        "character_action",   # ④ 角色行为决策（不传大纲）
        "outline_update",     # ⑤ 更新大纲 ⭐ 新增
        "narrative",          # ⑥ 叙事合成
        "memory_update",      # ⑦ 记忆更新
    ],
}
```

---

## 三、角色属性翻译体系 ⭐

### 3.1 现状

角色已有六维属性（Attributes）和特殊能力（special_ability）字段，但决策提示词中只以数字显示，**模型不理解其含义**：

```python
# 当前
"属性：智力16 | 感知10 | 魅力18"
# → 模型看到"16"不知道这意味着什么
```

### 3.2 设计：两层翻译

```
缓存层（compute once, cache forever）
═══════════════════════════════════════
原始数据                            翻译结果（自然语言行为描述）
─────────                          ──────────────────────────
智力: 16                           "你心思缜密，能从对方只言片语
                                   推断出没说出口的三层含义。
                                   你能预测几步之后的局势走向。"

感知: 8                            "你大咧咧的，经常注意不到
                                   别人的微表情和暗示。"

特殊能力: 天眼                      "你拥有天眼能力。你可以
                                   闭眼凝神，在意念中远程观察
                                   任意地点正在发生的事。"

特殊能力: 时间穿梭                  "你可以感知到时间线的分支。
                                   你知道某些事件"本应"如何发展，
                                   也看到它们实际如何偏离。"

运行层（each decision, runtime）
═══════════════════════════════════════
系统做的事：
  根据能力扩展角色能感知到的上下文范围
  例如：天眼 → 上下文包含远处场景的信息
  
模型做的事：
  基于"能力描述 + 已扩展的上下文"
  自行判断是否在叙事中使用能力
  通过叙事文本"演出来"

  例如看到天眼提供的远处场景信息后 →
  模型写："沈逸之闭上眼，意念扫过全营，
           看到曹三喜在后帐召集亲信..."
```

### 3.3 属性→行为翻译规则

| 属性 | 值范围 | 行为翻译 |
|------|--------|---------|
| 智力 | 6-8 | 头脑简单，想不了太复杂的事，容易被人忽悠 |
| 智力 | 9-11 | 普通人水平，能理解日常事务 |
| 智力 | 12-15 | 聪明，能举一反三，看问题比常人深一层 |
| 智力 | 16-18 | 极聪明，能从碎片信息拼出全貌，能预测局势 |
| 智力 | 19+ | 天才，几乎是先知级别的洞察力 |
| 感知 | 6-8 | 迟钝，容易忽视细节和暗示 |
| 感知 | 9-11 | 正常水平 |
| 感知 | 12-15 | 敏锐，能注意到常人忽略的细节 |
| 感知 | 16+ | 洞察人心，能看穿谎言和伪装 |
| 魅力 | 6-8 | 不善言辞，说服力弱 |
| 魅力 | 9-11 | 普通人 |
| 魅力 | 12-15 | 有说服力，容易获得他人好感 |
| 魅力 | 16+ | 天生的领袖，一句话能让人追随 |
| 力量 | 6-8 | 体弱，不能干重活、打硬仗 |
| 力量 | 16+ | 强壮，在肉搏中占优势 |
| 体质 | 6-8 | 体弱多病，耐力差 |
| 体质 | 16+ | 铁打的身子，耐扛耐熬 |
| 敏捷 | 6-8 | 笨拙，精细操作困难 |
| 敏捷 | 16+ | 手巧，能完成精密工艺 |

### 3.4 能力→上下文扩展规则

| 能力类型 | 上下文扩展 |
|----------|-----------|
| 普通（无特殊能力） | 只知道自己场景里的信息 |
| 高智力（16+） | 额外获得一层"推理层"：基于当前信息可以推断出的隐藏信息 |
| 天眼/千里眼 | 获得指定远处场景的信息（最多1个额外场景） |
| 超忆症 | 获得与当前场景相关的完整历史回顾 |
| 时间穿梭/预知 | 获得"未来/替代时间线"的线索 |
| 读心 | 获得遇见的每个角色的表层想法 |
| 敏锐感官（高感知16+） | 场景描述更丰富（多出细节、氛围变化、微表情） |

---

## 四、角色决策 Prompt 结构（更新后）

### 4.1 System Prompt

```python
system_prompt = f"""
你正在扮演{char_name}。你的所有行动必须严格遵循角色设定。

【核心规则】
1. 你只知道你自己能感知到的信息。你不知道"剧情"。
2. 你的行为由你的性格、记忆、能力和当前处境驱动。
3. 你可以使用你的能力——它们是你与生俱来的特质。
   在叙事中自然地展现能力的使用过程。
4. 如果你收到了超出普通感知的信息（如天眼看到的、推理得出的），
   这是因为你的能力使然。在决策中合理利用这些信息。
5. 始终保持角色性格一致。
"""
```

### 4.2 User Prompt（决策上下文）

```python
def _build_decision_prompt(agent, perception, scene_context, previous_actions):
    parts = []

    # 1. 角色身份
    parts.append(f"你扮演：{char_name}")
    parts.append(f"性格：{'、'.join(char.personality)}")
    parts.append(f"背景：{char.background[:200]}")

    # 2. ⭐ 属性翻译（缓存层）
    parts.append("\n【你的能力】")
    parts.append(build_ability_prompt(char))
    # → "属性翻译"的缓存结果
    # → 如："你心思缜密...你拥有天眼能力..."

    # 3. ⭐ 能力扩展的上下文（运行层）
    ability_context = build_ability_context(char, perception, novel)
    if ability_context:
        parts.append(f"\n【能力感知到的额外信息】")
        parts.append(ability_context)
    # → 如：天眼看到远处场景 | 高智力推理出的隐藏信息

    # 4. 场景感知
    parts.append(f"\n当前场景：{scene_context}")
    parts.append(f"你看到：{perception.visible_chars}")
    parts.append(f"你听到：{perception.sounds}")
    parts.append(f"氛围：{perception.mood}")

    # 5. 之前发生的事
    if previous_actions:
        parts.append("\n【你刚刚目睹的事】")
        for a in previous_actions:
            parts.append(f"  {a['character']}{a['action']}")

    return "\n\n".join(parts)
```

### 4.3 能力 Prompt 生成（缓存函数）

```python
# 缓存字典：{char_id: cached_prompt}
_ability_prompt_cache: dict[str, str] = {}

def build_ability_prompt(char) -> str:
    """将角色的属性和能力翻译为自然语言行为描述（缓存层）"""
    char_id = char.id
    if char_id in _ability_prompt_cache:
        return _ability_prompt_cache[char_id]

    lines = []

    # 六维属性翻译
    attr = char.attributes
    translations = {
        ("智力", attr.intelligence): {
            range(6, 9): "你头脑简单，想不太复杂的事。",
            range(9, 12): "你智力普通，能理解日常事务。",
            range(12, 16): "你挺聪明，能举一反三。",
            range(16, 19): "你心思极深。别人说一句话，你能听出三层意思。看到局势，你能预测几步后的走向。",
            range(19, 30): "你的智力近乎妖孽。你能从最细微的线索拼出全局。你几乎能预见未来。",
        },
        ("感知", attr.wisdom): {
            range(6, 9): "你大咧咧的，经常注意不到别人的微表情和暗示。",
            range(9, 12): "你的感知力正常。",
            range(12, 16): "你观察力敏锐，常人忽略的细节你一眼就能注意到。",
            range(16, 19): "你洞察人心。别人一开口你就知道他在打什么主意。",
            range(19, 30): "你几乎能看透因果。在你的感知中，世界由无数细节线索编织而成。",
        },
        ("魅力", attr.charisma): {
            range(6, 9): "你不善言辞，说话直来直去容易得罪人。",
            range(9, 12): "你社交能力普通。",
            range(12, 16): "你说话有分量，容易获得别人的好感和信任。",
            range(16, 19): "你天生有领袖气质。你一开口，别人就想听下去。",
            range(19, 30): "你的魅力近乎魔力。你能让最敌对的人放下戒心。",
        },
        ("力量", attr.strength): {
            range(6, 9): "你体弱，干不了重活，打架也吃亏。",
            range(9, 12): "你体力普通。",
            range(12, 16): "你有一把子力气，干体力活不成问题。",
            range(16, 19): "你很强壮，在肉搏中明显占优势。",
            range(19, 30): "你力能扛鼎，是万夫不当之勇。",
        },
        ("体质", attr.constitution): {
            range(6, 9): "你体弱多病，耐力差。",
            range(9, 12): "体质普通。",
            range(12, 16): "你身体结实，能扛能熬。",
            range(16, 19): "你铁打的身子骨，几天几夜不睡都扛得住。",
            range(19, 30): "你的体质近乎非人，百毒不侵。",
        },
        ("敏捷", attr.dexterity): {
            range(6, 9): "你手脚笨拙，精细操作做不来。",
            range(9, 12): "灵活度普通。",
            range(12, 16): "你手巧，能完成需要精细控制的工作。",
            range(16, 19): "你身轻如燕，动作快如闪电。",
            range(19, 30): "你的敏捷近乎超自然，能在针尖上绣花。",
        },
    }

    for i, (stat_name, stat_val) in enumerate(translations):
        found = False
        for r, desc in stat_val.items():
            if stat_val in r:
                lines.append(desc)
                found = True
                break
        if not found:
            lines.append(f"你的{stat_name}处于常人水平。")

    # 特殊能力翻译
    if char.special_ability:
        ability_desc = TRANSLATE_ABILITY(char.special_ability)
        lines.append(f"\n【特殊能力】{ability_desc}")

    result = "\n".join(lines)
    _ability_prompt_cache[char_id] = result
    return result
```

### 4.4 能力→上下文扩展（运行层函数）

```python
def build_ability_context(char, perception, novel) -> str:
    """根据角色的能力扩展感知上下文（运行层）"""
    extra = []
    attr = char.attributes

    # 高智力：推理层
    if attr.intelligence >= 16:
        extra.append("【你的推理】基于你观察到的情况，你推断出了一些深层信息...")
        extra.append(_generate_inference(char, perception, novel))

    # 天眼类能力
    if "天眼" in (char.special_ability or ""):
        extra.append(f"【天眼所见】你将意念投向远方，看到...")
        extra.append(_get_remote_scene_context(char, novel))

    # 敏锐感知
    if attr.wisdom >= 16:
        extra.append(f"【你注意到的细节】{_get_extra_details(perception)}")

    # 时间感知
    if any(w in (char.special_ability or "") for w in ["时间", "预知", "穿梭"]):
        extra.append("【时间感知】你的意识触及时间线，你感觉到一些\"本该\"发生的事...")

    return "\n\n".join(extra) if extra else ""
```

---

## 五、动态大纲更新模块 ⭐（新增）

### 5.1 新 Pipeline 模块

```python
class OutlineUpdateModule(BaseModule):
    """⑤ 更新大纲：对比实际 vs 预测，修正后续走向"""

    name = "outline_update"
    description = "🔄 更新大纲预测"
    modifies_storage = True

    async def execute(self, ctx) -> PipelineContext:
        # 输入：角色实际决策结果 + 旧大纲预测
        plan = ctx.get_output("chapter_plan")
        char_actions = ctx.get_output("character_action")

        # 对比：角色实际做了什么 vs 预测了什么
        prediction = plan.get("prediction", {})
        actual = extract_key_events(char_actions)

        divergence = analyze_divergence(prediction, actual)
        
        # 更新大纲预测
        new_prediction = await llm_update_prediction(
            novel=ctx.novel,
            old_prediction=prediction,
            actual_events=actual,
            divergence=divergence,
            user_hints=ctx.get("user_hints", ""),
        )

        # 写入 storage
        ctx.novel.outline.live_prediction = new_prediction

        return ctx
```

### 5.2 用户方向提示

在更新预测时，用户可以提供一个「方向提示」，例如：

```
"希望逐渐引入洪承畴这条线"
"让沈逸之在技术上有所突破，发明新的绘画材料"
"该给曹三喜搞点事情了"
```

这些提示**不会直接控制角色行为**，而是进入大纲预测层：

```
方向提示 → 更新大纲预测时参考 → 
  预测中可能出现含洪承畴的场景 →
  场景被生成 →
  角色进入场景 →
  角色自由决策（仍不知道大纲）
```

---

## 六、数据模型变化

### 6.1 Outline 新增字段

```python
class Outline(BaseModel):
    # 原有
    id: str
    title: str
    logline: str
    summary: str
    three_act: ThreeActStructure
    chapters: list[ChapterPlan]

    # 新增 ⭐
    live_prediction: str = ""      # 最新的动态预测（自然语言）
    prediction_history: list[dict] = []  # 历史预测记录，用于对比
    divergence_log: list[dict] = []     # 实际vs预测的偏差记录
```

### 6.2 Character 新增字段

```python
class Character(BaseModel):
    # 原有
    id: str
    name: str
    personality: list[str]
    background: str
    attributes: Attributes
    special_ability: str
    # ...

    # 新增 ⭐
    ability_prompt_cache: str = ""        # 缓存的能力翻译结果
    ability_contexts_used: list[str] = [] # 历史使用过的能力上下文
```

---

## 七、实现路线图

```
Phase 1: 属性翻译 + Prompt 改造（本迭代）
────────────────────────────────────────
  [1] 实现 build_ability_prompt() — 属性→行为描述翻译
  [2] 实现 build_ability_context() — 能力→上下文扩展
  [3] 修改 _build_decision_prompt() — 整合能力描述和扩展上下文
  [4] 修改 character_action system prompt — 加入能力使用引导
  [5] 添加 _ability_prompt_cache 缓存

Phase 2: 动态大纲（下一迭代）
────────────────────────────────────────
  [6] 实现 OutlineUpdateModule — 新 pipeline 模块
  [7] 修改 chapter_plan — 不再查静态大纲，用动态预测
  [8] 角色决策时阻断大纲信息
  [9] 添加用户方向提示接口

Phase 3: 完善与调整
────────────────────────────────────────
  [10] 跑通完整闭环，验证角色自主性
  [11] 添加 divergence 日志，可视化的"预测 vs 实际"
  [12] 调优属性翻译文案
```

---

## 八、关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 能力是否用真实 tool | ❌ 不用 | 模型直接通过叙事展现能力，更自然 |
| 大纲是否传给角色 | ❌ 不传 | 保证角色自主性，才有"自由演变" |
| 属性翻译能否缓存 | ✅ 能 | 每个角色固定，一次计算永久复用 |
| 方向提示是否强制 | ❌ 不强制 | 只影响预测层，不影响角色自由决策 |
| 更新大纲在哪个步骤 | 角色决策之后 | 先有行动，再有预测修正 |

---

## 九、与现有系统的关系

```
AgentSystem 基础设施
══════════════════════
  ModelRouter ───── LLM 调用
  ContextCenter ─── 角色记忆持久化
  ToolCallingEngine ─ 暂时不用（能力在 prompt 层实现）

Novel Studio 管道
══════════════════════
  6步 → 7步（新增 outline_update）
  角色决策 prompt 重写（属性翻译 + 能力上下文）
  outline 变动态（不再固定）
```

---

*本文档对应全部已讨论内容，后续代码实现以此为准。*
