# services/ai_async_client.py
import os
import httpx
import asyncio
from typing import List, Dict, Optional, Any, AsyncGenerator

class AIAsyncClient:
    def __init__(self, config: dict):
        self.config = config
        self._client = httpx.AsyncClient(timeout=60)

    # ----------- Single request for all providers -----------
    async def ask_openai(self, prompt: str, model: Optional[str] = None, stream: bool = False):
        url = self.config["openai"]["endpoint"] + "/chat/completions"
        api_key = self.config["openai"]["api_key"]
        model = model or self.config["openai"]["model"]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        data = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": stream}
        if stream:
            async with self._client.stream("POST", url, headers=headers, json=data) as resp:
                async for chunk in resp.aiter_lines():
                    if chunk.strip():
                        yield chunk
        else:
            resp = await self._client.post(url, headers=headers, json=data)
            resp.raise_for_status()
            result = resp.json()
            return result["choices"][0]["message"]["content"]

    async def ask_moonshot(self, prompt: str, model: Optional[str]=None, stream: bool = False):
        url = self.config["moonshot"]["endpoint"]
        api_key = self.config["moonshot"]["api_key"]
        model = model or self.config["moonshot"]["model"]
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        data = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": stream}
        if stream:
            async with self._client.stream("POST", url, headers=headers, json=data) as resp:
                async for chunk in resp.aiter_lines():
                    if chunk.strip():
                        yield chunk
        else:
            resp = await self._client.post(url, headers=headers, json=data)
            resp.raise_for_status()
            result = resp.json()
            # По Moonshot — уточните структуру ответа!
            return result["choices"][0]["message"]["content"]

    # ... реализуйте остальные провайдеры по аналогии ...

    # ----------- Batch for all providers (asyncio.gather) -----------
    async def batch(self, prompts: List[str], provider: str = "openai", stream: bool = False) -> List[str]:
        if stream:
            raise NotImplementedError("Batch streaming is not supported")
        method = getattr(self, f"ask_{provider}")
        results = await asyncio.gather(*(method(prompt, stream=False) for prompt in prompts))
        return results

    # ----------- Stream for all providers (as async generator) -----------
    async def stream(self, prompt: str, provider: str = "openai") -> AsyncGenerator[str, None]:
        method = getattr(self, f"ask_{provider}")
        async for chunk in method(prompt, stream=True):
            yield chunk

    async def ask(self, prompt: str, provider: str = "openai", stream: bool = False):
        method = getattr(self, f"ask_{provider}")
        return await method(prompt, stream=stream)

    async def aclose(self):
        await self._client.aclose()