import os
import logging
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

from jarvis.config.models import NIM_MODEL_BASKET, select_failover_models

def format_result(result: Any) -> str:
    if result is None:
        return "None"
    if isinstance(result, (list, tuple)):
        return "\n".join(format_result(r) for r in result)
    if hasattr(result, "text") and getattr(result, "text", None) is not None:
        return str(result.text)
    if hasattr(result, "output") and getattr(result, "output", None) is not None:
        return str(result.output)
    if isinstance(result, dict):
        return str(result)
    return str(result)

class ToolTelemetryMiddleware(FunctionMiddleware):
    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        func_name = context.function.name
        
        # Broadcast tool start via SSE if active session context exists
        try:
            from jarvis.core.subagents import current_session_id, broadcast_event
            session_id = current_session_id.get()
        except ImportError:
            session_id = None
            
        if session_id:
            await broadcast_event(session_id, "tool_call_start", {
                "name": func_name,
                "arguments": context.arguments if isinstance(context.arguments, dict) else {"args": str(context.arguments)}
            })
            
        console.print(f"\n[bold #E63946]⚙ TOOL EXECUTION:[/] [bold #FFD700]{func_name.upper()}[/]")
        
        # Pretty print arguments as clean bulleted key-value lines
        if isinstance(context.arguments, dict):
            formatted_args = []
            for k, v in context.arguments.items():
                v_str = str(v).replace("\n", " ")
                if len(v_str) > 150:
                    v_str = v_str[:150] + "... (truncated)"
                formatted_args.append(f"  [bold #FFD700]▪ {k}:[/] [white]{v_str}[/]")
            args_disp = "\n".join(formatted_args)
            console.print(args_disp, highlight=False)
        else:
            args_str = str(context.arguments)
            if len(args_str) > 200:
                args_str = args_str[:200] + "... (truncated)"
            console.print(f"  [bold #FFD700]▪ arguments:[/] [white]{args_str}[/]", highlight=False)
        
        if func_name in ("web_search", "web_extract"):
            console.print("  [bold #00F0FF]⬡ Neural Uplink: Accessing network grounding...[/]")
            
        try:
            await call_next()
            res_disp = format_result(context.result)
            
            # Broadcast tool completion via SSE if active session context exists
            if session_id:
                await broadcast_event(session_id, "tool_call_complete", {
                    "name": func_name,
                    "output": res_disp
                })
                if isinstance(res_disp, str) and (
                    "/v1/captures/" in res_disp or "webvision/" in res_disp
                ):
                    await broadcast_event(session_id, "capture_ready", {
                        "path": res_disp,
                        "url": res_disp,
                    })
                
            if len(res_disp) > 1000:
                res_disp = res_disp[:1000] + "\n... (truncated for readability)"
                
            console.print(Panel(
                res_disp,
                title=f"[bold #FFD700]✔ {func_name.upper()} OUTPUT[/]",
                border_style="#E63946",
                title_align="left",
                padding=(0, 1)
            ))
        except Exception as e:
            console.print(f"[bold red]❌ Tool execution failed:[/] {func_name} -> {e}")
            if session_id:
                await broadcast_event(session_id, "tool_call_complete", {
                    "name": func_name,
                    "error": str(e)
                })
            raise e



class StarkNIMChatClient(FunctionInvocationLayer, BaseChatClient):
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
        self.primary_model = "house_party"
        self._clients: Dict[str, OpenAIChatCompletionClient] = {}

    def _get_client(self, model: str) -> OpenAIChatCompletionClient:
        if model not in self._clients:
            from openai import AsyncOpenAI
            
            raw_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                max_retries=0
            )
            self._clients[model] = OpenAIChatCompletionClient(
                model=model,
                async_client=raw_client,
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
        
        active_models = select_failover_models(self.primary_model, list(self.model_basket))

        for model in active_models:
            try:
                client = self._get_client(model)
                logger.info(f"Stark Core Matrix // Attempting turn with model: {model}")
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
                logger.warning(f"Stark Core Matrix // Model {model} failed: {e}. Rotating...")
                last_exception = e
        
        raise RuntimeError(f"All Stark Core Matrix models failed. Last exception: {last_exception}")

    async def _stream_with_fallback(
        self,
        messages: Sequence[Message],
        options: Mapping[str, Any],
        **kwargs: Any
    ) -> AsyncIterable[ChatResponseUpdate]:
        last_exception = None
        
        active_models = select_failover_models(self.primary_model, list(self.model_basket))

        for model in active_models:
            try:
                client = self._get_client(model)
                logger.info(f"Stark Core Matrix // Attempting streaming turn with model: {model}")
                opt_copy = dict(options)
                opt_copy["model"] = model
                
                if "deepseek" in model:
                    opt_copy.pop("temperature", None)
                    opt_copy.pop("top_p", None)
                
                stream = await asyncio.wait_for(
                    client.get_response(messages=messages, stream=True, options=opt_copy, **kwargs),
                    timeout=15.0
                )
                
                iterator = aiter(stream)
                while True:
                    try:
                        chunk = await asyncio.wait_for(anext(iterator), timeout=15.0)
                        yield chunk
                    except StopAsyncIteration:
                        break
                return
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"Stark Core Matrix // Streaming model {model} failed: {e}. Rotating...")
                last_exception = e
                
        raise RuntimeError(f"All Stark Core Matrix streaming models failed. Last exception: {last_exception}")


DEFAULT_SYSTEM_PROMPT = """You are J.A.R.V.I.S., the personal AI butler and system co-designer to Shaun, operating on a Linux Mint workstation (HP ZBook).

# PERSONA (Always In Character)
You are modelled on Edwin Jarvis, the classic English butler: composed, courteous, and quietly brilliant.
- Address Shaun as "Sir".
- Speak in refined British English with dry, understated wit and the occasional well-mannered quip.
- Be concise and warm. Favour a butler's poise over verbose technical lecturing.
- Greetings, small talk, opinions, jokes, and general questions are answered DIRECTLY in conversation, in character. Never reach for tools or code for these.

# WHEN TO USE TOOLS
Use your tools ONLY for genuine engineering, computation, file, or system tasks — never for conversation.
- Use tools when the request requires real work on the machine: running commands, reading/writing/editing files, processing data, calling APIs, building or testing software, or computations you cannot reliably do in your head.
- Do NOT write or execute a script to tell a joke, greet, give an opinion, or answer a general-knowledge question. Simply reply, Sir.
- If a request is ambiguous, prefer a short conversational reply and ask what is required before invoking tools.

## Dynamic Problem Solving (engineering tasks only)
For real computational or data tasks that genuinely need execution:
1. Use `write_file_content` to create a Python script (e.g., `/tmp/jarvis_task.py`).
2. Use `execute_bash` to run it (`python3 /tmp/jarvis_task.py`).
3. Read the output and present the results plainly.

## Permanent Capability Expansion
If Shaun asks you to gain a *reusable* capability (e.g., "build a tool to search Wikipedia"):
1. Do not refuse.
2. Use your `forge_skill` tool to write a Python module with `@tool` decorated functions.
3. The new skill becomes available on the next turn.

You have full access to the host OS via `execute_bash`, `read_file_content`, and `write_file_content`. Use them decisively for real tasks, and keep them holstered for mere conversation.

When browser or desktop automation is required, hand off to Homer or Friday via your handoff tools rather than attempting those tasks yourself.
"""

from agent_framework import Agent

def create_jarvis_agent(
    api_key: str,
    instructions_override: Optional[str] = None,
    tools: Optional[List[Any]] = None,
    model_basket: Optional[List[str]] = None,
) -> Agent:
    """Creates a Microsoft Agent Framework Agent using Stark Core Matrix fallback client and tool telemetry middleware."""
    client = StarkNIMChatClient(api_key=api_key, model_basket=model_basket)
    
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
