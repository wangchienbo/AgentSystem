"""单测：角色决策输出的结构化 panels 解析（输出信封设计第1阶段）

覆盖：
- _parse_decision 解析结构化 panels JSON → action["panels"] + 渲染文本到「面板」
- 旧「面板:文本」自由文本兼容（panels 为空）
- _render_panels 通用渲染
- _aggregate_panels 按 id 去重合并（narrative 持久化）
"""
from app.novel_studio.pipeline.character_action.step_character_action import (
    _parse_decision, _render_panels,
)
from app.novel_studio.pipeline.narrative.step_narrative import _aggregate_panels


# ── _parse_decision：结构化 panels ──
def test_parse_decision_extracts_structured_panels():
    llm_out = """感知：系统弹出面板
行动：查看面板
对话：沉默
内心：这面板是什么
{
  "action": "查看系统面板",
  "dialogue": "沉默",
  "inner": "看看这个面板",
  "perception": "面板浮现",
  "panels": [
    {
      "id": "system",
      "title": "万界抽卡系统",
      "sections": [
        {"id": "ov", "title": "当前状态",
         "fields": [{"key": "绑定宿主", "value": "陈默"},
                    {"key": "下次抽取", "value": "23:59:57"}]},
        {"id": "rec", "title": "抽卡记录",
         "list": [{"seq": 1, "talent": "根骨鉴定", "desc": "可查看目标资质"}]}
      ]
    }
  ]
}"""
    d = _parse_decision(llm_out, "陈默")
    assert d["character"] == "陈默"
    assert d["action"] == "查看系统面板"
    # 结构化 panels 被提取
    assert len(d["panels"]) == 1
    assert d["panels"][0]["id"] == "system"
    assert d["panels"][0]["sections"][0]["fields"][0] == {"key": "绑定宿主", "value": "陈默"}
    # 渲染文本填到「面板」（供叙事正文消费）
    assert "万界抽卡系统" in d["面板"]
    assert "绑定宿主：陈默" in d["面板"]
    assert "抽卡记录" in d["面板"]


# ── 旧「面板:文本」自由文本兼容 ──
def test_parse_decision_legacy_text_panel_compat():
    llm_out = """感知：周围安静
行动：观察
对话：沉默
内心：没异常
面板：当前状态良好"""
    d = _parse_decision(llm_out, "铁柱")
    assert d["面板"] == "当前状态良好"
    assert d["panels"] == []  # 无结构化 panels，保持空
    assert d["action"] == "观察"


# ── _render_panels：通用渲染 ──
def test_render_panels_generic():
    panels = [{
        "id": "s", "title": "状态",
        "sections": [
            {"title": "基础", "fields": [{"key": "身份", "value": "流落冀北"}]},
            {"title": "同行者", "list": [{"name": "铁柱", "role": "前边军"}]},
        ],
    }]
    text = _render_panels(panels)
    assert "【状态】" in text
    assert "身份：流落冀北" in text
    assert "name：铁柱" in text


# ── _aggregate_panels：按 id 去重合并 ──
def test_aggregate_panels_dedup_by_id():
    actions = [
        {"panels": [{"id": "system", "title": "A", "sections": []}]},
        {"panels": [{"id": "system", "title": "A2", "sections": [{"fields": []}]}]},  # 同 id 覆盖
        {"panels": [{"id": "status", "title": "B", "sections": []}]},
    ]
    merged = _aggregate_panels(actions)
    ids = [p["id"] for p in merged]
    assert ids == ["system", "status"]  # 去重 + 保序
    sys_panel = next(p for p in merged if p["id"] == "system")
    assert sys_panel["title"] == "A2"  # 后出现覆盖


def test_aggregate_panels_ignores_non_dict():
    actions = [{"panels": ["not-a-dict", {"id": "x", "title": "X", "sections": []}]}]
    assert len(_aggregate_panels(actions)) == 1
