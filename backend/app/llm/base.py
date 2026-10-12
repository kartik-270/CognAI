from abc import ABC, abstractmethod
from typing import AsyncIterator

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generates a text response from the LLM"""
        pass
        
    async def astream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Streams text response chunks from the LLM. Default fallback yields full text."""
        result = await self.generate(prompt, **kwargs)
        yield result

    @abstractmethod
    async def get_embeddings(self, text: str) -> list[float]:
        """Returns 1024-dimensional embeddings (bge-m3)"""
        pass

