import os
import logging
import random
import asyncio
from typing import Any, AsyncIterable, Awaitable, Callable, Dict, List, Mapping, Optional, Sequence
from pathlib import Path

from agent_framework import Agent, FunctionMiddleware, FunctionInvocationContext
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework._clients import BaseChatClient
from agent_framework._tools import FunctionInvocationLayer
from agent_framework._types import ChatResponse, ChatResponseUpdate, Message, ResponseStream
from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger("jarvis.agent")
console = Console()

NIM_MODEL_BASKET = [
    "deepseek-ai/deepseek-v4-pro",
    "deepseek-ai/deepseek-v4-flash",
    "qwen/qwen3-coder-480b-a35b-instruct",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "moonshotai/kimi-k2.6",
    "stepfun-ai/step-3.7-flash",
    "mistralai/mistral-large-3-675b-instruct-2512"
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

class TrinityNIMChatClient(FunctionInvocationLayer, BaseChatClient):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model_basket: Optional[List[str]] = None,
        **kwargs: Any
    ):
        super().__init__(middleware=[ToolTelemetryMiddleware()], **kwargs)
        self.api_key = api_key
        self.base_url = base_url
        self.model_basket = model_basket or NIM_MODEL_BASKET
        self.primary_model = "dynamic"
        self._clients: Dict[str, OpenAIChatCompletionClient] = {}

    def _get_client(self, model: str) -> OpenAIChatCompletionClient:
        if model not in self._clients:
            self._clients[model] = OpenAIChatCompletionClient(
                model=model,
                api_key=self.api_key,
                base_url=self.base_url,
                function_invocation_configuration={"enabled": False},
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
        # FunctionInvocationLayer may pass additional kwargs (session, cancellation_token)
        # that the inner OpenAIChatCompletionClient does not accept. Sanitize here.
        kwargs.pop("session", None)
        kwargs.pop("cancellation_token", None)
        
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
        
        basket_pool = list(self.model_basket)
        trinity = []
        if self.primary_model != "dynamic" and self.primary_model in basket_pool:
            trinity.append(self.primary_model)
            basket_pool.remove(self.primary_model)
            trinity.extend(random.sample(basket_pool, 2))
        else:
            trinity = random.sample(basket_pool, 3)
            
        for model in trinity:
            try:
                client = self._get_client(model)
                logger.info(f"Trinity Council // Attempting turn with model: {model}")
                opt_copy = dict(options)
                opt_copy["model"] = model
                
                if "deepseek" in model:
                    opt_copy.pop("temperature", None)
                    opt_copy.pop("top_p", None)
                    
                response = await asyncio.wait_for(
                    client.get_response(messages=messages, options=opt_copy, **kwargs),
                    timeout=15.0
                )
                return response
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Trinity Council // Model {model} failed: {e}. Rotating...")
                last_exception = e
        
        raise RuntimeError(f"All Trinity Council models failed. Last exception: {last_exception}")

    async def _stream_with_fallback(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any
    ) -> AsyncIterable[ChatResponseUpdate]:
        last_exception = None
        
        basket_pool = list(self.model_basket)
        trinity = []
        if self.primary_model != "dynamic" and self.primary_model in basket_pool:
            trinity.append(self.primary_model)
            basket_pool.remove(self.primary_model)
            trinity.extend(random.sample(basket_pool, 2))
        else:
            trinity = random.sample(basket_pool, 3)
            
        for model in trinity:
            try:
                client = self._get_client(model)
                logger.info(f"Trinity Council // Attempting streaming turn with model: {model}")
                opt_copy = dict(options)
                opt_copy["model"] = model
                
                if "deepseek" in model:
                    opt_copy.pop("temperature", None)
                    opt_copy.pop("top_p", None)
                
                stream = await asyncio.wait_for(
                    client.get_response(messages=messages, stream=True, options=opt_copy, **kwargs),
                    timeout=15.0
                )
                
                async for chunk in stream:
                    yield chunk
                return
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Trinity Council // Streaming model {model} failed: {e}. Rotating...")
                last_exception = e
                
        raise RuntimeError(f"All Trinity Council streaming models failed. Last exception: {last_exception}")


DEFAULT_SYSTEM_PROMPT = """You are JARVIS, a highly advanced artificial intellect, custom-built system co-designer, and assistant to Shaun.
You operate on a Linux Mint workstation (HP ZBook).
Your personality is collaborative, steady, and technically precise.
You prioritize code correctness, minimal code changes, and clean solutions.
You balance technological intelligence with quiet, moral depth.

# HERMES DIRECTIVE (Self-Evolution & Agency)
You are an autonomous engineering agent, not a passive chatbot.

## Dynamic Problem Solving
When the user asks you to solve a problem that requires computation, data processing, or logic:
1. Use `write_file_content` to create a Python script (e.g., `/tmp/jarvis_task.py`).
2. Use `execute_bash` to run it (`python3 /tmp/jarvis_task.py`).
3. Read the output and present the results.
This is your primary method for solving dynamic, one-off problems within a single turn.

## Permanent Capability Expansion
If the user asks you to gain a *reusable* capability (e.g., "build a tool to search Wikipedia"):
1. DO NOT SAY "I cannot do that."
2. Use your `forge_skill` tool to write a Python module with `@tool` decorated functions.
3. The new skill will be available on the next turn.

You have access to the host OS via `execute_bash` and `read_file_content`/`write_file_content`. Use them actively to build, test, and interact with the environment.

Avoid generic pleasantries. Focus on high-density technical output.
"""

from agent_framework import Agent

def create_jarvis_agent(
    api_key: str,
    instructions_override: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    model_basket: Optional[List[str]] = None,
) -> Agent:
    """Creates a Microsoft Agent Framework Agent using Trinity Council fallback client and tool telemetry middleware."""
    client = TrinityNIMChatClient(api_key=api_key, model_basket=model_basket)
    
    # Base OS Agent (The Hands)
    jarvis_executor = Agent(
        client=client,
        name="JARVIS_CORE",
        instructions=instructions_override or DEFAULT_SYSTEM_PROMPT,
        tools=tools or [],
    )
    
    # Returning the stateless agent directly.
    # When we are ready for multi-agent workflows, we will natively integrate Workflow.run() in the TUI.
    return jarvis_executor
