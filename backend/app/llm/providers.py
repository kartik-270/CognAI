import logging
import hashlib
from typing import List, Optional
from app.core.config import settings
from app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

_embedding_model = None

def get_embedding_model():
    """Lazily load BAAI/bge-m3 model so module imports remain fast."""
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            # Strictly using BAAI/bge-m3 for 1024-dim dense vectors as per constraints
            _embedding_model = SentenceTransformer("BAAI/bge-m3")
        except ImportError:
            _embedding_model = "MOCK"
    return _embedding_model


class GroqProvider(BaseLLMProvider):
    def __init__(self, model_name="qwen/qwen3.8-27b"):
        self.model_name = model_name
        self._llm = None

    def _get_client(self):
        if self._llm is None:
            try:
                from langchain_groq import ChatGroq
                self._llm = ChatGroq(
                    api_key=settings.GROQ_API_KEY or "dummy_key",
                    model_name=self.model_name,
                    max_retries=20
                )
            except ImportError:
                raise RuntimeError("langchain_groq is not installed in the current environment.")
        return self._llm
        
    def _prepare_payload(self, prompt: str, images: Optional[List[str]] = None):
        if not images:
            return prompt
        from langchain_core.messages import HumanMessage
        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": img}
            })
        return [HumanMessage(content=content)]
        
    async def generate(self, prompt: str, images: Optional[List[str]] = None, **kwargs) -> str:
        client = self._get_client()
        payload = self._prepare_payload(prompt, images or kwargs.get("images"))
        response = await client.ainvoke(payload)
        content = response.content
        if isinstance(content, list):
            content = " ".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
        return str(content)
        
    async def astream(self, prompt: str, images: Optional[List[str]] = None, **kwargs):
        client = self._get_client()
        payload = self._prepare_payload(prompt, images or kwargs.get("images"))
        try:
            async for chunk in client.astream(payload):
                content = chunk.content
                if isinstance(content, list):
                    content = " ".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
                if content:
                    yield str(content)
        except Exception as e:
            logger.warning(f"GroqProvider astream error: {e}. Falling back to generate().")
            yield await self.generate(prompt, images=images, **kwargs)

    async def get_embeddings(self, text: str) -> list[float]:
        raise NotImplementedError("Groq endpoint is reserved strictly for real-time chat latency, not embeddings.")

class AWSBedrockProvider(BaseLLMProvider):
    def __init__(self):
        super().__init__()
        import os
        self.model_name = settings.AWS_BEDROCK_MODEL
        self.vision_model_name = os.environ.get("AWS_BEDROCK_VISION_MODEL", "qwen.qwen3-vl-235b-a22b")

    def _prepare_payload(self, prompt: str, images: Optional[List[str]] = None):
        if not images:
            return prompt
        from langchain_core.messages import HumanMessage
        content = [{"type": "text", "text": prompt}]
        for img in images:
            content.append({
                "type": "image_url",
                "image_url": {"url": img}
            })
        return [HumanMessage(content=content)]

    async def generate(self, prompt: str, images: Optional[List[str]] = None, **kwargs) -> str:
        img_list = images or kwargs.get("images")
        model = self.vision_model_name if img_list else self.model_name
        client = self._get_client(model)
        payload = self._prepare_payload(prompt, img_list)
        response = await client.ainvoke(payload)
        content = response.content
        if isinstance(content, list):
            content = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
        return str(content)

    async def astream(self, prompt: str, images: Optional[List[str]] = None, **kwargs):
        img_list = images or kwargs.get("images")
        model = self.vision_model_name if img_list else self.model_name
        client = self._get_client(model)
        payload = self._prepare_payload(prompt, img_list)
        try:
            async for chunk in client.astream(payload):
                content = chunk.content
                if isinstance(content, list):
                    content = "".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
                if content:
                    yield str(content)
        except Exception as e:
            logger.warning(f"AWSBedrockProvider astream error: {e}. Falling back to generate().")
            yield await self.generate(prompt, images=images, **kwargs)

    def _get_client(self, model: str):
        from langchain_aws import ChatBedrock
        import os
        
        return ChatBedrock(
            model_id=model,
            region_name=settings.AWS_REGION,
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            model_kwargs={"temperature": 0.0}
        )

    async def get_embeddings(self, text: str) -> list[float]:
        raise NotImplementedError("Embeddings not configured for Bedrock yet.")


class GeminiProvider(BaseLLMProvider):
    def __init__(self, model_name="gemma-4-26b-a4b-it"):
        self.model_name = model_name
        self._llm = None

    def _get_client(self, model: Optional[str] = None):
        target_model = model or self.model_name
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                api_key=settings.GEMINI_API_KEY or "dummy_key",
                model=target_model,
                max_retries=5,
                request_timeout=30.0
            )
        except ImportError:
            raise RuntimeError("langchain_google_genai is not installed in the current environment.")
        
    async def generate(self, prompt: str, **kwargs) -> str:
        try:
            client = self._get_client(self.model_name)
            response = await client.ainvoke(prompt)
        except Exception as e:
            logger.warning(f"GeminiProvider failed with {self.model_name}: {e}. Retrying with gemma-4-26b-a4b-it...")
            client = self._get_client("gemma-4-26b-a4b-it")
            response = await client.ainvoke(prompt)

        content = response.content
        if isinstance(content, list):
            content = " ".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
        return str(content)

    async def astream(self, prompt: str, **kwargs):
        try:
            client = self._get_client(self.model_name)
            async for chunk in client.astream(prompt):
                content = chunk.content
                if isinstance(content, list):
                    content = " ".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
                if content:
                    yield str(content)
        except Exception as e:
            logger.warning(f"GeminiProvider astream failed with {self.model_name}: {e}. Retrying with gemma-4-26b-a4b-it...")
            try:
                client = self._get_client("gemma-4-26b-a4b-it")
                async for chunk in client.astream(prompt):
                    content = chunk.content
                    if isinstance(content, list):
                        content = " ".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
                    if content:
                        yield str(content)
            except Exception as e2:
                logger.error(f"Fallback generation error: {e2}")
                yield await self.generate(prompt, **kwargs)

    async def get_embeddings(self, text: str) -> list[float]:
        # Generating 1024-dim vector using bge-m3 locally
        model = get_embedding_model()
        if model != "MOCK":
            vector = model.encode(text, normalize_embeddings=True)
            return vector.tolist()
        else:
            # Deterministic 1024-dim fallback for offline unit testing without torch/bge-m3
            h = hashlib.sha256(text.encode()).digest()
            # Repeat hash to fill 1024 floats
            vals = []
            for i in range(1024):
                vals.append(float(h[i % len(h)]) / 255.0)
            norm = sum(v * v for v in vals) ** 0.5
            return [v / norm for v in vals]



class CloudflareProvider(BaseLLMProvider):
    def __init__(self, model_name=None):
        self.model_name = model_name or settings.CLOUDFLARE_MODEL
        self._llm = None

    def _get_client(self):
        if self._llm is None:
            try:
                from langchain_openai import ChatOpenAI
                self._llm = ChatOpenAI(
                    api_key=settings.CLOUDFLARE_API_TOKEN,
                    base_url=f"https://api.cloudflare.com/client/v4/accounts/{settings.CLOUDFLARE_ACCOUNT_ID}/ai/v1",
                    model=self.model_name,
                    max_retries=5
                )
            except ImportError:
                raise RuntimeError("langchain_openai is not installed.")
        return self._llm
        
    async def generate(self, prompt: str, **kwargs) -> str:
        client = self._get_client()
        response = await client.ainvoke(prompt)
        content = response.content
        if isinstance(content, list):
            content = " ".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
        return str(content)

    async def astream(self, prompt: str, **kwargs):
        client = self._get_client()
        try:
            async for chunk in client.astream(prompt):
                content = chunk.content
                if isinstance(content, list):
                    content = " ".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
                if content:
                    yield str(content)
        except Exception as e:
            logger.warning(f"CloudflareProvider astream error: {e}. Falling back to generate().")
            yield await self.generate(prompt, **kwargs)

    async def get_embeddings(self, text: str) -> list[float]:
        raise NotImplementedError("CloudflareProvider is used for chat latency, not embeddings.")
