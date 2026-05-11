"""50 User Scenarios × 20 Turns — User-Level E2E Test via HTTP API.

Tests the full AgentSystem stack end-to-end through the real HTTP API
(`/api/chat`), with actual LLM responses. Each turn includes a configurable
delay to avoid overwhelming vLLM, plus scenario-end conversation checks.

Usage:
    # Default: 3s delay between turns, target localhost:8765
    python -m tests.e2e.test_50_scenarios_20_turns_user_level

    # Custom delay and target
    python -m tests.e2e.test_50_scenarios_20_turns_user_level \
        --base-url http://localhost:8765 \
        --delay 5 \
        --scenarios S01,S02,S03

    # Only run specific scenario ranges
    python -m tests.e2e.test_50_scenarios_20_turns_user_level \
        --range 1-10

    # Skip delay (for local dev only)
    python -m tests.e2e.test_50_scenarios_20_turns_user_level --delay 0
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    import httpx
except ImportError:
    print("[ERROR] httpx not installed. Run: pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 50 Scenarios × 20 Turns (same scenarios as architecture-level test)
# ---------------------------------------------------------------------------

SCENARIOS = [
    {"id": "S01", "name": "首次体验-你好", "user_id": "user_new_01", "turns": [
        "你好", "你能做什么？", "帮我创建一个小说App吧", "这个小说App主要用来做什么？",
        "好，启动它", "帮我写一段科幻小说的开头", "太棒了，能帮我把这段保存吗？",
        "我想看看我有哪些App", "小说App现在是什么状态？", "能帮我优化一下小说App的功能吗？",
        "给我看看系统状态", "你有什么推荐的Skill吗？", "帮我安装一个写作相关的Skill",
        "现在能用这个Skill帮我写一段吗？", "我想停止小说App", "停止成功了吗？",
        "重新启动小说App", "现在能继续写了吗？", "帮我总结一下今天的对话", "谢谢，再见",
    ]},
    {"id": "S02", "name": "首次体验-你能做什么", "user_id": "user_new_02", "turns": [
        "在吗？", "你能帮我做什么事情？", "有哪些类型的App可以创建？", "我想做一个天气查询的App",
        "好的，帮我创建", "天气App创建好了吗？", "查询一下北京今天的天气", "那上海呢？",
        "这个App能自动提醒我吗？", "帮我设置一个每天早上8点的天气提醒", "看看我的App列表",
        "天气App能修改名字吗？", "改成叫每日天气助手", "确认一下改成功了没",
        "我想删除天气App", "真的删除了吗？确认一下", "那再帮我创建一个新的",
        "这次做一个待办事项App", "帮我在待办App里添加一个任务", "好的，今天就到这里",
    ]},
    {"id": "S03", "name": "首次体验-需求模糊", "user_id": "user_new_03", "turns": [
        "嗨", "我想做一个App，但不知道做什么好", "那你有什么建议？", "做一个日记App怎么样？",
        "帮我创建这个日记App", "日记App有什么功能？", "帮我写一篇今天的日记", "今天天气不错，心情也很好",
        "这篇日记能保存吗？", "我想看看之前写的日记", "能搜索特定关键词吗？", "帮我搜一下心情相关的日记",
        "日记App能导出数据吗？", "导出成什么格式？", "能导出成Markdown吗？", "好的，导出吧",
        "导出完成了吗？", "我想给日记App加个密码保护", "密码保护设置好了吗？", "谢谢，很好",
    ]},
    {"id": "S04", "name": "首次体验-直奔主题", "user_id": "user_new_04", "turns": [
        "帮我创建一个翻译App", "这个翻译App支持哪些语言？", "帮我翻译一段英文到中文", "Hello world, this is a test",
        "翻译得准确吗？", "我想翻译一段法文", "Bonjour le monde", "这个App能语音输入吗？",
        "能批量翻译吗？", "翻译质量怎么样？", "查看一下翻译App的状态", "能修改翻译App的默认语言吗？",
        "改成英文到日文", "帮我翻译一段日文看看", "こんにちは世界", "看起来不错",
        "翻译App能离线使用吗？", "我想停止翻译App", "确认停止了", "好的，下次见",
    ]},
    {"id": "S05", "name": "首次体验-探索型", "user_id": "user_new_05", "turns": [
        "你好呀", "这个系统是怎么工作的？", "听起来很厉害，帮我创建一个简单的App试试", "做一个计算器App吧",
        "计算器App能用了吗？", "帮我算一下 123 × 456", "再算一个 999 ÷ 7", "这个App能做科学计算吗？",
        "帮我算 sin(30度)", "精度怎么样？", "计算器App的历史记录在哪？", "能清除历史记录吗？",
        "我想查看系统信息", "系统用了多少资源？", "有哪些App在运行？", "计算器App的详情给我看看",
        "能给计算器App换个皮肤吗？", "有什么主题可选？", "换个深色的吧", "好的，谢谢",
    ]},
    {"id": "S06", "name": "App创建-完整流程", "user_id": "user_lifecycle_01", "turns": [
        "帮我创建一个任务管理App", "这个App需要什么配置？", "用默认配置就行", "创建完成了吗？",
        "查看任务管理App的详情", "启动它", "帮我在App里添加一个任务：完成Phase P测试",
        "再添加一个：审查代码", "查看任务列表", "标记完成Phase P测试为已完成",
        "查看更新后的列表", "修改任务管理App的名字为工作看板", "确认名字改过来了",
        "在工作看板里添加优先级标签", "把审查代码标记为高优先级", "查看所有高优先级任务",
        "删除已完成的任务", "查看剩余任务", "停止工作看板", "确认App已停止",
    ]},
    {"id": "S07", "name": "App修改-功能扩展", "user_id": "user_lifecycle_02", "turns": [
        "创建一个笔记App", "笔记App的基本功能有哪些？", "帮我写一篇笔记，标题是开发笔记",
        "内容是关于Phase P架构重构的", "保存这篇笔记", "查看我的笔记列表", "我想给笔记App添加标签功能",
        "能给开发笔记打上架构标签吗？", "再写一篇笔记", "这次写测试策略",
        "搜索所有笔记", "搜索包含架构的笔记", "笔记App支持Markdown吗？", "帮我用Markdown格式写一篇",
        "查看Markdown预览", "导出所有笔记", "导出成什么格式？", "导出成PDF",
        "导出完成了吗？", "好的，停止笔记App",
    ]},
    {"id": "S08", "name": "App删除与重建", "user_id": "user_lifecycle_03", "turns": [
        "看看我有哪些App", "删除那个不再使用的App", "确认删除", "真的删掉了吗？",
        "再列一次App列表", "好的，创建一个新的邮件管理App", "这个App需要配置邮件服务器",
        "用测试配置", "邮件App创建好了", "启动邮件App", "检查一下收件箱", "有新邮件吗？",
        "帮我读第一封邮件", "这封邮件重要吗？", "标记为已读", "帮我回复这封邮件",
        "回复内容是收到，谢谢", "发送了吗？", "停止邮件App", "我想删除这个测试用的邮件App",
    ]},
    {"id": "S09", "name": "App状态管理", "user_id": "user_lifecycle_04", "turns": [
        "创建一个监控面板App", "启动监控面板", "检查监控面板状态", "监控面板健康吗？",
        "查看监控面板的日志", "有什么错误日志吗？", "帮我查看性能指标", "CPU使用率多少？",
        "内存使用率呢？", "设置一个告警阈值", "CPU超过80%时告警", "告警设置好了吗？",
        "模拟一下高CPU负载", "告警触发了吗？", "查看告警历史", "清除所有告警",
        "修改告警阈值为90%", "确认修改生效", "重启监控面板", "重启后状态正常吗？",
    ]},
    {"id": "S10", "name": "App版本升级", "user_id": "user_lifecycle_05", "turns": [
        "创建一个数据看板App", "当前版本是多少？", "查看数据看板的详细信息", "数据看板有哪些功能？",
        "帮我添加一个图表功能", "添加折线图支持", "更新完成了吗？", "查看更新后的版本",
        "用新的图表功能画个图", "画一个销售趋势折线图", "图表渲染得怎么样？", "能导出图表吗？",
        "导出为PNG格式", "导出完成了吗？", "我想回退到上一个版本", "回退成功了吗？",
        "确认版本回退了", "再升级到最新版", "这次升级顺利吗？", "查看最终状态",
    ]},
    {"id": "S11", "name": "多App协同", "user_id": "user_lifecycle_06", "turns": [
        "创建一个日历App", "再创建一个提醒App", "两个App都启动了吗？", "在日历App里添加一个会议",
        "明天下午2点，项目评审会", "设置提醒App在会议前30分钟提醒", "提醒设置好了吗？",
        "查看明天的日程", "有多少个待办事项？", "会议和提醒关联了吗？", "修改会议时间为下午3点",
        "提醒时间自动调整了吗？", "取消这个会议", "提醒也取消了吗？", "在日历App里添加更多事件",
        "后天上午10点，团队建设", "给团队建设也设置提醒", "查看所有事件的提醒状态",
        "停止提醒App", "保留日历App继续运行",
    ]},
    {"id": "S12", "name": "App批量操作与安装链路", "user_id": "user_lifecycle_07", "turns": [
        "帮我创建三个App：博客、论坛、Wiki", "三个都创建好了吗？", "如果这些App要按标准安装链路交付，下一步通常先做什么",
        "先确认它们是不是已经正确安装和注册", "然后再统一启动", "都启动成功了吗？", "查看每个App的状态",
        "博客App能发帖吗？", "帮我发一篇测试博文", "论坛App能创建板块吗？", "创建一个技术讨论板块",
        "WikiApp能创建页面吗？", "创建一个关于AgentSystem的页面", "如果我要检查资产侧是否齐全，应该先 list 还是 discover",
        "如果发现缺少依赖资产，install 一个之后最少要验证什么", "三个App的存储用量各是多少？", "哪个App占用最多？", "统一停止三个App", "确认都停了", "只重新启动WikiApp并确认单独运行正常",
    ]},
    {"id": "S13", "name": "App配置管理", "user_id": "user_lifecycle_08", "turns": [
        "创建一个数据库管理App", "查看数据库App的默认配置", "修改数据库连接配置", "改成使用SQLite",
        "配置生效了吗？", "测试数据库连接", "连接成功了吗？", "帮我创建一张测试表",
        "表名users，字段id和name", "表创建成功了吗？", "插入一条测试数据", "查询所有数据",
        "能备份数据库吗？", "帮我备份", "备份文件在哪？", "恢复备份",
        "恢复成功了吗？", "数据完整性检查", "修改配置使用MySQL", "配置切换顺利吗？",
    ]},
    {"id": "S14", "name": "App权限管理", "user_id": "user_lifecycle_09", "turns": [
        "创建一个文件管理App", "设置文件管理App的访问权限", "只允许我访问", "权限设置好了吗？",
        "上传一个测试文件", "文件上传成功了吗？", "查看文件列表", "下载刚上传的文件",
        "文件内容正确吗？", "分享这个文件给另一个用户", "分享成功了吗？", "取消分享",
        "确认分享已取消", "修改文件权限为只读", "权限修改生效了吗？", "尝试写入文件",
        "写入被拒绝了吗？", "恢复读写权限", "删除测试文件", "文件删除了吗？",
    ]},
    {"id": "S15", "name": "App审计与日志", "user_id": "user_lifecycle_10", "turns": [
        "创建一个API网关App", "启动API网关", "发送一个测试请求", "请求成功了吗？",
        "查看API网关的访问日志", "有多少次请求记录？", "查看最近5次请求", "有失败的请求吗？",
        "查看错误日志", "错误率是多少？", "生成一份审计报告", "审计报告包含哪些内容？",
        "导出审计报告", "导出格式是什么？", "导出了吗？", "配置日志轮转策略",
        "设置保留7天的日志", "策略生效了吗？", "清理过期日志", "清理完成了吗？",
    ]},
    {"id": "S16", "name": "多轮-上下文保持", "user_id": "user_context_01", "turns": [
        "你好", "我叫小明，记住我的名字", "好的，小明。帮我创建一个个人博客App",
        "给博客App起个名字叫小明的博客", "在小明的博客里写一篇文章", "标题是我的第一个项目",
        "内容写关于我学习编程的经历", "小明还记得你吗？", "查看小明的博客文章列表",
        "编辑第一篇文章", "在文章末尾加上一段总结", "保存修改", "小明的博客访问正常吗？",
        "给文章添加标签", "加上编程和学习两个标签", "搜索小明写的所有文章",
        "小明有多少篇文章？", "删除最后一篇文章", "确认删除", "小明，谢谢你帮我管理博客",
    ]},
    {"id": "S17", "name": "多轮-话题切换", "user_id": "user_context_02", "turns": [
        "帮我创建一个任务App", "添加任务：完成报告", "对了，现在几点了？", "帮我查一下今天的天气",
        "回到任务App，再添加一个任务", "任务是准备明天会议的PPT", "查看任务列表",
        "标记完成报告已完成", "会议PPT需要什么内容？", "帮我生成一个PPT大纲",
        "大纲的第一部分写项目概述", "第二部分写进度汇报", "第三部分写下一步计划", "保存这个大纲",
        "任务App里有多少个未完成的任务？", "把会议PPT的截止日期设为明天",
        "提醒我下午3点交报告", "查看所有提醒", "取消下午3点的提醒", "好的，就这样",
    ]},
    {"id": "S18", "name": "多轮-纠错与修正", "user_id": "user_context_03", "turns": [
        "创建一个购物清单App", "添加苹果，5斤", "不对，改成3斤", "再添加香蕉，2把",
        "香蕉改成4把", "删除苹果", "哎呀，别删，恢复苹果", "苹果改回5斤",
        "查看当前清单", "添加牛奶，2箱", "牛奶要全脂的", "给牛奶加上全脂的备注",
        "清单里有多少种商品？", "总共需要花多少钱？", "帮我按价格排序", "导出购物清单",
        "分享给家人", "取消分享", "清空购物清单", "确认清空",
    ]},
    {"id": "S19", "name": "多轮-复杂需求", "user_id": "user_context_04", "turns": [
        "我想做一个项目管理App", "需要支持团队协作", "还要有甘特图", "能追踪进度",
        "可以分配任务给成员", "好的，按这些需求帮我创建", "项目管理App创建好了吗？",
        "添加一个项目：网站改版", "给网站改版项目创建任务", "第一个任务：需求分析",
        "第二个任务：UI设计", "第三个任务：前端开发", "第四个任务：后端开发",
        "第五个任务：测试上线", "设置任务之间的依赖关系", "需求分析完成后才能开始UI设计",
        "查看甘特图", "整体进度是多少？", "标记需求分析已完成", "现在UI设计可以开始了吗？",
    ]},
    {"id": "S20", "name": "多轮-追问深入", "user_id": "user_context_05", "turns": [
        "什么是大语言模型？", "它和传统AI有什么区别？", "能举几个实际应用的例子吗？",
        "这些应用是怎么实现的？", "需要用到哪些技术栈？", "帮我创建一个学习AI的App",
        "这个App应该包含哪些内容？", "先添加基础概念部分", "再添加实践案例部分",
        "案例部分要包含代码示例", "代码示例用Python写", "能运行这些代码吗？",
        "给我一个Hello World的示例", "运行这个示例", "输出结果是什么？",
        "再写一个更复杂的例子", "用Python实现一个简单的神经网络", "代码能跑通吗？",
        "保存所有示例", "这个学习App完成了吗？",
    ]},
    {"id": "S21", "name": "多轮-指令冲突处理", "user_id": "user_context_06", "turns": [
        "创建一个音乐App", "启动音乐App", "播放一首歌", "暂停", "继续播放", "停止音乐App",
        "删除音乐App", "等等，别删，恢复音乐App", "音乐App还能恢复吗？",
        "那重新创建一个音乐App", "新的音乐App和之前的一样吗？", "给音乐App添加播放列表功能",
        "创建一个我的最爱列表", "添加三首歌到列表", "第一首叫晴天", "第二首叫七里香",
        "第三首叫稻香", "播放我的最爱列表", "随机播放", "停止播放",
    ]},
    {"id": "S22", "name": "多轮-模糊需求澄清", "user_id": "user_context_07", "turns": [
        "帮我做个东西", "做什么呢？嗯...做一个管理工具", "管理什么东西？", "管理我的书籍",
        "那叫图书管理App", "需要记录书名、作者、状态", "状态分为已读和未读", "能按作者排序",
        "能搜索", "帮我添加第一本书", "书名百年孤独，作者马尔克斯，状态已读",
        "再添加一本", "活着，余华，已读", "添加第三本", "三体，刘慈欣，未读",
        "查看所有未读的书", "把所有书按书名排序", "搜索余华的书",
        "标记三体为已读", "现在我读了多少本书？",
    ]},
    {"id": "S23", "name": "多轮-长对话记忆", "user_id": "user_context_08", "turns": [
        "你好，我叫张三", "记住我的名字", "我喜欢吃川菜", "我的城市是成都",
        "帮我创建一个美食App", "在美食App里添加川菜分类", "添加一道水煮鱼", "再添加一道麻婆豆腐",
        "我是哪里人来着？", "我喜欢吃什么菜系？", "根据我的口味推荐一道菜",
        "推荐的菜加到美食App里", "查看所有收藏的菜", "张三的川菜清单有哪些？",
        "删除水煮鱼", "添加一道新的回锅肉", "我有几道收藏的菜？", "导出我的美食清单",
        "张三，你的清单导出完成了", "谢谢你，下次见",
    ]},
    {"id": "S24", "name": "多轮-指令链执行", "user_id": "user_context_09", "turns": [
        "创建一个数据分析App", "导入一份销售数据", "数据格式是CSV", "分析销售趋势",
        "按月统计", "画出月度趋势图", "找出销量最高的月份", "分析该月份的热销产品",
        "对比去年同期数据", "计算同比增长率", "生成分析报告", "报告包含哪些章节？",
        "导出报告为PDF", "同时导出Excel数据表", "两个文件都导出了吗？",
        "发送邮件给经理", "附上分析报告", "邮件发送成功了吗？", "查看发送记录",
        "停止数据分析App",
    ]},
    {"id": "S25", "name": "多轮-异常恢复与重启连续性", "user_id": "user_context_10", "turns": [
        "创建一个文档编辑器App", "打开一个新文档", "写一段文字：今天天气真好", "保存文档",
        "关闭文档", "重新打开", "内容还在吗？", "继续编辑：适合出去玩", "保存修改",
        "如果服务这时异常退出，重启后最先该检查什么", "先确认文档内容和会话状态是否还在", "再看这个App是否需要重新启动或恢复",
        "如果只恢复了一半，doctor 应该能帮我看出什么", "除了 doctor，还要不要看 runtime-layout 和日志目录", "那就按这个顺序做一次恢复检查",
        "查看版本历史", "恢复到第一个版本", "恢复成功了吗？", "导出为Markdown和PDF", "两个版本都保存好了吗？",
    ]},
    {"id": "S26", "name": "权限-用户隔离", "user_id": "user_security_01", "turns": [
        "创建我的个人App", "在我的App里添加一条私人笔记", "查看我的App列表",
        "尝试访问其他用户的App", "能看到别人的App吗？", "修改我的App权限为私有",
        "确认权限设置", "尝试分享我的私人笔记", "分享给用户user_security_02",
        "分享成功了吗？", "取消分享", "确认分享已取消", "另一个用户能看到我的笔记吗？",
        "查看我的隐私设置", "设置默认权限为私有", "创建一个公开的App",
        "公开App允许所有人访问", "确认公开App的权限", "删除私人笔记", "确认删除",
    ]},
    {"id": "S27", "name": "权限-角色管理", "user_id": "user_security_02", "turns": [
        "创建一个团队协作App", "添加成员user_security_01", "设置user_security_01为编辑者",
        "添加成员user_security_03", "设置user_security_03为查看者", "查看所有成员和角色",
        "编辑者能做什么操作？", "查看者能做什么操作？", "修改user_security_01为管理员",
        "确认角色变更", "添加一个新成员", "设置默认为查看者", "移除一个成员",
        "确认成员已移除", "查看团队App的权限矩阵", "创建一个新的子项目",
        "继承父项目的权限设置", "子项目权限正确吗？", "导出权限配置", "停止团队协作App",
    ]},
    {"id": "S28", "name": "权限-操作审计", "user_id": "user_security_03", "turns": [
        "创建一个敏感数据App", "设置高安全级别", "启用操作日志", "添加一条敏感数据",
        "查看操作日志", "记录了多少次操作？", "修改敏感数据", "再次查看日志",
        "能看到谁修改了数据吗？", "删除一条数据", "删除操作有记录吗？", "导出审计日志",
        "日志包含哪些字段？", "设置日志保留期限30天", "清理过期日志",
        "查看当前日志大小", "配置告警：异常操作通知", "测试告警触发", "收到告警了吗？",
        "停止敏感数据App",
    ]},
    {"id": "S29", "name": "权限-Token与限流", "user_id": "user_security_04", "turns": [
        "创建一个API测试App", "发送一个API请求", "请求成功了吗？", "查看当前Token用量",
        "发送大量请求测试限流", "连续发送10个请求", "被限流了吗？", "查看限流策略配置",
        "修改限流阈值为更高", "再次发送请求", "这次成功了吗？", "查看API调用统计",
        "成功率是多少？", "平均响应时间？", "查看错误率", "有哪些常见错误？",
        "生成API使用报告", "优化API配置", "验证优化效果", "停止API测试App",
    ]},
    {"id": "S30", "name": "权限-数据加密", "user_id": "user_security_05", "turns": [
        "创建一个加密记事本App", "设置加密密码", "添加一条加密笔记", "内容是密码123456",
        "保存并加密", "查看加密后的内容", "能看到明文吗？", "输入密码解密",
        "解密成功了吗？", "修改密码", "用新密码解密", "旧密码还能用吗？",
        "添加更多加密笔记", "查看所有加密笔记", "批量加密", "导出加密数据",
        "导出文件是加密的吗？", "导入加密备份", "导入成功了吗？", "删除所有笔记并销毁密钥",
    ]},
    {"id": "S31", "name": "错误-无效输入", "user_id": "user_error_01", "turns": [
        "帮我创建一个App", "", "   ", "创建一个名字叫空的App", "创建一个特殊字符的App: @#$%",
        "创建一个名字超长的App", "添加一个任务：", "添加一个只有空格的笔记", "搜索不存在的内容",
        "删除一个不存在的App", "修改一个不存在的App", "启动一个不存在的App",
        "查看不存在的App详情", "输入一段很长的文字" * 10, "输入包含emoji的文字😀",
        "输入HTML标签<script>alert(1)</script>", "输入SQL注入: ' OR 1=1 --",
        "输入JSON注入: {malformed", "正常输入：帮我创建一个测试App", "这个App能处理上面的异常输入吗？",
    ]},
    {"id": "S32", "name": "错误-并发冲突", "user_id": "user_error_02", "turns": [
        "创建一个共享文档App", "打开文档", "编辑文档：第一段内容", "同时编辑同一行",
        "修改为：第一段修改后的内容", "保存修改", "有冲突吗？", "解决冲突", "查看最终内容",
        "再打开另一个文档", "编辑第二个文档", "删除第一个文档", "在删除的同时编辑",
        "系统怎么处理？", "查看冲突日志", "恢复被删除的文档", "确认恢复成功",
        "再次尝试并发编辑", "这次有冲突吗？", "停止共享文档App",
    ]},
    {"id": "S33", "name": "错误-资源不足", "user_id": "user_error_03", "turns": [
        "创建一个图片处理App", "上传一张大图片", "图片处理正常吗？", "压缩这张图片",
        "压缩后的文件大小？", "批量处理10张图片", "处理完成了吗？", "上传一张超大图片",
        "系统能处理吗？", "内存够用吗？", "查看系统资源使用情况", "清理缓存",
        "再次尝试处理大图", "这次成功了吗？", "降低图片分辨率试试", "处理成功了吗？",
        "查看处理历史", "导出所有处理后的图片", "磁盘空间够吗？", "停止图片处理App",
    ]},
    {"id": "S34", "name": "错误-网络异常模拟", "user_id": "user_error_04", "turns": [
        "创建一个网络爬虫App", "爬取一个网页", "爬取成功了吗？", "解析网页内容",
        "提取所有链接", "爬取第二个网页", "模拟网络超时", "超时后系统怎么处理？",
        "有重试机制吗？", "重试了几次？", "模拟DNS解析失败", "系统能优雅地处理吗？",
        "查看错误日志", "错误信息清晰吗？", "模拟404错误", "404能正确处理吗？",
        "模拟500服务器错误", "系统崩溃了吗？", "恢复网络连接", "重新爬取，成功了吗？",
    ]},
    {"id": "S35", "name": "错误-数据一致性", "user_id": "user_error_05", "turns": [
        "创建一个数据库App", "创建一张数据表", "插入100条测试数据", "查询所有数据",
        "数据数量对吗？", "批量更新所有数据", "更新过程中断", "数据一致吗？",
        "回滚未完成的操作", "回滚成功了吗？", "再次查询数据", "数量和更新前一样吗？",
        "检查数据完整性", "有损坏的数据吗？", "修复损坏的数据", "修复完成",
        "备份数据库", "模拟数据损坏", "从备份恢复", "恢复后数据完整吗？",
    ]},
    {"id": "S36", "name": "Skill-安装失败与修复", "user_id": "user_skill_01", "turns": [
        "查看可用的Skill列表", "我想安装一个代码审查Skill", "如果安装失败，第一步应该先查什么", "先看看是资产没发现还是安装过程出错",
        "那就重新 discover 一次相关资产", "现在再试一次安装", "如果还是失败，doctor 能告诉我哪些线索？", "还需要看 installed 目录或者日志目录吗？",
        "假设修复后安装成功了，怎么确认它真的可用", "查看已安装的Skill", "用代码审查Skill检查一段代码", "代码是 def hello(): print('hello')",
        "审查结果如何？", "有改进建议吗？", "按照建议修改代码", "再次审查", "这次通过了吗？", "再安装一个翻译Skill做对比验证", "最后把这次安装失败到修复的排查步骤总结一下", "好的，后续都按这个流程处理",
    ]},
    {"id": "S37", "name": "Skill-自定义创建", "user_id": "user_skill_02", "turns": [
        "帮我创建一个自定义Skill", "这个Skill的功能是计算BMI", "输入身高和体重",
        "输出BMI值和健康建议", "测试这个Skill", "身高175cm，体重70kg", "计算结果正确吗？",
        "健康建议合理吗？", "修改BMI计算公式", "使用新的公式重新计算", "结果有变化吗？",
        "给Skill添加单位转换", "支持英寸和磅", "测试英制单位", "身高5英尺9英寸，体重154磅",
        "计算正确吗？", "保存这个Skill", "发布到Skill市场", "查看Skill详情", "有人用过吗？",
    ]},
    {"id": "S38", "name": "Skill-组合调用", "user_id": "user_skill_03", "turns": [
        "安装翻译Skill", "安装文本摘要Skill", "安装情感分析Skill", "三个Skill都安装好了吗？",
        "先用翻译Skill翻译一段英文", "翻译完成", "再用摘要Skill总结翻译后的内容",
        "总结完成了吗？", "最后用情感分析Skill分析情感", "情感倾向是正面还是负面？",
        "把这三个Skill串联起来", "创建一个自动化流程", "输入英文，输出摘要+情感",
        "测试流程", "流程执行成功吗？", "修改流程顺序", "先摘要再翻译",
        "结果有什么不同？", "保存新的流程", "删除旧流程",
    ]},
    {"id": "S39", "name": "Skill-性能调优", "user_id": "user_skill_04", "turns": [
        "安装一个图像处理Skill", "处理一张测试图片", "处理耗时多少？", "能优化性能吗？",
        "降低处理质量加快速度", "这次耗时多少？", "速度提升明显吗？", "批量处理10张图片",
        "全部处理完了吗？", "查看性能报告", "平均处理时间？", "内存占用多少？",
        "能并行处理吗？", "开启并行处理", "并行后速度提升多少？", "有错误吗？",
        "调整并行度", "找到最优配置", "保存配置", "停止图像处理App",
    ]},
    {"id": "S40", "name": "Skill-推荐与发现", "user_id": "user_skill_05", "turns": [
        "有什么推荐的Skill吗？", "根据我的使用习惯推荐", "我常用文本处理类App",
        "推荐一个适合的Skill", "这个Skill怎么用？", "安装推荐的Skill",
        "在文本App里使用这个Skill", "效果好吗？", "有没有更好的替代Skill？",
        "比较两个Skill的功能", "哪个更适合我？", "切换到更好的Skill", "卸载旧Skill",
        "浏览Skill市场", "按评分排序", "查看最高评分的Skill", "试用一下",
        "满意吗？", "安装这个Skill", "给这个Skill打分",
    ]},
    {"id": "S41", "name": "系统-状态与运维检查", "user_id": "user_system_01", "turns": [
        "先给我看一下系统当前状态", "现在有多少个App在运行？", "如果状态异常，第一步应该先查什么？", "那再做一次健康检查",
        "健康检查最该关注哪些结果", "把当前运行时目录布局也讲给我", "配置目录和数据目录分别负责什么", "日志目录和 installed 目录又分别是干什么的？",
        "如果我怀疑是安装问题，不看业务功能的话先查哪几个入口", "除了 status 和 doctor，还有哪些 CLI 动作最关键", "如果服务卡住了，restart 和 stop 的判断边界是什么",
        "假设我要检查资产能力，先 list 还是先 discover", "两者的区别是什么", "如果我要安装一个资产，安装前要先确认什么", "安装后应该怎么验证它真的可用了",
        "如果我要做一次标准安装迁移前检查，最少要确认哪些项目", "为什么还要跑 50x20 的用户级基线回归", "如果回归里发现 operator 场景不足，应该优先补哪类场景", "把这套运维检查流程给我总结成简版 checklist", "好的，按这个 checklist 继续",
    ]},
    {"id": "S42", "name": "系统-配置管理", "user_id": "user_system_02", "turns": [
        "查看系统配置", "默认语言是什么？", "修改默认语言为英文", "语言切换成功吗？",
        "Hello, can you understand me?", "切换回中文", "你好，还能理解我吗？",
        "查看时区设置", "修改时区为UTC", "当前时间是多少？", "改回Asia/Shanghai",
        "查看主题设置", "切换为暗色主题", "主题生效了吗？", "查看通知设置",
        "开启邮件通知", "开启App创建通知", "查看所有通知设置", "导出配置文件", "恢复默认配置",
    ]},
    {"id": "S43", "name": "系统-备份恢复", "user_id": "user_system_03", "turns": [
        "创建三个测试App", "确认三个App都运行正常", "备份整个系统", "备份完成了吗？",
        "备份文件多大？", "备份文件在哪？", "删除所有App", "确认所有App都删除了",
        "从备份恢复", "恢复完成了吗？", "三个App都恢复了吗？", "App的状态还在吗？",
        "数据完整吗？", "检查每个App的内容", "第一个App正常吗？", "第二个App正常吗？",
        "第三个App正常吗？", "生成恢复报告", "备份策略配置", "设置自动备份每天一次",
    ]},
    {"id": "S44", "name": "系统-用户管理", "user_id": "user_system_04", "turns": [
        "查看用户列表", "有多少个注册用户？", "创建新用户test_user", "设置test_user的权限",
        "查看test_user的详情", "修改test_user的权限", "禁用test_user",
        "test_user还能登录吗？", "重新启用test_user", "查看活跃用户", "有多少个活跃用户？",
        "查看用户登录历史", "最近一次登录是什么时候？", "查看所有用户创建的App",
        "哪个用户创建的App最多？", "查看用户统计", "导出用户报告", "删除test_user",
        "确认删除", "test_user的数据清理了吗？",
    ]},
    {"id": "S45", "name": "系统-日志分析", "user_id": "user_system_05", "turns": [
        "创建几个App并操作", "查看系统日志", "日志总量多少？", "按类型分类统计",
        "有多少错误日志？", "有哪些常见错误？", "错误集中在什么时间段？", "查看警告日志",
        "警告需要处理吗？", "分析日志趋势", "日志量在增长吗？", "生成日志分析报告",
        "报告的关键发现是什么？", "优化日志配置", "减少冗余日志", "配置日志归档",
        "归档旧日志", "查看归档文件", "恢复归档日志", "清理过期日志",
    ]},
    {"id": "S46", "name": "交叉-多用户操作同一系统", "user_id": "user_cross_01", "turns": [
        "创建一个共享项目App", "添加任务：设计阶段", "添加任务：开发阶段", "添加任务：测试阶段",
        "查看任务列表", "标记设计阶段完成", "查看剩余任务", "添加新任务：部署阶段",
        "修改开发阶段的描述", "删除测试阶段", "重新添加测试阶段", "排序任务按优先级",
        "查看项目进度", "导出项目报告", "分享给团队成员", "查看分享状态",
        "取消分享", "修改项目名字为项目A", "确认名字修改", "停止项目A",
    ]},
    {"id": "S47", "name": "交叉-高频快速操作", "user_id": "user_cross_02", "turns": [
        "快速创建5个App", "都创建好了吗？", "快速启动所有App", "都启动了吗？",
        "快速列出所有App", "快速查看每个App状态", "快速修改第一个App名字",
        "快速修改第二个App名字", "快速修改第三个App名字", "快速停止所有App",
        "都停了吗？", "快速删除前两个App", "确认删除", "查看剩余App",
        "重新启动剩余App", "查看运行中的App数量", "快速创建一个新的App",
        "快速停止它", "快速删除它", "最终还有几个App？",
    ]},
    {"id": "S48", "name": "交叉-混合指令类型", "user_id": "user_cross_03", "turns": [
        "你好", "创建一个天气App", "系统状态如何？", "查看我的App列表", "启动天气App",
        "今天的天气怎么样？", "有什么Skill推荐？", "安装一个翻译Skill", "翻译Hello World",
        "天气App能正常使用吗？", "修改天气App的名字", "确认修改", "系统有多少用户？",
        "创建一个新的笔记App", "写一条笔记", "查看笔记列表", "停止笔记App",
        "查看系统日志", "生成一份报告", "好的，谢谢",
    ]},
    {"id": "S49", "name": "交叉-长时间会话", "user_id": "user_cross_04", "turns": [
        "开始一个新项目", "项目叫个人网站", "先做需求分析", "记录需求：响应式设计",
        "记录需求：博客功能", "记录需求：联系表单", "创建网站项目App", "在App里添加设计任务",
        "添加开发任务", "添加测试任务", "给每个任务设置截止日期", "查看所有任务的时间线",
        "先完成设计任务", "标记设计为已完成", "开始开发", "开发进度如何？",
        "记录开发笔记", "遇到一个问题需要解决", "记录问题和解决方案", "生成项目进度报告",
    ]},
    {"id": "S50", "name": "交叉-标准安装运维全流程", "user_id": "user_cross_05", "turns": [
        "我是新来的运维，先告诉我这个系统现在怎么安装和启动", "先检查当前运行状态", "再做一次健康检查",
        "把当前运行时目录布局给我讲清楚", "如果我要查看可用资产，应该怎么查", "那就列一下当前可见的资产",
        "再试试发现还没安装的资产", "假设我要安装一个 asset.demo 资产，应该怎么做", "安装前要注意什么前置条件？",
        "如果服务异常，我应该先 stop 还是先 doctor", "那 restart 适合什么场景", "如果我要迁移到标准安装模型，第一步应该做什么",
        "迁移前为什么要先做 50x20 基线回归", "如果回归里发现资产链路缺失，应该先补什么", "那当前这套基线最明显缺什么类型的场景",
        "除了资产链路，还缺哪些 operator 生命周期场景", "如果我要把 repo 脚本入口逐步收敛到统一 CLI，应该怎么理解现在的状态",
        "那 start_server.sh 和 start_web_server.sh 现在扮演什么角色", "请把标准安装迁移前的关键检查项给我总结成一个简短清单", "好的，按这个方向继续推进",
    ]},
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TurnResult:
    turn_index: int
    message: str
    ok: bool
    content_preview: str = ""
    error: str = ""
    elapsed_ms: float = 0.0
    http_status: int = 0
    session_id: str = ""
    full_response: str = ""
    closure_signals: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioExpectationResult:
    ok: bool
    checks: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


@dataclass
class ScenarioResult:
    scenario_id: str
    name: str
    user_id: str
    total_turns: int
    turns: list = field(default_factory=list)
    session_ids: list = field(default_factory=list)
    total_ok: int = 0
    total_fail: int = 0
    total_error: int = 0   # HTTP/network errors (not counted as business fail)
    total_ms: float = 0.0
    expectation: ScenarioExpectationResult | None = None
    closure_summary: dict[str, Any] | None = None
    aborted_early: bool = False
    abort_reason: str = ""


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class E2EClient:
    """Thin wrapper around httpx for the AgentSystem /api/chat endpoint.

    Auth: POST /login with username → sets session_id cookie.
    Chat: POST /api/chat with {"message": ..., "session_id": ...}
    """

    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)
        self._session_map: dict[str, str] = {}  # user_id -> session_id (cookie)

    def login(self, username: str) -> str:
        """Login via POST /login. Returns session_id."""
        resp = self.client.post(
            f"{self.base_url}/login",
            data={"username": username},
        )
        resp.raise_for_status()
        data = resp.json()
        sid = data.get("session_id", f"session_{username}")
        self._session_map[username] = sid
        return sid

    def send_message(
        self,
        user_id: str,
        message: str,
        session_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a chat message via /api/chat. Returns parsed JSON.

        The auth cookie (session_id) is managed automatically by httpx's
        cookie jar. We also send session_id in the JSON body for the
        AgentSystem's own session tracking.
        """
        # Ensure we're logged in as this user
        if user_id not in self._session_map:
            self.login(user_id)

        # Use the cookie session_id for continuity
        cookie_sid = self._session_map.get(user_id)
        body_sid = session_id or cookie_sid

        payload = {
            "message": message,
            "session_id": body_sid,
            "payload": payload or None,
        }

        resp = self.client.post(
            f"{self.base_url}/api/chat",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

        # Track session for continuity
        returned_sid = data.get("session_id")
        if returned_sid:
            self._session_map[user_id] = returned_sid

        return data

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        resp = self.client.get(f"{self.base_url}/api/history/{session_id}")
        resp.raise_for_status()
        data = resp.json()
        return list(data.get("history") or [])

    def close(self):
        self.client.close()


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def _evaluate_turn_closure(*, ok: bool, response_text: str, error_text: str = "") -> dict[str, Any]:
    text = (response_text or "").strip()
    lower = text.lower()
    empty_response = not text
    very_short_response = bool(text) and len(text) < 8
    fallback_markers = ["无法", "不能", "抱歉", "请先", "需要", "澄清", "进一步验证", "稍后"]
    fallback_like = any(marker in text for marker in fallback_markers)
    workflow_markers = ["已", "完成", "成功", "处理", "创建", "启动", "更新", "可以", "如下"]
    workflow_success_hint = ok and any(marker in text for marker in workflow_markers)
    informative_length_ok = len(text) >= 20
    score = 0.0
    if ok:
        score += 0.35
    if not empty_response:
        score += 0.20
    if informative_length_ok:
        score += 0.20
    if workflow_success_hint:
        score += 0.15
    if not fallback_like:
        score += 0.10
    score = max(0.0, min(1.0, round(score, 2)))
    return {
        "raw_ok": ok,
        "empty_response": empty_response,
        "very_short_response": very_short_response,
        "informative_length_ok": informative_length_ok,
        "fallback_like": fallback_like,
        "workflow_success_hint": workflow_success_hint,
        "closure_score": score,
        "error_present": bool(error_text),
        "response_length": len(text),
        "response_excerpt": text[:120],
    }


def _summarize_scenario_closure(result: ScenarioResult) -> dict[str, Any]:
    signals = [t.closure_signals for t in result.turns if t.closure_signals]
    if not signals:
        return {
            "avg_closure_score": 0.0,
            "empty_response_turns": 0,
            "very_short_response_turns": 0,
            "fallback_like_turns": 0,
            "workflow_success_hint_turns": 0,
            "raw_ok_turns": result.total_ok,
        }
    return {
        "avg_closure_score": round(sum(float(s.get("closure_score", 0.0)) for s in signals) / len(signals), 2),
        "empty_response_turns": sum(1 for s in signals if s.get("empty_response")),
        "very_short_response_turns": sum(1 for s in signals if s.get("very_short_response")),
        "fallback_like_turns": sum(1 for s in signals if s.get("fallback_like")),
        "workflow_success_hint_turns": sum(1 for s in signals if s.get("workflow_success_hint")),
        "raw_ok_turns": sum(1 for s in signals if s.get("raw_ok")),
    }


def _wait_for_service(base_url: str, timeout_seconds: float = 30.0) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout_seconds
    last_error = "service did not become ready"
    while time.monotonic() < deadline:
        try:
            with httpx.Client(timeout=5.0, trust_env=False) as hc:
                resp = hc.get(f"{base_url}/api/status")
                if resp.status_code < 500:
                    return True, f"HTTP {resp.status_code}"
                last_error = f"HTTP {resp.status_code}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1.0)
    return False, last_error


def _evaluate_scenario_history(scenario: dict, history: list[dict[str, Any]], result: ScenarioResult) -> ScenarioExpectationResult:
    checks: list[str] = []
    failures: list[str] = []

    user_messages = [item for item in history if item.get("role") == "user"]
    assistant_messages = [item for item in history if item.get("role") == "assistant"]

    expected_turns = len(result.turns)

    if len(user_messages) != expected_turns:
        failures.append(f"expected {expected_turns} user turns, got {len(user_messages)}")
    else:
        checks.append(f"user turn count matched: {len(user_messages)}")

    if len(assistant_messages) < max(1, expected_turns - 2):
        failures.append(f"assistant replies too few: {len(assistant_messages)}")
    else:
        checks.append(f"assistant replies acceptable: {len(assistant_messages)}")

    unique_sessions = {sid for sid in result.session_ids if sid}
    if len(unique_sessions) > 1:
        failures.append(f"session drift detected: {sorted(unique_sessions)}")
    elif len(unique_sessions) == 1:
        checks.append(f"single session preserved: {next(iter(unique_sessions))}")

    last_reply = (assistant_messages[-1].get("content") or "") if assistant_messages else ""
    if not last_reply.strip():
        failures.append("final assistant reply empty")
    else:
        checks.append("final assistant reply non-empty")

    lower_blob = "\n".join((item.get("content") or "") for item in assistant_messages).lower()
    bad_markers = ["traceback", "internal server error", "llm request failed"]
    found_bad = [marker for marker in bad_markers if marker in lower_blob]
    if found_bad:
        failures.append(f"unexpected error markers in conversation: {found_bad}")
    else:
        checks.append("no obvious error markers in assistant history")

    return ScenarioExpectationResult(ok=not failures, checks=checks, failures=failures)


def _scenario_verdict(result: ScenarioResult) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if result.total_error > 0:
        reasons.append(f"transport_or_service_errors={result.total_error}")
    if result.total_fail > 0:
        reasons.append(f"failed_turns={result.total_fail}")
    if result.expectation and not result.expectation.ok:
        reasons.extend(result.expectation.failures[:3])
    if not reasons:
        reasons.append("all_turns_and_history_checks_passed")
    verdict = "pass" if result.total_fail == 0 and result.total_error == 0 and (not result.expectation or result.expectation.ok) else "fail"
    return verdict, reasons


def _effective_user_id(user_id: str, run_id: str | None) -> str:
    if not run_id:
        return user_id
    safe_run = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})
    return f"{user_id}__{safe_run}"


def run_scenario(
    client: E2EClient,
    scenario: dict,
    delay: float,
    turn_timeout: float = 120.0,
    run_id: str | None = None,
    max_consecutive_failures: int = 0,
    max_turns: int | None = None,
) -> ScenarioResult:
    user_id = _effective_user_id(scenario["user_id"], run_id)
    result = ScenarioResult(
        scenario_id=scenario["id"],
        name=scenario["name"],
        user_id=user_id,
        total_turns=len(scenario["turns"]),
    )

    current_session: str | None = None
    consecutive_failures = 0
    scenario_turns = scenario["turns"][:max_turns] if max_turns and max_turns > 0 else scenario["turns"]

    for idx, message in enumerate(scenario_turns):
        # Skip empty messages (S31 has some intentional empty/whitespace inputs)
        if not message.strip() and scenario["id"] == "S31":
            tr = TurnResult(
                turn_index=idx + 1, message=message, ok=True,
                content_preview="(empty input — expected to handle gracefully)",
            )
            result.turns.append(tr)
            result.total_ok += 1
            if delay > 0:
                time.sleep(delay)
            continue

        t0 = time.monotonic()
        try:
            data = client.send_message(
                user_id,
                message,
                session_id=current_session,
                payload={"run_id": run_id, "scenario_id": scenario["id"]} if run_id else {"scenario_id": scenario["id"]},
            )
            elapsed = (time.monotonic() - t0) * 1000

            content = data.get("content", "")[:200]
            ok = data.get("ok", True) or data.get("type") != "error"
            sid = data.get("session_id", "")
            if sid:
                current_session = sid
                result.session_ids.append(sid)

            tr = TurnResult(
                turn_index=idx + 1,
                message=message,
                ok=bool(ok),
                content_preview=content,
                elapsed_ms=elapsed,
                http_status=200,
                session_id=sid,
                full_response=data.get("response", "") or "",
                closure_signals=_evaluate_turn_closure(
                    ok=bool(ok),
                    response_text=(data.get("response", "") or data.get("content", "") or ""),
                ),
            )
        except httpx.HTTPStatusError as exc:
            elapsed = (time.monotonic() - t0) * 1000
            tr = TurnResult(
                turn_index=idx + 1,
                message=message,
                ok=False,
                error=f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
                elapsed_ms=elapsed,
                http_status=exc.response.status_code,
                closure_signals=_evaluate_turn_closure(ok=False, response_text="", error_text=exc.response.text[:200]),
            )
            result.total_error += 1
        except httpx.TimeoutException:
            elapsed = (time.monotonic() - t0) * 1000
            tr = TurnResult(
                turn_index=idx + 1,
                message=message,
                ok=False,
                error=f"Timeout after {turn_timeout}s",
                elapsed_ms=elapsed,
                closure_signals=_evaluate_turn_closure(ok=False, response_text="", error_text=f"Timeout after {turn_timeout}s"),
            )
            result.total_error += 1
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            tr = TurnResult(
                turn_index=idx + 1,
                message=message,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=elapsed,
                closure_signals=_evaluate_turn_closure(ok=False, response_text="", error_text=f"{type(exc).__name__}: {exc}"),
            )
            result.total_error += 1

        result.turns.append(tr)
        if tr.ok:
            result.total_ok += 1
            consecutive_failures = 0
        else:
            result.total_fail += 1
            consecutive_failures += 1
        result.total_ms += tr.elapsed_ms

        # Progress indicator
        status = "✅" if tr.ok else "❌"
        preview = tr.content_preview[:60] if tr.content_preview else (tr.error[:60] if tr.error else "")
        print(f"    [{idx+1:02d}/20] {status} {elapsed/1000:.1f}s | {preview}")

        if max_consecutive_failures > 0 and consecutive_failures >= max_consecutive_failures:
            result.aborted_early = True
            result.abort_reason = f"consecutive_failures={consecutive_failures}"
            print(f"    [abort] ⏹️ reached max consecutive failures: {consecutive_failures}")
            break

        # Delay between turns to avoid vLLM overload
        if delay > 0 and idx < len(scenario_turns) - 1:
            time.sleep(delay)

    if current_session:
        try:
            history = client.get_history(current_session)
            result.expectation = _evaluate_scenario_history(scenario, history, result)
            if result.expectation.ok:
                print(f"    [history] ✅ scenario-end history checks passed ({len(history)} records)")
            else:
                print(f"    [history] ❌ scenario-end history checks failed: {'; '.join(result.expectation.failures[:3])}")
                result.total_fail += 1
        except Exception as exc:
            print(f"    [history] ❌ failed to fetch/evaluate history: {exc}")
            result.total_fail += 1
            result.total_error += 1

    result.closure_summary = _summarize_scenario_closure(result)
    return result


def main():
    parser = argparse.ArgumentParser(description="50×20 User-Level E2E Test")
    parser.add_argument("--base-url", default="http://localhost:8765", help="AgentSystem base URL")
    parser.add_argument("--delay", type=float, default=3.0, help="Seconds between turns (default: 3)")
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-turn timeout in seconds (default: 120)")
    parser.add_argument("--scenarios", default="", help="Comma-separated scenario IDs to run (e.g. S01,S02)")
    parser.add_argument("--range", default="", help="Scenario range (e.g. 1-10)")
    parser.add_argument("--output", default="/tmp/agentsystem_e2e_user_level_report.json", help="Report output path")
    parser.add_argument("--run-id", default=f"e2e-user-level-{uuid4().hex[:12]}", help="Run identifier for correlating chat logs and scenario traces")
    parser.add_argument("--wait-ready-seconds", type=float, default=30.0, help="How long to wait for /api/status readiness before running (default: 30)")
    parser.add_argument("--max-consecutive-failures", type=int, default=0, help="Abort a scenario early after this many consecutive failed turns (default: disabled)")
    parser.add_argument("--max-turns-per-scenario", type=int, default=0, help="Limit how many turns to execute per scenario for bounded diagnostics (default: full scenario)")
    args = parser.parse_args()

    # Filter scenarios
    selected = SCENARIOS
    if args.scenarios:
        ids = {s.strip() for s in args.scenarios.split(",")}
        selected = [s for s in SCENARIOS if s["id"] in ids]
    elif args.range:
        parts = args.range.split("-")
        lo, hi = int(parts[0]), int(parts[1]) if len(parts) > 1 else len(SCENARIOS)
        selected = [s for s in SCENARIOS if lo <= int(s["id"][1:]) <= hi]

    total_turns = len(selected) * 20
    effective_turns_per_scenario = args.max_turns_per_scenario if args.max_turns_per_scenario > 0 else 20
    planned_executed_turns = sum(min(len(s["turns"]), effective_turns_per_scenario) for s in selected)
    est_minutes = planned_executed_turns * (args.delay + 5) / 60  # rough: delay + avg LLM time

    print(f"{'='*70}")
    print(f"  50 场景 × 20 轮 用户级 E2E 测试")
    print(f"{'='*70}")
    print(f"  目标服务:   {args.base_url}")
    print(f"  Run ID:     {args.run_id}")
    print(f"  场景数量:   {len(selected)}")
    print(f"  计划轮次:   {total_turns}")
    print(f"  执行轮次:   {planned_executed_turns}")
    print(f"  轮次延迟:   {args.delay}s")
    print(f"  超时:       {args.timeout}s")
    print(f"  预计耗时:   ~{est_minutes:.0f} 分钟")
    print(f"{'='*70}")

    # Health check
    print(f"\n[1/3] 检查服务连通性 ...")
    ready, ready_detail = _wait_for_service(args.base_url, timeout_seconds=args.wait_ready_seconds)
    if ready:
        print(f"  ✅ 服务就绪 ({ready_detail})")
    else:
        print(f"  ❌ 服务不可达: {ready_detail}")
        print(f"  请先启动 AgentSystem 服务:")
        print(f"    在项目目录执行: bash start_web_server.sh")
        sys.exit(1)

    # Run tests
    print(f"\n[2/3] 执行测试 ...")
    client = E2EClient(args.base_url, timeout=args.timeout)
    all_results: list[ScenarioResult] = []
    grand_start = time.monotonic()

    for idx, scenario in enumerate(selected):
        t0 = time.monotonic()
        print(f"\n  [{idx+1:03d}/{len(selected):03d}] {scenario['id']} {scenario['name']} ({scenario['user_id']})")
        sr = run_scenario(
            client,
            scenario,
            delay=args.delay,
            turn_timeout=args.timeout,
            run_id=args.run_id,
            max_consecutive_failures=args.max_consecutive_failures,
            max_turns=(args.max_turns_per_scenario or None),
        )
        elapsed = time.monotonic() - t0

        verdict, reasons = _scenario_verdict(sr)
        status = "✅" if verdict == "pass" else f"⚠️ {sr.total_fail}fail"
        if sr.total_error > 0:
            status += f" ({sr.total_error} errors)"
        print(f"  → {status} {sr.total_ok}ok/{sr.total_fail}fail, {elapsed:.1f}s")
        print(f"    verdict={verdict} | reason={' ; '.join(reasons[:3])}")
        all_results.append(sr)

    grand_elapsed = time.monotonic() - grand_start
    client.close()

    # Summary
    print(f"\n{'='*70}")
    print(f"  E2E 用户级测试报告 — {len(all_results)} 场景 × 20 轮 = {len(all_results)*20} 计划轮")
    print(f"{'='*70}")

    total_scenarios = len(all_results)
    scenarios_all_ok = sum(1 for r in all_results if r.total_fail == 0)
    scenarios_with_fail = total_scenarios - scenarios_all_ok
    total_turns_run = sum(len(r.turns) for r in all_results)
    total_ok = sum(r.total_ok for r in all_results)
    total_fail = sum(r.total_fail for r in all_results)
    total_errors = sum(r.total_error for r in all_results)

    pass_rate = total_ok / total_turns_run * 100 if total_turns_run > 0 else 0

    print(f"  总耗时:         {grand_elapsed/60:.1f} 分钟 ({grand_elapsed:.0f}s)")
    print(f"  场景全通过:     {scenarios_all_ok}/{total_scenarios} ({scenarios_all_ok/total_scenarios*100:.0f}%)")
    print(f"  场景有失败:     {scenarios_with_fail}/{total_scenarios}")
    print(f"  计划轮次:       {total_turns}")
    print(f"  执行预算轮次:   {planned_executed_turns}")
    print(f"  实际执行轮次:   {total_turns_run}")
    print(f"  成功轮次:       {total_ok} ({pass_rate:.1f}%)")
    print(f"  失败轮次:       {total_fail}")
    print(f"  网络/服务错误:  {total_errors}")
    print(f"  平均轮次耗时:   {grand_elapsed/total_turns_run:.1f}s")

    # Failed scenario details
    failed_scenarios = [r for r in all_results if _scenario_verdict(r)[0] == "fail"]
    if failed_scenarios:
        print(f"\n  失败场景详情:")
        for r in failed_scenarios:
            verdict, reasons = _scenario_verdict(r)
            print(f"\n    {r.scenario_id} {r.name} ({r.user_id}): verdict={verdict}, reason={' ; '.join(reasons[:3])}")
            print(f"      turns={r.total_ok}ok/{r.total_fail}fail, errors={r.total_error}")
            if r.closure_summary:
                print(
                    f"      closure_score={r.closure_summary.get('avg_closure_score')} "
                    f"empty={r.closure_summary.get('empty_response_turns')} "
                    f"short={r.closure_summary.get('very_short_response_turns')} "
                    f"fallback={r.closure_summary.get('fallback_like_turns')}"
                )
            for t in r.turns:
                if not t.ok:
                    msg_preview = t.message[:50] if t.message else "(empty)"
                    print(f"      Turn {t.turn_index}: '{msg_preview}' → {t.error[:100]}")

    # Save report
    report = {
        "test_type": "user_level_e2e",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "delay_seconds": args.delay,
        "timeout_seconds": args.timeout,
        "max_turns_per_scenario": args.max_turns_per_scenario,
        "max_consecutive_failures": args.max_consecutive_failures,
        "total_scenarios": total_scenarios,
        "planned_total_turns": total_turns,
        "executed_turn_budget": planned_executed_turns,
        "scenarios_all_ok": scenarios_all_ok,
        "scenarios_with_fail": scenarios_with_fail,
        "total_turns": total_turns_run,
        "total_ok": total_ok,
        "total_fail": total_fail,
        "total_errors": total_errors,
        "pass_rate_pct": round(pass_rate, 1),
        "total_seconds": round(grand_elapsed, 1),
        "avg_turn_seconds": round(grand_elapsed / total_turns_run, 1) if total_turns_run > 0 else 0,
        "details": [
            {
                "id": r.scenario_id, "name": r.name, "user_id": r.user_id,
                "total_turns": r.total_turns, "ok": r.total_ok, "fail": r.total_fail,
                "errors": r.total_error, "seconds": round(r.total_ms / 1000, 1),
                "verdict": _scenario_verdict(r)[0],
                "verdict_reasons": _scenario_verdict(r)[1],
                "history_expectation_ok": r.expectation.ok if r.expectation else None,
                "history_expectation_failures": r.expectation.failures if r.expectation else [],
                "history_expectation_checks": r.expectation.checks if r.expectation else [],
                "closure_summary": r.closure_summary or {},
                "aborted_early": r.aborted_early,
                "abort_reason": r.abort_reason,
                "turns": [
                    {
                        "turn": t.turn_index,
                        "message": t.message[:100],
                        "ok": t.ok,
                        "content_preview": t.content_preview[:100],
                        "error": t.error[:200] if t.error else "",
                        "elapsed_s": round(t.elapsed_ms / 1000, 1),
                        "session_id": t.session_id,
                        "closure_signals": t.closure_signals,
                    }
                    for t in r.turns
                ],
            }
            for r in all_results
        ],
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  报告已保存: {output_path}")

    # Verdict
    print(f"\n{'='*70}")
    if scenarios_all_ok == total_scenarios:
        print(f"  ✅ 全部 {total_scenarios} 个场景通过！")
    else:
        print(f"  ⚠️  {scenarios_with_fail}/{total_scenarios} 个场景有失败")
    print(f"{'='*70}")

    return 0 if scenarios_all_ok == total_scenarios else 1


if __name__ == "__main__":
    sys.exit(main())
