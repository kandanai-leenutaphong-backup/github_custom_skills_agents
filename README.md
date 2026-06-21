# github_custom_skills_agents

[![CI](https://github.com/edsml-kl121/github_custom_skills_agents/actions/workflows/ci.yml/badge.svg)](https://github.com/edsml-kl121/github_custom_skills_agents/actions/workflows/ci.yml)

A cloud-native AI chatbot starter app built with **FastAPI** (backend) and a lightweight HTML/JS frontend, powered by **Azure OpenAI** via `DefaultAzureCredential` — no API keys ever hardcoded.

---

## 🏗️ Architecture

```
frontend (nginx :8080)
    └── /api/* → proxy → backend (FastAPI :8000)
                              └── Azure OpenAI (DefaultAzureCredential)
```

---

## 🔐 Security Design

- **No API keys** — authentication uses [`DefaultAzureCredential`](https://learn.microsoft.com/azure/developer/python/sdk/authentication-overview) (managed identity in production, `az login` locally).
- CORS locked to explicit allowed origins.
- Pydantic input validation on all chat requests (max message length, valid roles, message count limits).
- Frontend uses `textContent` exclusively — never `innerHTML` — to prevent XSS.
- Nginx serves security headers: `X-Frame-Options`, `X-Content-Type-Options`, `Content-Security-Policy`.
- Backend container runs as a non-root user.

---

## 📋 Prerequisites

- Python 3.11+
- Docker & Docker Compose (for containerised setup)
- An [Azure OpenAI resource](https://learn.microsoft.com/azure/ai-services/openai/how-to/create-resource) with a chat model deployed
- Azure CLI (`az`) for local authentication

---

## ⚙️ Azure OpenAI Configuration

1. Create an Azure OpenAI resource in the [Azure portal](https://portal.azure.com).
2. Deploy a chat model (e.g. `gpt-4o`) in **Azure OpenAI Studio → Deployments**.
3. Assign yourself (or your app's managed identity) the **"Cognitive Services OpenAI User"** role on the resource.

```bash
az role assignment create \
  --role "Cognitive Services OpenAI User" \
  --assignee <your-object-id-or-client-id> \
  --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<resource>
```

---

## 🚀 Local Development (without Docker)

```bash
# 1. Authenticate with Azure
az login

# 2. Install backend dependencies
cd backend
pip install -r requirements-dev.txt

# 3. Configure environment
cp ../.env.example ../.env
# Edit .env and set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT_NAME

# 4. Run the backend
uvicorn main:app --reload --port 8000

# 5. Open the frontend (in a second terminal or browser)
# Simply open frontend/index.html in your browser,
# then set the API URL in the browser console:
#   window.API_BASE_URL = 'http://localhost:8000'
```

---

## 🐳 Docker Usage

```bash
# 1. Copy and fill in your environment variables
cp .env.example .env
# Edit .env — set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT_NAME

# 2. Build and start both services
docker compose up --build

# 3. Open the chat UI
open http://localhost:8080
```

To stop: `docker compose down`

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | ✅ | — | Your Azure OpenAI resource URL |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | ✅ | `gpt-4o` | Deployment name in Azure OpenAI Studio |
| `AZURE_OPENAI_API_VERSION` | ❌ | `2024-02-15-preview` | API version |
| `ALLOWED_ORIGINS` | ❌ | `http://localhost:8080` | Comma-separated CORS origins |

---

## 🧪 Running Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests/ -v
```

Tests mock all Azure OpenAI calls via FastAPI dependency overrides — no real credentials needed.

---

## 🔍 Linting

```bash
cd backend
ruff check .
```

---

## 📁 Project Structure

```
backend/
├── main.py               # FastAPI app — chat endpoint, Azure OpenAI client
├── requirements.txt      # Runtime dependencies
├── requirements-dev.txt  # Dev/test dependencies
├── pyproject.toml        # Ruff + pytest config
├── Dockerfile
└── tests/
    ├── conftest.py
    └── test_main.py
frontend/
├── index.html            # Single-page chat UI
├── nginx.conf            # Nginx config with security headers + API proxy
└── Dockerfile
docker-compose.yml
.env.example              # Template for environment variables
sample_prompts.json       # Example prompts shown in the UI
.github/workflows/ci.yml  # GitHub Actions: lint + test
```

---

## 🤖 Custom Copilot Skills & Agents

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