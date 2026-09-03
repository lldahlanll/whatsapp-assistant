# DOC-023 · Deployment & Infrastructure Plan

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** DevOps Engineer  

---

## 1. Containerization Strategy

Aplikasi dibungkus sebagai **multi-stage Docker container** berbasis Python 3.13-slim untuk meminimalkan ukuran image dan mengamankan runtime.

### `docker/Dockerfile` Reference
```dockerfile
FROM python:3.13-slim AS builder

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.13-slim AS runner

WORKDIR /app
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

USER appuser
ENTRYPOINT ["python", "-m", "whatsapp_platform"]
```

---

## 2. Docker Compose Layout (Development & Production)

### Local Development (`docker-compose.yml`)
```yaml
services:
  app:
    build:
      context: .
      dockerfile: docker/Dockerfile.dev
    volumes:
      - ./src:/app/src
      - ./data:/app/data
    env_file:
      - .env
```

### Production Setup (`docker-compose.prod.yml`)
```yaml
services:
  app:
    image: whatsapp-platform:latest
    restart: unless-stopped
    volumes:
      - neonize_session_data:/app/data
    env_file:
      - .env.production
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: whatsapp_db
      POSTGRES_USER: app_user
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_user -d whatsapp_db"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  neonize_session_data:
  postgres_data:
```

---

## 3. Persistent Volumes & Session Data Safety

File database session Neonize (SQLite atau credentials) **TIDAK BOLEH** disimpan di ephemerally container storage. Selalu dipetakan ke **Docker Volume Persistent** agar session tetap valid walaupun container direstart atau di-redeploy.

---

## References

- [DOC-016: Security Model](./14_security_model.md)
- [DOC-022: CI/CD Pipeline](./20_cicd_pipeline.md)
