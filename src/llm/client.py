"""
LLM client for OpenAI-compatible APIs (Z.AI/GLM and HF Router).
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


# Z.AI / GLM: set LLM_BASE_URL + LLM_API_KEY to use glm-4.7-flash etc.
LLM_BASE_URL = os.getenv("LLM_BASE_URL")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "glm-4.7-flash")

# HF Router (for tutor chat)
HF_ROUTER_BASE_URL = os.getenv("HF_ROUTER_BASE_URL", "https://router.huggingface.co/v1")
HF_ROUTER_API_KEY = os.getenv("HF_ROUTER_API_KEY") or os.getenv("HF_TOKEN")
HF_ROUTER_MODEL = os.getenv("HF_ROUTER_MODEL", "MiniMaxAI/MiniMax-M2.7:fireworks-ai")

logger = logging.getLogger(__name__)


class LLMClient:
    """OpenAI-compatible chat client (Z.AI/GLM, HF Router, etc.)."""

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

        self.model_name = model_name or LLM_MODEL
        self.base_url = base_url or (LLM_BASE_URL or "")
        api_key = api_token or (LLM_API_KEY or "")

        if not self.base_url or not api_key:
            raise ValueError(
                "API base_url and key required. Set LLM_BASE_URL + LLM_API_KEY (for Z.AI) "
                "or pass them explicitly."
            )
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=api_key,
            timeout=60.0,
            max_retries=2,
        )

    def generate_single(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[List[str]] = None,
        max_retries: int = 3,
        response_format: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> str:
        """Generate text for a single prompt."""
        results = self.generate(
            [prompt], max_tokens, temperature, top_p, stop, max_retries, response_format, timeout
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
        timeout: Optional[float] = None,
    ) -> List[str]:
        """Generate text for a batch of prompts with rate limiting."""
        results = []
        for i, prompt in enumerate(prompts):
            retry_count = 0
            while retry_count < max_retries:
                try:
                    # Z.AI supports only one stop word; pass at most one
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
                    if timeout is not None:
                        create_kw["timeout"] = timeout

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
                            time.sleep(10 + random.uniform(0, 5))
                            break
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
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LLMClient:
    """Create a Z.AI/GLM client from env vars or explicit args."""
    return LLMClient(
        model_name=model_name,
        api_token=api_key,
        base_url=base_url,
    )


def create_tutor_client(
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> LLMClient:
    """Create an HF Router client for the tutor chat."""
    key = api_key or HF_ROUTER_API_KEY
    url = base_url or HF_ROUTER_BASE_URL
    model = model_name or HF_ROUTER_MODEL
    if not key:
        raise ValueError(
            "HF Router API key required. Set HF_ROUTER_API_KEY or HF_TOKEN env var."
        )
    return LLMClient(
        model_name=model,
        api_token=key,
        base_url=url,
    )
