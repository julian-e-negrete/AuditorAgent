# arch-agent

LLM-backed conversational architecture documentation agent. Reviews Markdown architecture docs, identifies risks, suggests improvements, generates ADRs/diagrams/runbooks, and integrates with GLPI for ticket tracking.

## Requirements

- Python 3.11+
- A free LLM API key (Groq recommended — see below)
- GLPI proxy reachable at `http://100.112.16.115:8080` (optional — agent runs in degraded mode without it)

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd arch-agent
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -e ".[dev]"
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
LLM_PROVIDER=groq
LLM_API_KEY=your-groq-api-key
LLM_MODEL=groq/llama-3.1-70b-versatile

GLPI_PROXY_URL=http://100.112.16.115:8080
GLPI_CLIENT_ID=your-glpi-client-id
GLPI_CLIENT_SECRET=your-glpi-client-secret
GLPI_USERNAME=your-glpi-username
GLPI_PASSWORD=your-glpi-password
```

### 4. Get a free Groq API key

1. Sign up at [console.groq.com](https://console.groq.com) — no credit card required
2. Go to **API Keys** → **Create API Key**
3. Paste the key into `.env` as `LLM_API_KEY`

Other free providers that work out of the box:

| Provider | Model value for `.env` |
|---|---|
| [Google AI Studio](https://aistudio.google.com) | `gemini/gemini-1.5-flash` |
| [Groq](https://console.groq.com) | `groq/llama-3.1-70b-versatile` |
| [OpenRouter](https://openrouter.ai) | `openrouter/meta-llama/llama-3.1-8b-instruct:free` |

## Usage

### Review architecture docs

```bash
# Review specific files
arch-agent review ARCHITECTURE.md SYSTEM_DIAGRAM.md

# Review all .md files in a directory
arch-agent review --dir docs/

# Auto-create GLPI tickets for critical/high findings
arch-agent review ARCHITECTURE.md --auto-ticket
```

### Interactive chat

```bash
# Chat with the agent (optionally pre-load context files)
arch-agent chat --context ARCHITECTURE.md
```

### Generate documents

```bash
# Architecture Decision Record
arch-agent generate adr --title "Use Redis for session caching" --output adr-001.md

# System diagram (Mermaid)
arch-agent generate diagram --type system --output diagram.md

# Operational runbook
arch-agent generate runbook --scenario "Database failover" --output runbook.md
```

### HTTP API (optional)

```bash
uvicorn arch_agent.api:app --port 8000
```

```bash
# Review
curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{"files": ["ARCHITECTURE.md"]}'

# Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What are the biggest risks?", "session_id": "s1"}'

# Generate ADR
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{"doc_type": "adr", "title": "Adopt Tailscale for inter-server networking"}'
```

### Python API

```python
import asyncio
from arch_agent import Orchestrator, ReviewRequest
from pathlib import Path

async def main():
    agent = Orchestrator.from_env()
    async for chunk in agent.run_review(ReviewRequest(files=[Path("ARCHITECTURE.md")])):
        print(chunk, end="", flush=True)

asyncio.run(main())
```

## Run tests

```bash
pytest tests/ -v
```

## Project structure

```
arch_agent/
  tools/
    ingestion.py   # Markdown ingestion
    risk.py        # Risk analysis via LLM
    improvement.py # Improvement suggestions
    docgen.py      # ADR / diagram / runbook generation
    glpi.py        # GLPI ticket integration
  models/          # Pydantic data models
  orchestrator.py  # Central coordinator
  cli.py           # Typer CLI
  api.py           # FastAPI interface
  config.py        # Settings (pydantic-settings)
  memory.py        # Conversation memory
tests/             # pytest test suite
.env.example       # Environment variable template
pyproject.toml     # Dependencies and entry points
```
