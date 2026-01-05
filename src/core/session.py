"""Session state management for learning sessions."""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ActionRecord:
    """Record of a single action taken during a session."""

    timestamp: str
    action_type: str
    selector: str | None
    value: str | None
    reasoning: str
    success: bool
    page_url: str
    screenshot_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp,
            "action_type": self.action_type,
            "selector": self.selector,
            "value": self.value,
            "reasoning": self.reasoning,
            "success": self.success,
            "page_url": self.page_url,
            "screenshot_path": self.screenshot_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionRecord":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class Session:
    """Represents a learning session for a URL."""

    session_id: str
    target_url: str
    created_at: str
    status: str = "active"  # active, completed, failed
    actions: list[ActionRecord] = field(default_factory=list)
    confidence_score: float = 0.0
    total_elements_found: int = 0
    elements_explored: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, url: str) -> "Session":
        """Create a new session for a URL."""
        return cls(
            session_id=str(uuid.uuid4())[:8],
            target_url=url,
            created_at=datetime.now().isoformat(),
        )

    def add_action(self, action: ActionRecord) -> None:
        """Record an action in this session."""
        self.actions.append(action)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "target_url": self.target_url,
            "created_at": self.created_at,
            "status": self.status,
            "actions": [a.to_dict() for a in self.actions],
            "confidence_score": self.confidence_score,
            "total_elements_found": self.total_elements_found,
            "elements_explored": self.elements_explored,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """Create from dictionary."""
        actions = [ActionRecord.from_dict(a) for a in data.pop("actions", [])]
        return cls(actions=actions, **data)

    def save(self, sessions_dir: Path) -> Path:
        """Save session to disk."""
        filepath = sessions_dir / f"{self.session_id}.json"
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return filepath

    @classmethod
    def load(cls, session_id: str, sessions_dir: Path) -> "Session":
        """Load session from disk."""
        filepath = sessions_dir / f"{session_id}.json"
        with open(filepath) as f:
            return cls.from_dict(json.load(f))

    @property
    def success_rate(self) -> float:
        """Calculate action success rate."""
        if not self.actions:
            return 0.0
        successful = sum(1 for a in self.actions if a.success)
        return successful / len(self.actions)

    @property
    def duration_seconds(self) -> float:
        """Calculate session duration in seconds."""
        if len(self.actions) < 2:
            return 0.0
        first = datetime.fromisoformat(self.actions[0].timestamp)
        last = datetime.fromisoformat(self.actions[-1].timestamp)
        return (last - first).total_seconds()
