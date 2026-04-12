"""Agent loop: Anthropic call, tool dispatch, iteration, stop conditions."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from cosinabox import defaults
from cosinabox.agent.cost import CostExceeded, CostTracker
from cosinabox.agent.routing import Router

# Advisor tool definition (beta API)
_ADVISOR_TOOL = {
    "type": "advisor_20260301",
    "name": "advisor",
    "model": defaults.OPUS_MODEL_ID,
    "max_uses": defaults.ADVISOR_MAX_USES,
}
_ADVISOR_BETA = "advisor-tool-2026-03-01"


class AnthropicClient(Protocol):
    messages: Any  # duck-typed against the real anthropic.Anthropic client
    beta: Any  # for advisor calls via client.beta.messages.create


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    result: str
    tool_use_id: str


@dataclass
class LoopResult:
    final_text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stopped_reason: str = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0


def _wrap_untrusted(data: str) -> str:
    """Wrap external tool output to defend against prompt injection.

    Layer 1: tool results need prompt-injection defense.
    """
    return "<untrusted_tool_output>\n" + data + "\n</untrusted_tool_output>"


def _strip_advisor_blocks(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove server_tool_use and advisor_tool_result blocks from history.

    Required because the API returns 400 if the current turn doesn't use
    advisor but history contains advisor blocks.
    """
    cleaned = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            filtered = [
                b
                for b in content
                if not (
                    isinstance(b, dict)
                    and b.get("type") in ("server_tool_use", "advisor_tool_result")
                )
                and not (
                    hasattr(b, "type") and b.type in ("server_tool_use", "advisor_tool_result")
                )
            ]
            if filtered:
                cleaned.append({**msg, "content": filtered})
        else:
            cleaned.append(msg)
    return cleaned


class AgentLoop:
    def __init__(
        self,
        *,
        anthropic_client: AnthropicClient,
        router: Router,
        cost_tracker: CostTracker,
        tools: dict[str, Callable[..., str]],
        max_tool_iterations: int = 8,
        tool_iteration_delay_s: float = 2.0,
    ) -> None:
        self.client = anthropic_client
        self.router = router
        self.cost = cost_tracker
        self.tools = tools
        self.max_tool_iterations = max_tool_iterations
        self.tool_iteration_delay_s = tool_iteration_delay_s

    def run(self, *, prompt: str, session_id: str) -> LoopResult:
        model, thinking, use_advisor = self.router.choose_model(prompt)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        result = LoopResult(final_text="")
        for iteration in range(self.max_tool_iterations):
            # Strip advisor blocks if not using advisor this iteration
            call_messages = messages if use_advisor else _strip_advisor_blocks(messages)

            try:
                call_kwargs: dict[str, Any] = {
                    "model": model,
                    "max_tokens": 4096,
                    "messages": call_messages,
                }
                if thinking:
                    call_kwargs["thinking"] = thinking

                # Inject advisor tool if enabled
                if use_advisor:
                    call_kwargs["tools"] = [_ADVISOR_TOOL]
                    response = self.client.beta.messages.create(
                        betas=[_ADVISOR_BETA],
                        **call_kwargs,
                    )
                else:
                    response = self.client.messages.create(**call_kwargs)
            except CostExceeded:
                result.stopped_reason = "cost_exceeded"
                return result
            result.input_tokens += response.usage.input_tokens
            result.output_tokens += response.usage.output_tokens
            if response.stop_reason == "end_turn":
                text_blocks = [b.text for b in response.content if b.type == "text"]
                result.final_text = "\n".join(text_blocks)
                return result
            if response.stop_reason == "tool_use":
                tool_blocks = [b for b in response.content if b.type == "tool_use"]
                tool_results: list[dict[str, Any]] = []
                for block in tool_blocks:
                    fn = self.tools.get(block.name)
                    if fn is None:
                        raw = f"Tool '{block.name}' not configured"
                    else:
                        raw = str(fn(**block.input))
                    wrapped = _wrap_untrusted(raw)
                    result.tool_calls.append(
                        ToolCall(
                            name=block.name,
                            args=dict(block.input),
                            result=raw,
                            tool_use_id=block.id,
                        )
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": wrapped,
                        }
                    )
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})

                # After first iteration, disable advisor (tool-loops are mechanical)
                if iteration == 0 and use_advisor:
                    use_advisor = False
                    thinking = None

                if iteration < self.max_tool_iterations - 1:
                    time.sleep(self.tool_iteration_delay_s)
                continue
            result.stopped_reason = response.stop_reason or "unknown"
            return result
        result.stopped_reason = "max_iterations"
        return result
