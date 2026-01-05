# Browser Automation Learning System

An intelligent browser automation system powered by LLM that learns from web interactions and sends email notifications upon task completion.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run learning on a site
python -m src.main learn https://example.com
```

## Features

- 🧠 **LLM-Powered Decision Making** - Uses Claude/GPT-4 to reason about page state
- 👁️ **Vision + DOM Analysis** - Combines screenshots with DOM structure
- 📚 **Learning Loop** - Iteratively builds knowledge about site behavior
- 📧 **Email Notifications** - Alerts when learning completes or errors occur
- 💾 **Persistent Memory** - Stores learned patterns for future sessions

## Configuration

See `.env.example` for all available configuration options:

- `LLM_PROVIDER` - "anthropic" or "openai"
- `LLM_API_KEY` - Your API key
- `EMAIL_PROVIDER` - "resend", "sendgrid", or "smtp"
- `EMAIL_API_KEY` - Your email service API key
- `NOTIFICATION_EMAIL` - Where to send notifications

## CLI Commands

```bash
# Learn a new site
python -m src.main learn <url> [--headless] [--max-iterations N]

# Resume a session
python -m src.main resume <session_id>

# Generate report
python -m src.main report <session_id> [--format html|json]
```

## Architecture

```
src/
├── core/          # Orchestrator, Browser Agent
├── intelligence/  # LLM Client, DOM Analyzer
├── learning/      # Memory, Confidence Scoring
└── notifications/ # Email Service
```

## License

MIT
