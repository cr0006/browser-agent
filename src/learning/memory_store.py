"""Memory Store - Persistent storage for learned patterns."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class LearnedPattern:
    """A pattern learned from interacting with a website."""

    pattern_id: str
    domain: str
    element_type: str
    selector_pattern: str
    action_sequence: list[str]
    success_count: int = 0
    failure_count: int = 0
    last_used: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def reliability(self) -> float:
        """Calculate reliability score."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "pattern_id": self.pattern_id,
            "domain": self.domain,
            "element_type": self.element_type,
            "selector_pattern": self.selector_pattern,
            "action_sequence": self.action_sequence,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "last_used": self.last_used,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearnedPattern":
        """Create from dictionary."""
        return cls(**data)


class MemoryStore:
    """Persistent storage for learned patterns and session history."""

    def __init__(self, patterns_dir: Path):
        self.patterns_dir = patterns_dir
        self.patterns_dir.mkdir(parents=True, exist_ok=True)
        self._patterns: dict[str, LearnedPattern] = {}
        self._load_patterns()

    def _load_patterns(self) -> None:
        """Load all patterns from disk."""
        for filepath in self.patterns_dir.glob("*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    pattern = LearnedPattern.from_dict(data)
                    self._patterns[pattern.pattern_id] = pattern
            except Exception as e:
                logger.warning("Failed to load pattern", filepath=str(filepath), error=str(e))

        logger.info("Loaded patterns from disk", count=len(self._patterns))

    def save_pattern(self, pattern: LearnedPattern) -> None:
        """Save a pattern to disk."""
        self._patterns[pattern.pattern_id] = pattern
        filepath = self.patterns_dir / f"{pattern.pattern_id}.json"
        with open(filepath, "w") as f:
            json.dump(pattern.to_dict(), f, indent=2)
        logger.debug("Saved pattern", pattern_id=pattern.pattern_id)

    def get_patterns_for_domain(self, domain: str) -> list[LearnedPattern]:
        """Get all learned patterns for a domain."""
        return [p for p in self._patterns.values() if p.domain == domain]

    def record_success(self, pattern_id: str) -> None:
        """Record a successful use of a pattern."""
        if pattern_id in self._patterns:
            self._patterns[pattern_id].success_count += 1
            self._patterns[pattern_id].last_used = datetime.now().isoformat()
            self.save_pattern(self._patterns[pattern_id])

    def record_failure(self, pattern_id: str) -> None:
        """Record a failed use of a pattern."""
        if pattern_id in self._patterns:
            self._patterns[pattern_id].failure_count += 1
            self.save_pattern(self._patterns[pattern_id])

    def get_context_for_llm(self, domain: str, max_patterns: int = 10) -> str:
        """Generate context string for LLM about known patterns."""
        patterns = self.get_patterns_for_domain(domain)

        if not patterns:
            return "No previously learned patterns for this domain."

        # Sort by reliability
        patterns.sort(key=lambda p: p.reliability, reverse=True)

        context_lines = ["## Previously Learned Patterns\n"]
        for pattern in patterns[:max_patterns]:
            context_lines.append(
                f"- {pattern.element_type}: {pattern.selector_pattern} "
                f"(reliability: {pattern.reliability:.0%})"
            )

        return "\n".join(context_lines)

    def add_pattern_from_action(
        self,
        domain: str,
        element_type: str,
        selector: str,
        action_type: str,
        success: bool,
    ) -> str:
        """Create or update a pattern based on an action."""
        # Generate pattern ID from domain and selector
        pattern_id = f"{domain}_{hash(selector) % 10000:04d}"

        if pattern_id in self._patterns:
            pattern = self._patterns[pattern_id]
        else:
            pattern = LearnedPattern(
                pattern_id=pattern_id,
                domain=domain,
                element_type=element_type,
                selector_pattern=selector,
                action_sequence=[action_type],
            )

        if success:
            pattern.success_count += 1
        else:
            pattern.failure_count += 1

        pattern.last_used = datetime.now().isoformat()
        self.save_pattern(pattern)

        return pattern_id
