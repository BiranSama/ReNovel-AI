import re
from typing import Optional


class TokenCounter:
    AVG_CHARS_PER_TOKEN_EN = 4
    AVG_CHARS_PER_TOKEN_ZH = 2
    
    def __init__(self):
        self._tiktoken_encoder = None
    
    def _load_tiktoken(self):
        if self._tiktoken_encoder is not None:
            return
        
        try:
            import tiktoken
            self._tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            self._tiktoken_encoder = False
    
    def count_tokens(self, text: str, model: Optional[str] = None) -> int:
        self._load_tiktoken()
        
        if self._tiktoken_encoder and model:
            try:
                import tiktoken
                encoding = tiktoken.encoding_for_model(model)
                return len(encoding.encode(text))
            except Exception:
                pass
        
        if self._tiktoken_encoder:
            return len(self._tiktoken_encoder.encode(text))
        
        return self._estimate_tokens(text)
    
    def _estimate_tokens(self, text: str) -> int:
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        other_chars = len(text) - chinese_chars
        
        tokens_from_chinese = chinese_chars / self.AVG_CHARS_PER_TOKEN_ZH
        tokens_from_other = other_chars / self.AVG_CHARS_PER_TOKEN_EN
        
        return int(tokens_from_chinese + tokens_from_other) + 1
    
    def count_messages_tokens(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            total += 4
            total += self.count_tokens(msg.get('content', ''))
            total += self.count_tokens(msg.get('role', ''))
        
        total += 2
        return total
    
    def estimate_max_output_tokens(self, context_tokens: int, model_limit: int = 4096) -> int:
        available = model_limit - context_tokens - 100
        return max(100, min(available, 2000))
