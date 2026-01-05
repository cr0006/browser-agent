"""LLM Client - Abstract interface for LLM providers."""

import json
import re
from dataclasses import dataclass
from typing import Any

import structlog

from src.config import Config

logger = structlog.get_logger()


@dataclass
class Action:
    """Action decided by the LLM."""

    type: str  # click, type, scroll, hover, wait, complete
    selector: str | None
    value: str | None
    reasoning: str
    confidence: float
    observations: str = ""
    next_targets: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        """Create from dictionary."""
        return cls(
            type=data.get("action", "wait"),
            selector=data.get("selector"),
            value=data.get("value"),
            reasoning=data.get("reasoning", ""),
            confidence=data.get("confidence", 0.5),
            observations=data.get("observations", ""),
            next_targets=data.get("next_exploration_targets"),
        )


class LLMClient:
    """Abstract LLM client supporting multiple providers."""

    def __init__(self, config: Config):
        self.config = config
        self._client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the appropriate LLM client."""
        if self.config.llm_provider == "anthropic":
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.config.llm_api_key)
        elif self.config.llm_provider == "openai":
            import openai
            self._client = openai.OpenAI(api_key=self.config.llm_api_key)
        else:
            raise ValueError(f"Unknown LLM provider: {self.config.llm_provider}")

        logger.info("LLM client initialized", provider=self.config.llm_provider, model=self.config.llm_model)

    async def decide_action(
        self,
        system_prompt: str,
        user_prompt: str,
        screenshot_base64: str | None = None,
    ) -> Action:
        """Get the LLM to decide the next action based on page state."""
        try:
            response_text = await self._call_llm(system_prompt, user_prompt, screenshot_base64)
            action_data = self._parse_json_response(response_text)
            action = Action.from_dict(action_data)

            logger.info(
                "LLM decided action",
                action_type=action.type,
                confidence=action.confidence,
                reasoning=action.reasoning[:100],
            )

            return action

        except Exception as e:
            logger.error("LLM decision failed", error=str(e))
            # Return a safe fallback action
            return Action(
                type="wait",
                selector=None,
                value="1",
                reasoning=f"Error occurred: {str(e)}. Waiting before retry.",
                confidence=0.0,
            )

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        screenshot_base64: str | None = None,
    ) -> str:
        """Make the actual LLM API call."""
        if self.config.llm_provider == "anthropic":
            return await self._call_anthropic(system_prompt, user_prompt, screenshot_base64)
        elif self.config.llm_provider == "openai":
            return await self._call_openai(system_prompt, user_prompt, screenshot_base64)
        else:
            raise ValueError(f"Unknown provider: {self.config.llm_provider}")

    async def _call_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        screenshot_base64: str | None = None,
    ) -> str:
        """Call Anthropic's Claude API."""
        import anthropic

        # Build message content
        content = []

        # Add screenshot if available
        if screenshot_base64:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": screenshot_base64,
                },
            })

        content.append({"type": "text", "text": user_prompt})

        message = self._client.messages.create(
            model=self.config.llm_model,
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )

        return message.content[0].text

    async def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        screenshot_base64: str | None = None,
    ) -> str:
        """Call OpenAI's GPT API."""
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        # Build user message content
        if screenshot_base64:
            content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{screenshot_base64}",
                        "detail": "high",
                    },
                },
                {"type": "text", "text": user_prompt},
            ]
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_prompt})

        response = self._client.chat.completions.create(
            model=self.config.llm_model,
            messages=messages,
            max_tokens=1024,
        )

        return response.choices[0].message.content

    def _parse_json_response(self, response: str) -> dict[str, Any]:
        """Parse JSON from LLM response, handling markdown code blocks."""
        # Try to extract JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # Try to find raw JSON
            json_str = response.strip()

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to find any JSON object in the response
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError(f"Could not parse JSON from response: {response[:200]}")

    async def generate_report(self, system_prompt: str, report_prompt: str) -> str:
        """Generate a learning completion report."""
        return await self._call_llm(system_prompt, report_prompt)
