"""
LLM client for OpenAI-compatible APIs (ModelScope, Z.AI/GLM, DeepSeek, etc.).
"""

from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path
from typing import Iterator, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

# Load .env file if it exists
if load_dotenv is not None:
    project_root = Path(__file__).resolve().parents[2]
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)


# Z.AI / GLM (optional): set LLM_BASE_URL + LLM_API_KEY to use GLM-4.7-flash etc.
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "glm-4.7-flash")

# ModelScope fallback
DEFAULT_MODELSCOPE_MODEL = os.getenv("MODELSCOPE_MODEL", "deepseek-ai/DeepSeek-R1-0528")
DEFAULT_MODELSCOPE_BASE_URL = "https://api-inference.modelscope.ai/v1"

logger = logging.getLogger(__name__)


def _resolve_client_params(
    model_name: Optional[str] = None,
    api_token: Optional[str] = None,
    base_url: Optional[str] = None,
) -> tuple[str, str, str]:
    """Resolve model, api_key, base_url from args or env (Z.AI when set, else ModelScope)."""
    use_zai = (LLM_BASE_URL and LLM_API_KEY) or (base_url and api_token)
    if use_zai:
        base = base_url or LLM_BASE_URL or ""
        key = api_token or LLM_API_KEY or ""
        model = model_name or LLM_MODEL
        if base and key:
            return model, key, base
    # ModelScope
    key = api_token or os.getenv("MODELSCOPE_API_TOKEN")
    base = base_url or os.getenv("MODELSCOPE_API_URL", DEFAULT_MODELSCOPE_BASE_URL)
    model = model_name or DEFAULT_MODELSCOPE_MODEL
    return model, key or "", base


class ModelScopeClient:
    """OpenAI-compatible chat client (ModelScope, Z.AI/GLM, DeepSeek, etc.)."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_token: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        if OpenAI is None:
            raise ImportError(
                "openai not installed. Install with: uv pip install openai"
            )

        self.model_name, api_key, self.base_url = _resolve_client_params(
            model_name=model_name, api_token=api_token, base_url=base_url
        )
        if not api_key:
            raise ValueError(
                "API key required. Set LLM_API_KEY (for Z.AI) or MODELSCOPE_API_TOKEN (for ModelScope)."
            )
        self.client = OpenAI(base_url=self.base_url, api_key=api_key)

    def generate_single(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
        max_retries: int = 3,
        response_format: Optional[dict] = None,
    ) -> str:
        """Generate text for a single prompt."""
        results = self.generate(
            [prompt], max_tokens, temperature, top_p, stop, max_retries, response_format
        )
        return results[0] if results else ""

    def generate(
        self,
        prompts: List[str],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
        max_retries: int = 3,
        response_format: Optional[dict] = None,
    ) -> List[str]:
        """Generate text for a batch of prompts with rate limiting."""
        results = []
        for i, prompt in enumerate(prompts):
            retry_count = 0
            while retry_count < max_retries:
                try:
                    # Z.AI supports only one stop word; pass at most one to avoid empty/invalid response
                    stop_param = stop[:1] if stop else None
                    create_kw: dict = {
                        "model": self.model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "top_p": top_p,
                        "stop": stop_param,
                    }
                    if response_format is not None:
                        create_kw["response_format"] = response_format
                    # Z.AI: disable thinking so the model returns directly in content
                    if "z.ai" in self.base_url.lower():
                        create_kw["extra_body"] = {"thinking": {"type": "disabled"}}

                    response = self.client.chat.completions.create(**create_kw)

                    if response.choices and len(response.choices) > 0:
                        msg = response.choices[0].message
                        generated_text = msg.content or ""
                        # Z.AI may put output in reasoning_content when thinking is enabled
                        if not generated_text.strip() and getattr(
                            msg, "reasoning_content", None
                        ):
                            generated_text = (msg.reasoning_content or "").strip()
                        if not generated_text.strip():
                            logger.warning(
                                "Empty content in response for prompt %s (finish_reason=%s)",
                                i + 1,
                                getattr(response.choices[0], "finish_reason", "?"),
                            )
                        results.append(generated_text.strip())
                    else:
                        logger.warning("Empty response from API for prompt %s", i + 1)
                        results.append("")

                    break

                except Exception as e:
                    error_str = str(e)
                    # Check for rate limit errors
                    if (
                        "429" in error_str
                        or "concurrency" in error_str.lower()
                        or "1302" in error_str
                    ):
                        retry_count += 1
                        if retry_count >= max_retries:
                            logger.warning(
                                "Rate limit exceeded after %s retries. Skipping prompt.",
                                max_retries,
                            )
                            results.append("")
                            # Longer delay before continuing to next prompt
                            time.sleep(10 + random.uniform(0, 5))
                            break
                        # Exponential backoff with jitter for concurrency limits
                        backoff = (2**retry_count) * 3 + random.uniform(0, 3)
                        logger.warning(
                            "Rate limit hit (429/concurrency). Retrying in %s s (attempt %s/%s)",
                            round(backoff, 1),
                            retry_count,
                            max_retries,
                        )
                        time.sleep(backoff)
                    else:
                        logger.error("Error calling API: %s", e)
                        results.append("")
                        time.sleep(2)
                        break

        return results

    def stream(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
    ) -> Iterator[str]:
        """Stream text generation for a single prompt."""
        stop_param = stop[:1] if stop else None
        stream_kw: dict = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stop": stop_param,
            "stream": True,
        }
        if "z.ai" in self.base_url.lower():
            stream_kw["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            response = self.client.chat.completions.create(**stream_kw)

            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error("Error streaming from API: %s", e)
            yield ""


def create_client(
    model_name: Optional[str] = None,
    modelscope_token: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> ModelScopeClient:
    """Create an OpenAI-compatible client (Z.AI/GLM, ModelScope, etc.)."""
    return ModelScopeClient(
        model_name=model_name,
        api_token=modelscope_token or api_key,
        base_url=base_url,
    )
