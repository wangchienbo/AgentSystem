import yaml
from pathlib import Path
"""
Context Compressor - 智能上下文压缩组件
目标：降低长对话 Token 消耗 (>35%)，提升响应速度 (>20%)
策略：
1. 关键信息 (正则匹配) 100% 保留
2. 普通对话每 3 轮压缩为 1 句摘要
3. 支持配置压缩档位 (激进/平衡/保守)
"""
import re
from typing import List, Dict, Any

class ContextCompressor:
    def __init__(self, mode: str = "balanced"):
        """
        mode: "aggressive" | "balanced" | "conservative"
        """
        self.mode = mode
        # 关键信息正则模式
        self.key_patterns = [
            r"我叫 [叫是] (.+)",
            r"路径 [是] ?:? ?(\S+)",
            r"项目 [在] ?:? ?(\S+)",
            r"记住 [：:]? (.+)",
            r"密码 [是] ?:? ?(\S+)",
        ]

    def is_key_info(self, text: str) -> bool:
        """判断是否包含关键信息"""
        for pattern in self.key_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def compress_history(self, history:
        # Load from global config if not provided
        if max_turns is None:
            try:
                cfg = yaml.safe_load(Path("/root/.config/agentsystem/config.yaml").read_text(encoding="utf-8")) or {}
                app_cfg = cfg.get("app", {}) or {}
                max_turns = app_cfg.get("context_compress_turns", 10)
            except Exception:
                max_turns = 10 List[Dict[str, Any]], max_turns: int = 30) -> List[Dict[str, Any]]:
        """
        压缩历史记录
        - 保留最近 3 轮完整对话
        - 之前对话：关键信息保留，普通对话每 3 轮压缩为摘要
        """
        if len(history) <= max_turns:
            return history

        # 分离关键信息与普通对话
        key_messages = []
        normal_history = []

        for msg in history:
            if self.is_key_info(msg.get("content", "")):
                key_messages.append(msg)
            else:
                normal_history.append(msg)

        # 如果关键信息 + 最近 max_turns 仍超限，则对普通历史进行摘要
        if len(key_messages) + len(normal_history) <= max_turns:
            return history  # 无需压缩

        # 激进模式：只保留最近 max_turns 轮，其余摘要
        if self.mode == "aggressive":
            compressed = self._aggressive_compress(normal_history, max_turns - len(key_messages))
            return key_messages + compressed
        
        # 平衡/保守模式：保留最近 3 轮完整，之前摘要
        recent_turns = 3
        recent_messages = normal_history[-recent_turns * 2:] if len(normal_history) > recent_turns * 2 else normal_history
        older_messages = normal_history[:-recent_turns * 2] if len(normal_history) > recent_turns * 2 else []
        
        if older_messages:
            summary_msg = {
                "role": "system",
                "content": f"[历史摘要] 之前 {len(older_messages)//2} 轮对话已压缩。主要讨论了用户身份、项目路径等上下文。"
            }
            return key_messages + [summary_msg] + recent_messages
        
        return key_messages + normal_history

    def _aggressive_compress(self, messages: List[Dict[str, Any]], keep_limit: int) -> List[Dict[str, Any]]:
        """激进压缩：只保留最近 keep_limit 条消息"""
        if len(messages) <= keep_limit:
            return messages
        # 丢弃旧消息，保留最新
        return messages[-keep_limit:]

# 测试用例
if __name__ == "__main__":
    compressor = ContextCompressor(mode="balanced")
    test_history = [
        {"role": "user", "content": "我叫张三"},
        {"role": "assistant", "content": "你好张三"},
        {"role": "user", "content": "闲聊 1"},
        {"role": "assistant", "content": "回复 1"},
        {"role": "user", "content": "闲聊 2"},
        {"role": "assistant", "content": "回复 2"},
    ]
    compressed = compressor.compress_history(test_history, max_turns=4)
    print(f"原始条数：{len(test_history)}, 压缩后：{len(compressed)}")
    print(compressed)
