from typing import Optional
import httpx
import os

from .base import BaseEmbedder


class OpenAIEmbedder(BaseEmbedder):
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: Optional[str] = None,
        dimension: Optional[int] = None,
        proxy: Optional[str] = None,
    ):
        super().__init__(dimension)
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"
        
        if proxy and proxy.strip():
            os.environ['http_proxy'] = proxy
            os.environ['https_proxy'] = proxy
    
    def embed(self, texts: list[str]) -> list[list[float]]:
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "input": texts,
        }
        
        if self._dimension:
            payload["dimensions"] = self._dimension
        
        with httpx.Client(trust_env=True, timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        
        embeddings = [item["embedding"] for item in data["data"]]
        
        if self._dimension is None:
            self._dimension = len(embeddings[0])
        
        return embeddings
    
    def embed_query(self, query: str) -> list[float]:
        results = self.embed([query])
        return results[0]
