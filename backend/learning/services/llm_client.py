from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

import requests
from django.conf import settings
from dotenv import dotenv_values

from app.debug_logger import debug_log


class LLMClientError(Exception):
    pass


class LLMAuthError(LLMClientError):
    pass


@dataclass
class ChatMessage:
    role: str
    content: Any


class OpenAICompatibleClient:
    # 初始化当前对象需要的依赖和运行参数。
    def __init__(self):
        self.base_url = str(settings.OPENAI_BASE_URL or "").strip().rstrip("/")
        self.api_key = str(settings.OPENAI_API_KEY or "").strip()
        self.model = str(settings.OPENAI_MODEL or "").strip()
        self.max_retries = max(int(getattr(settings, "LLM_REQUEST_MAX_RETRIES", 2) or 1), 1)
        self.base_retry_delay = max(float(getattr(settings, "LLM_REQUEST_RETRY_BASE_DELAY", 0.2) or 0.1), 0.1)
        default_timeout = 180 if self._is_local_ollama_endpoint(self.base_url) else 60
        self.request_timeout_seconds = max(float(getattr(settings, "LLM_REQUEST_TIMEOUT_SECONDS", default_timeout) or 5), 5)
        if self._is_local_ollama_endpoint(self.base_url):
            # Local VLM inference can be much slower than cloud API.
            self.request_timeout_seconds = max(self.request_timeout_seconds, 120.0)

    @staticmethod
    # 实现状态和进度计算，为前端展示提供一致的任务信息。
    def _is_retryable_status(status_code: int | None) -> bool:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    @staticmethod
    # 实现 _safe_text 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _safe_text(value: object, max_len: int = 500) -> str:
        return str(value or "")[:max_len]

    @staticmethod
    # 实现 _serialize_content 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _serialize_content(content: Any) -> Any:
        if isinstance(content, (str, list, dict)):
            return content
        return str(content or "")

    @staticmethod
    # 实现 _is_local_ollama_endpoint 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _is_local_ollama_endpoint(base_url: str) -> bool:
        value = str(base_url or "").strip().lower()
        return "localhost:11434" in value or "127.0.0.1:11434" in value

    # 实现 _reload_from_dotenv 对应的核心处理，封装输入转换、状态更新或结果返回。
    def _reload_from_dotenv(self) -> bool:
        # 运行期重新读取 .env，方便切换本地 Ollama/云端模型或更新 key 后立刻生效。
        changed = False
        env_path = Path(getattr(settings, "BASE_DIR", Path("."))) / ".env"
        if not env_path.exists():
            return False
        values = dotenv_values(str(env_path))

        use_local = str(values.get("USE_LOCAL_LLM") or "").strip().lower() in {"1", "true", "yes", "on"}
        if use_local:
            raw_base_url = str(values.get("OLLAMA_BASE_URL") or values.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
            raw_api_key = str(values.get("OLLAMA_API_KEY") or values.get("OPENAI_API_KEY") or "ollama").strip()
            raw_model = str(values.get("OLLAMA_MODEL") or values.get("OPENAI_MODEL") or "").strip()
        else:
            raw_base_url = str(values.get("OPENAI_BASE_URL") or "").strip().rstrip("/")
            raw_api_key = str(values.get("OPENAI_API_KEY") or "").strip()
            raw_model = str(values.get("OPENAI_MODEL") or "").strip()

        raw_retries = values.get("LLM_REQUEST_MAX_RETRIES")
        raw_retry_delay = values.get("LLM_REQUEST_RETRY_BASE_DELAY")
        raw_timeout = values.get("LLM_REQUEST_TIMEOUT_SECONDS")

        if raw_base_url and raw_base_url != self.base_url:
            self.base_url = raw_base_url
            changed = True
        if raw_api_key and raw_api_key != self.api_key:
            self.api_key = raw_api_key
            changed = True
        if raw_model and raw_model != self.model:
            self.model = raw_model
            changed = True

        if raw_retries not in {None, ""}:
            try:
                retries = max(int(raw_retries or 1), 1)
                if retries != self.max_retries:
                    self.max_retries = retries
                    changed = True
            except Exception:
                pass

        if raw_retry_delay not in {None, ""}:
            try:
                retry_delay = max(float(raw_retry_delay or 0.1), 0.1)
                if retry_delay != self.base_retry_delay:
                    self.base_retry_delay = retry_delay
                    changed = True
            except Exception:
                pass

        timeout_candidate = self.request_timeout_seconds
        if raw_timeout not in {None, ""}:
            try:
                timeout_candidate = max(float(raw_timeout or 5), 5)
            except Exception:
                pass
        if self._is_local_ollama_endpoint(self.base_url):
            # 本地模型首 token 和视觉模型耗时通常更长，单独放宽超时，避免大课件 OCR 时误判失败。
            timeout_candidate = max(timeout_candidate, 120.0)
        if timeout_candidate != self.request_timeout_seconds:
            self.request_timeout_seconds = timeout_candidate
            changed = True
        return changed

    # 实现 chat 对应的核心处理，封装输入转换、状态更新或结果返回。
    def chat(self, messages: list[ChatMessage], temperature: float = 0.2, _allow_auth_retry: bool = True) -> str:
        # Pull latest local runtime config on each call, so .env tuning can take effect
        # immediately without requiring a Django restart.
        self._reload_from_dotenv()

        is_local_ollama = self._is_local_ollama_endpoint(self.base_url)
        if not self.api_key:
            if is_local_ollama:
                self.api_key = "ollama"
            else:
                #region agent log H2_llm_api_key_empty
                debug_log(
                    hypothesisId="H2",
                    runId="pre-diagnose",
                    location="llm_client:chat",
                    message="OPENAI_API_KEY is empty",
                    data={"base_url": self.base_url, "model": self.model},
                )
                #endregion
                raise LLMClientError("OPENAI_API_KEY is empty. Please configure environment variables.")

        endpoint = f"{self.base_url}/chat/completions"
        request_timeout: float | tuple[float, float]
        if is_local_ollama:
            request_timeout = (10.0, float(self.request_timeout_seconds))
        else:
            request_timeout = float(self.request_timeout_seconds)
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": self._serialize_content(m.content)} for m in messages],
            "temperature": temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=request_timeout,
                )
                response.raise_for_status()
                body = response.json()
                return body["choices"][0]["message"]["content"].strip()
            except requests.RequestException as exc:
                last_exc = exc
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                body_head = self._safe_text(getattr(getattr(exc, "response", None), "text", ""))

                if status_code == 401 and _allow_auth_retry:
                    updated = self._reload_from_dotenv()
                    debug_log(
                        hypothesisId="H2",
                        runId="pre-diagnose",
                        location="llm_client:chat",
                        message="Received 401 from LLM provider, retrying once after dotenv refresh",
                        data={
                            "endpoint": endpoint,
                            "model": self.model,
                            "dotenv_refreshed": bool(updated),
                            "status_code": status_code,
                            "response_head": body_head,
                        },
                    )
                    return self.chat(messages, temperature=temperature, _allow_auth_retry=False)

                should_retry = (
                    # 只重试网络抖动、限流和服务端临时错误；认证错误会走专门的刷新逻辑，避免盲目重试。
                    attempt < self.max_retries
                    and (
                        self._is_retryable_status(status_code)
                        or isinstance(exc, (requests.Timeout, requests.ConnectionError))
                    )
                )
                if should_retry:
                    delay = self.base_retry_delay * (2 ** (attempt - 1))
                    debug_log(
                        hypothesisId="H2",
                        runId="pre-diagnose",
                        location="llm_client:chat",
                        message="LLM request transient failure, retrying",
                        data={
                            "endpoint": endpoint,
                            "model": self.model,
                            "attempt": attempt,
                            "max_retries": self.max_retries,
                            "status_code": status_code,
                            "delay_seconds": round(delay, 2),
                            "exc_type": type(exc).__name__,
                            "error": str(exc)[:260],
                        },
                    )
                    time.sleep(delay)
                    continue

                #region agent log H2_llm_request_exception
                debug_log(
                    hypothesisId="H2",
                    runId="pre-diagnose",
                    location="llm_client:chat",
                    message="LLM request failed",
                    data={
                        "exc_type": type(exc).__name__,
                        "error": str(exc)[:500],
                        "endpoint": endpoint,
                        "model": self.model,
                        "status_code": status_code,
                        "response_head": body_head,
                    },
                )
                #endregion
                if status_code == 401:
                    raise LLMAuthError(f"LLM unauthorized (401): {exc}") from exc
                raise LLMClientError(f"LLM request failed: {exc}") from exc
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                #region agent log H5_llm_response_format_exception
                debug_log(
                    hypothesisId="H5",
                    runId="pre-diagnose",
                    location="llm_client:chat",
                    message="Unexpected LLM response format",
                    data={"exc_type": type(exc).__name__, "error": str(exc)[:500], "endpoint": endpoint},
                )
                #endregion
                raise LLMClientError(f"Unexpected LLM response format: {exc}") from exc
        if last_exc is not None:
            raise LLMClientError(f"LLM request failed after retries: {last_exc}") from last_exc
        raise LLMClientError("LLM request failed: unknown error")
