# Security Architecture

Security controls required for all components of the Autonomous Software Factory.

---

## Authentication and Authorization

All service endpoints require authentication. No service is exposed without access control.

```python
# vLLM inference endpoints — API key required
# Set via environment variable, never hardcoded
vllm serve model_name \
  --api-key "${VLLM_API_KEY}" \
  ...

# FastAPI agent endpoints — bearer token validation
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != os.environ["FACTORY_API_TOKEN"]:
        raise HTTPException(status_code=401, detail="Invalid token")
```

---

## CORS Policy

CORS is restricted to known origins. Wildcard origins (`*`) are never used.

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ["ALLOWED_ORIGIN"]],  # explicit origin only
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

---

## TLS / Encryption in Transit

All inter-service communication uses TLS:
- vLLM endpoints served behind TLS-terminating reverse proxy
- Temporal client connections use TLS certificates
- ChromaDB accessed over authenticated HTTPS
- No plaintext HTTP in production

---

## Input Validation

All user-facing input is validated via Pydantic models before processing. Raw strings are never passed directly to:
- SQL queries (SQLAlchemy ORM only — no raw SQL with string interpolation)
- Shell commands (no `subprocess` with `shell=True` on user input)
- LLM prompts without sanitization (prompt injection mitigations applied)

```python
class FeatureIdeaInput(BaseModel):
    description: str = Field(..., min_length=10, max_length=5000)
    complexity_hint: Optional[str] = Field(None, pattern="^(nano|micro|standard|complex|critical)$")
```

---

## Secrets Management

Secrets are never committed to the repository. All sensitive values are loaded from environment variables or a secrets manager at runtime.

Required secrets (stored in environment, not in code):
- `VLLM_API_KEY` — inference endpoint authentication
- `FACTORY_API_TOKEN` — inter-agent API authentication
- `DATABASE_URL` — database connection string
- `TEMPORAL_TLS_CERT` / `TEMPORAL_TLS_KEY` — Temporal mTLS
- `CHROMADB_AUTH_TOKEN` — vector database authentication

---

## Debug and Diagnostic Endpoints

Debug endpoints (`/debug`, `/docs`, `/redoc`, `/openapi.json`) are disabled in production:

```python
import os

debug_mode = os.environ.get("FACTORY_ENV") == "development"

app = FastAPI(
    docs_url="/docs" if debug_mode else None,
    redoc_url="/redoc" if debug_mode else None,
    openapi_url="/openapi.json" if debug_mode else None,
)
```

---

## Dependency Security

- All dependencies pinned to exact versions in `dependency_manifest.json`
- `pip-audit` run before any version is approved
- New dependencies require a 7-day maturity window before adoption
- `bandit` and `semgrep` scan every code change for security issues
