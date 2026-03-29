import os
from pathlib import Path
from typing import Optional
import yaml

from src.utils.logger import Log


class PromptManager:
    def __init__(self, template_dir: Optional[str] = None):
        if template_dir is None:
            template_dir = os.path.join(os.path.dirname(__file__), "..", "..", "config", "prompts")
        self.template_dir = Path(template_dir)
        self._cache: dict[str, dict] = {}
    
    def load_template(self, name: str) -> dict:
        if name in self._cache:
            return self._cache[name]
        
        template_path = self.template_dir / f"{name}.yaml"
        
        if not template_path.exists():
            Log.warning(f"Template not found: {name}")
            return {"system": "", "user": "", "constraints": []}
        
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template = yaml.safe_load(f)
            self._cache[name] = template
            return template
        except Exception as e:
            Log.error(f"Failed to load template {name}", e)
            return {"system": "", "user": "", "constraints": []}
    
    def render(
        self, 
        name: str, 
        instruction: str = "",
        text: str = "",
        context: str = "",
        **kwargs
    ) -> tuple[str, str]:
        template = self.load_template(name)
        
        system_prompt = template.get("system", "")
        
        user_prompt = template.get("user", "")
        user_prompt = user_prompt.replace("{{ instruction }}", instruction)
        user_prompt = user_prompt.replace("{{ text }}", text)
        user_prompt = user_prompt.replace("{{ context }}", context)
        
        for key, value in kwargs.items():
            user_prompt = user_prompt.replace(f"{{{{ {key} }}}}", str(value))
        
        return system_prompt, user_prompt
    
    def render_writer(self, text: str, instruction: str, context: str = "") -> tuple[str, str]:
        return self.render("writer", instruction=instruction, text=text, context=context)
    
    def render_reviewer(
        self, 
        original_text: str, 
        rewritten_text: str, 
        instruction: str = ""
    ) -> tuple[str, str]:
        return self.render(
            "reviewer",
            instruction=instruction,
            original_text=original_text,
            text=rewritten_text,
        )
    
    def render_analyzer(
        self, 
        text: str, 
        instruction: str = "",
        characters: str = "",
        plot_summary: str = ""
    ) -> tuple[str, str]:
        return self.render(
            "analyzer",
            instruction=instruction,
            text=text,
            characters=characters,
            plot_summary=plot_summary,
        )
    
    def render_chat(
        self, 
        question: str, 
        chapter_content: str = "",
        context: str = ""
    ) -> tuple[str, str]:
        return self.render(
            "chat",
            question=question,
            chapter_content=chapter_content,
            context=context,
        )
    
    def render_graph(self, text: str, known_entities: str = "") -> tuple[str, str]:
        return self.render(
            "graph",
            text=text,
            known_entities=known_entities,
        )
    
    def get_constraints(self, name: str) -> list[str]:
        template = self.load_template(name)
        return template.get("constraints", [])
    
    def clear_cache(self) -> None:
        self._cache.clear()


prompt_manager = PromptManager()
