# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, email: **sslabbert@student.umgc.edu**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive an acknowledgment within 48 hours and a detailed response within 7 days.

## Supported Versions

| Version | Supported |
|---------|-----------|
| main    | Yes       |

## Security Requirements

This project enforces the following security controls:

### Dependency Management
- All dependencies pinned to exact versions in `dependency_manifest.json`
- No carets, tildes, or ranges permitted
- Dependencies audited with `pip-audit` before approval
- New dependencies require explicit approval and a 7-day maturity window

### Secrets Management
- No secrets, API keys, or credentials committed to the repository
- All secrets loaded from environment variables or a secrets manager at runtime
- `.gitignore` blocks common secret file patterns (`.env`, `*.pem`, `*.key`, `credentials.json`)

### Code Quality Gates
- `bandit` security scanner — HIGH severity findings block merge
- `mypy --strict` type checking required
- `ruff` linting enforced
- Hostile audit (second-model review) for logic and auth issues

### Runtime Security
- All inter-service communication over TLS
- Authentication required on all endpoints (vLLM, FastAPI, ChromaDB)
- CORS restricted to known origins only
- No debug endpoints in production deployments
- Input validation on all user-facing endpoints via Pydantic models
