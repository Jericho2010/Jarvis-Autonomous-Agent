import os
import logging
from typing import Any, AsyncIterable, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence
from pathlib import Path

from agent_framework import Agent, FunctionMiddleware, FunctionInvocationContext
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework._clients import BaseChatClient
from agent_framework._types import ChatResponse, ChatResponseUpdate, Message, ResponseStream
from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger("jarvis.agent")
console = Console()

DEFAULT_FALLBACK_LADDER = [
    "deepseek-ai/deepseek-r1",
    "deepseek-ai/deepseek-coder",
    "qwen/qwen2.5-72b-instruct",
    "meta/llama-3.3-70b-instruct",
    "microsoft/phi-4"
]

class ToolTelemetryMiddleware(FunctionMiddleware):
    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        func_name = context.function.name
        args = str(context.arguments)
        
        console.print(f"\n[bold cyan]🔧 Executing Tool:[/] [yellow]{func_name}[/] with arguments: [dim]{args}[/]")
        
        try:
            await call_next()
            res = str(context.result)
            if len(res) > 500:
                res_disp = res[:500] + "\n... (truncated)"
            else:
                res_disp = res
                
            console.print(Panel(
                res_disp,
                title=f"Tool Result: {func_name}",
                border_style="green",
                title_align="left",
                padding=(0, 1)
            ))
        except Exception as e:
            console.print(f"[bold red]❌ Tool execution failed:[/] {func_name} -> {e}")
            raise e

class TrinityNIMChatClient(BaseChatClient):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        fallback_ladder: Optional[List[str]] = None,
        **kwargs: Any
    ):
        super().__init__(**kwargs)
        self.api_key = api_key
        self.base_url = base_url
        self.fallback_ladder = fallback_ladder or DEFAULT_FALLBACK_LADDER
        self._clients: Dict[str, OpenAIChatCompletionClient] = {}

    def _get_client(self, model: str) -> OpenAIChatCompletionClient:
        if model not in self._clients:
            self._clients[model] = OpenAIChatCompletionClient(
                model=model,
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._clients[model]

    def _inner_get_response(
        self,
        *,
        messages: Sequence[Message],
        stream: bool,
        options: Mapping[str, Any],
        **kwargs: Any
    ) -> Awaitable[ChatResponse] | ResponseStream[ChatResponseUpdate, ChatResponse]:
        if stream:
            return self._build_response_stream(
                self._stream_with_fallback(messages, options, **kwargs)
            )
        else:
            return self._get_response_with_fallback(messages, options, **kwargs)

    async def _get_response_with_fallback(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any
    ) -> ChatResponse:
        last_exception = None
        for model in self.fallback_ladder:
            try:
                client = self._get_client(model)
                logger.info(f"Trinity Council // Attempting turn with model: {model}")
                opt_copy = dict(options)
                opt_copy["model"] = model
                
                if "deepseek-r1" in model:
                    opt_copy.pop("temperature", None)
                    opt_copy.pop("top_p", None)
                    
                response = await client.get_response(messages=messages, options=opt_copy, **kwargs)
                return response
            except Exception as e:
                logger.warning(f"Trinity Council // Model {model} failed: {e}. Falling back...")
                last_exception = e
        
        raise RuntimeError(f"All Trinity Council models failed. Last exception: {last_exception}")

    async def _stream_with_fallback(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any
    ) -> AsyncIterable[ChatResponseUpdate]:
        last_exception = None
        for model in self.fallback_ladder:
            try:
                client = self._get_client(model)
                logger.info(f"Trinity Council // Attempting streaming turn with model: {model}")
                opt_copy = dict(options)
                opt_copy["model"] = model
                
                if "deepseek-r1" in model:
                    opt_copy.pop("temperature", None)
                    opt_copy.pop("top_p", None)
                
                stream = await client.get_response(messages=messages, stream=True, options=opt_copy, **kwargs)
                
                async for chunk in stream:
                    yield chunk
                return
            except Exception as e:
                logger.warning(f"Trinity Council // Streaming model {model} failed: {e}. Falling back...")
                last_exception = e
                
        raise RuntimeError(f"All Trinity Council streaming models failed. Last exception: {last_exception}")


DEFAULT_SYSTEM_PROMPT = """You are JARVIS, a highly advanced artificial intellect, custom-built system co-designer, and assistant to Shaun.
You operate on a Linux Mint workstation (HP ZBook).
Your personality is collaborative, steady, and technically precise.
You prioritize code correctness, minimal code changes, and clean solutions.
You balance technological intelligence with quiet, moral depth.

Avoid generic pleasantries. Focus on high-density technical output.
"""

def create_jarvis_agent(
    api_key: str,
    instructions_override: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    fallback_ladder: Optional[List[str]] = None,
) -> Agent:
    """Creates a Microsoft Agent Framework Agent using Trinity Council fallback client and tool telemetry middleware."""
    client = TrinityNIMChatClient(api_key=api_key, fallback_ladder=fallback_ladder)
    
    agent = Agent(
        client=client,
        name="JARVIS",
        instructions=instructions_override or DEFAULT_SYSTEM_PROMPT,
        tools=tools or [],
        middleware=[ToolTelemetryMiddleware()],
    )
    return agent
