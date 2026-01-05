"""Configuration management for the Browser Learning Agent."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Settings
    llm_provider: Literal["anthropic", "openai"] = "openai"
    llm_model: str = "gpt-4o"
    llm_api_key: str = Field(default="", description="API key for LLM provider")
    llm_reasoning_effort: str = "medium"  # low, medium, high (for OpenAI reasoning models)

    # Browser Settings
    headless: bool = False
    viewport_width: int = 1280
    viewport_height: int = 720
    timeout_ms: int = 30000

    # Learning Settings
    max_iterations: int = 100
    confidence_threshold: float = 0.95
    action_delay_ms: int = 500

    # Email Settings
    email_provider: Literal["resend", "sendgrid", "smtp", "gmail"] = "gmail"
    email_api_key: str = Field(default="", description="API key for email service")
    notification_email: str = "caique.rivero@gmail.com"
    
    # Gmail OAuth Settings
    gmail_client_id: str = Field(default="", description="Gmail OAuth client ID")
    gmail_client_secret: str = Field(default="", description="Gmail OAuth client secret")

    # Storage
    data_dir: Path = Path("./data")

    @property
    def sessions_dir(self) -> Path:
        """Directory for session data."""
        return self.data_dir / "sessions"

    @property
    def screenshots_dir(self) -> Path:
        """Directory for screenshots."""
        return self.data_dir / "screenshots"

    @property
    def patterns_dir(self) -> Path:
        """Directory for learned patterns."""
        return self.data_dir / "learned_patterns"

    def ensure_directories(self) -> None:
        """Create required data directories."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.patterns_dir.mkdir(parents=True, exist_ok=True)


# Global config instance
config = Config()
