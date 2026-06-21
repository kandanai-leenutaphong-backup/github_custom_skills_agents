# github_custom_skills_agents


Switch to `Hi Agent` and try the following prompt:
1. ```Create a streamline app for Kanban board.```

Change back to main Agent and type the following:

2. ```Write a file main.py to call azure openai model```

You should see the code follows `copilot-instructions.md` to use DefaultAzureCredentials

Try the following skills:

3. ```/meeting-minutes Please generate meeting meeting minutes in assets/transcript.txt for this transcript in the assets/ai-summary.md```

4. ```Write a Python function `get_user_by_email` in a file query.py that takes an email address and returns the matching user row from a `users` table in a PostgreSQL database using psycopg2.```

This will check the `security-and-owasp.instructions.md`


See more of custom skills & Agents at: https://github.com/github/awesome-copilot

Side note on custom PR Review: https://github.com/skills/copilot-code-review/blob/main/.github/steps/3-step.md

---

## Resilience & Observability

This repo ships production-ready retry logic and structured logging for Azure OpenAI API calls.

### Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # edit values as needed
python3 -m pytest tests/ -v
```

### Modules

| Module | Purpose |
|---|---|
| `resilience.py` | Retry wrapper with exponential backoff + jitter (tenacity) |
| `logger.py` | JSON-formatted structured logger with OpenAI call helpers |
| `middleware.py` | FastAPI middleware that injects a UUID correlation ID per request |

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `RETRY_MAX_ATTEMPTS` | `3` | Maximum number of retry attempts for HTTP 429 / 5xx responses |
| `RETRY_BASE_DELAY` | `1.0` | Base delay in seconds for the first retry backoff interval |
| `LOG_LEVEL` | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FORMAT` | `json` | Log output format: `json` (structured) or `text` (human-readable) |

See `.env.example` for a full annotated template.

### Security

- **No API keys in code.** Authentication uses `DefaultAzureCredential()` (managed identity / Entra ID).
- Correlation IDs in incoming `x-request-id` headers are validated as UUID4 to prevent log injection.
- All secrets must be loaded from environment variables or a secrets manager — never hardcoded.