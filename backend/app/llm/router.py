from typing import Optional, List
from app.llm.providers import GroqProvider, GeminiProvider

class LLMRouter:
    def __init__(self):
        import os
        from app.core.config import settings

        # AI Provider Selection
        chosen_provider = (settings.LLM_PROVIDER or "").lower()
        if chosen_provider == "bedrock" and (os.environ.get("AWS_ACCESS_KEY_ID") or settings.AWS_BEDROCK_API_KEY):
            from app.llm.providers import AWSBedrockProvider
            self.chat_provider = AWSBedrockProvider()
        elif settings.GROQ_API_KEY and chosen_provider != "bedrock":
            self.chat_provider = GroqProvider()
        elif os.environ.get("AWS_ACCESS_KEY_ID") or settings.AWS_BEDROCK_API_KEY:
            from app.llm.providers import AWSBedrockProvider
            self.chat_provider = AWSBedrockProvider()
        elif settings.CLOUDFLARE_API_TOKEN:
            from app.llm.providers import CloudflareProvider
            self.chat_provider = CloudflareProvider()
        else:
            self.chat_provider = GeminiProvider() 

        # Background tasks (Gemini 2.0 Flash / Qwen 2.5 / Bedrock)
        if os.environ.get("AWS_ACCESS_KEY_ID"):
            from app.llm.providers import AWSBedrockProvider
            self.background_provider = AWSBedrockProvider()
        elif settings.GEMINI_API_KEY:
            self.background_provider = GeminiProvider()
        elif settings.CLOUDFLARE_API_TOKEN:
            from app.llm.providers import CloudflareProvider
            self.background_provider = CloudflareProvider()
        else:
            self.background_provider = self.chat_provider
        
    async def chat(self, prompt: str, images: Optional[list[str]] = None) -> str:
        """Route to low-latency Groq for real-time user interactions."""
        return await self.chat_provider.generate(prompt, images=images)

    async def chat_stream(self, prompt: str, images: Optional[list[str]] = None):
        """Route to low-latency streaming chat provider."""
        if hasattr(self.chat_provider, "astream"):
            async for chunk in self.chat_provider.astream(prompt, images=images):
                yield chunk
        else:
            yield await self.chat(prompt, images=images)
        
    async def background_task(self, prompt: str, images: Optional[list[str]] = None) -> str:
        """Route to Gemini/Qwen for background tasks to protect API rate limits."""
        return await self.background_provider.generate(prompt, images=images)

    async def background_stream(self, prompt: str, images: Optional[list[str]] = None):
        """Route to background task streaming provider."""
        if hasattr(self.background_provider, "astream"):
            async for chunk in self.background_provider.astream(prompt, images=images):
                yield chunk
        else:
            yield await self.background_task(prompt, images=images)

    async def embed(self, text: str) -> list[float]:
        """Returns 1024-dimensional bge-m3 embeddings locally."""
        from app.llm.providers import get_embedding_model
        import hashlib
        model = get_embedding_model()
        if model != "MOCK":
            vector = model.encode(text, normalize_embeddings=True)
            return vector.tolist()
        else:
            h = hashlib.sha256(text.encode()).digest()
            return [float(b) / 255.0 for b in h * 32]

llm_router = LLMRouter()
