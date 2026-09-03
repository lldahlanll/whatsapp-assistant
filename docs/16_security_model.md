# DOC-016 · Security & Threat Model Document

> **Status:** Draft  
> **Version:** 1.0.0  
> **Last Updated:** 2026-08-03  
> **Owner:** Security Engineer + Senior Developer  

---

## 1. Assets Yang Perlu Dilindungi

| Asset | Sensitivity | Lokasi |
|-------|-------------|--------|
| Neonize session credentials | CRITICAL | Database, file sistem |
| API keys (OpenAI, Gemini) | HIGH | Environment variables |
| Database credentials | HIGH | Environment variables |
| Message content | MEDIUM | Database |
| Contact data (JID, phone) | MEDIUM | Database |
| Source code | LOW | Git repository |

---

## 2. STRIDE Threat Model

### S — Spoofing (Identitas Palsu)

| Threat | Scenario | Risk | Mitigation |
|--------|----------|------|-----------|
| S-001 | Attacker inject pesan palsu ke event bus | Medium | Event bus hanya accessible in-process; tidak ada network exposure |
| S-002 | Attacker impersonate WhatsApp user | Low | E2EE dihandle oleh Neonize/Whatsmeow; kita tidak bisa verify beyond JID |

### T — Tampering (Modifikasi Data)

| Threat | Scenario | Risk | Mitigation |
|--------|----------|------|-----------|
| T-001 | Attacker modifikasi message di database | Medium | Database access control, file permission ketat |
| T-002 | Attacker modifikasi session file | HIGH | File permission 600, enkripsi session (future) |
| T-003 | Attacker modifikasi konfigurasi env file | HIGH | .env tidak boleh di-commit, proper file permission |

### R — Repudiation (Penyangkalan)

| Threat | Scenario | Risk | Mitigation |
|--------|----------|------|-----------|
| R-001 | Tidak ada audit trail untuk command yang dieksekusi | Medium | `command_logs` table, structured logging |
| R-002 | Session activity tidak tercatat | Low | Session status changes selalu di-log dan di-save ke DB |

### I — Information Disclosure (Kebocoran Informasi)

| Threat | Scenario | Risk | Mitigation |
|--------|----------|------|-----------|
| I-001 | API keys ter-log ke file | CRITICAL | `SecretStr` di Pydantic — tidak pernah di-serialize |
| I-002 | Message content ter-log (privacy) | HIGH | Log hanya metadata, bukan isi pesan (configurable) |
| I-003 | Database credentials ter-commit ke git | CRITICAL | .gitignore .env, pre-commit secret scanning |
| I-004 | Stack trace ter-kirim ke WhatsApp user | Medium | Error handling layer filter technical details |
| I-005 | Session file ter-commit ke git | CRITICAL | .gitignore data/ folder |

### D — Denial of Service (Serangan Ketersediaan)

| Threat | Scenario | Risk | Mitigation |
|--------|----------|------|-----------|
| D-001 | Flood pesan dari satu user | Medium | Rate limiting per JID (future feature) |
| D-002 | AI API cost DoS (flood request ke LLM) | HIGH | Rate limiting + monthly budget alert |
| D-003 | Database disk full | Medium | Retention policy, monitoring |
| D-004 | Memory leak (long-running process) | Medium | Memory monitoring, periodic health checks |

### E — Elevation of Privilege (Eskalasi Hak Akses)

| Threat | Scenario | Risk | Mitigation |
|--------|----------|------|-----------|
| E-001 | User biasa eksekusi admin command | Medium | Command permission system (role-based) |
| E-002 | Process berjalan sebagai root di container | Medium | Docker non-root user (UID 1000) |
| E-003 | Dependency dengan known vulnerability | Medium | pip-audit di CI, automatic Dependabot |

---

## 3. Security Controls

### 3.1 Secret Management

```python
# BENAR — menggunakan SecretStr
class Settings(BaseSettings):
    openai_api_key: SecretStr | None = None
    database_url: SecretStr  # Berisi password
    
    def get_openai_key(self) -> str:
        if self.openai_api_key is None:
            raise MissingConfigurationException("OPENAI_API_KEY")
        return self.openai_api_key.get_secret_value()

# SALAH — jangan pernah
logger.info("Connecting to OpenAI", api_key=settings.openai_api_key)  # EXPOSED!
```

**Aturan absolut:**
- API keys tidak pernah di-log (bahkan di DEBUG level)
- API keys tidak pernah di-hardcode dalam kode
- `.env` file selalu masuk `.gitignore`
- `data/` folder (session files) selalu masuk `.gitignore`

---

### 3.2 Input Validation

```python
# Validasi JID sebelum kirim pesan
def validate_jid(jid: str) -> bool:
    """JID harus dalam format yang valid."""
    if not jid:
        return False
    parts = jid.split("@")
    if len(parts) != 2:
        return False
    phone, domain = parts
    if domain not in ("s.whatsapp.net", "g.us"):
        return False
    return phone.isdigit() and len(phone) >= 7

# Validasi panjang pesan
MAX_TEXT_LENGTH = 4096  # WhatsApp limit
MAX_COMMAND_ARGS_LENGTH = 1000

def validate_message_body(body: str) -> None:
    if len(body) > MAX_TEXT_LENGTH:
        raise MessageTooLongException(len(body), MAX_TEXT_LENGTH)
    if not body.strip():
        raise ValueError("Message body cannot be empty or whitespace only")
```

---

### 3.3 Logging Privacy

```python
# Konfigurasi: apakah log message content?
LOG_MESSAGE_CONTENT: bool = False  # Default: False untuk privacy

def sanitize_log_context(context: dict) -> dict:
    """Remove atau mask sensitive fields sebelum logging."""
    sensitive_keys = {"body", "content", "password", "api_key", "token", "secret"}
    return {
        k: "[REDACTED]" if k in sensitive_keys else v
        for k, v in context.items()
    }
```

---

### 3.4 File System Security

```
Permissions yang harus diset:
  .env                → chmod 600 (owner read/write only)
  data/neonize.db     → chmod 600
  data/app.db         → chmod 600
  
.gitignore wajib berisi:
  .env
  .env.*
  data/
  *.db
  *.sqlite
  logs/
```

---

### 3.5 Docker Security

```dockerfile
# Dockerfile — non-root user
FROM python:3.13-slim

# Create non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Set working directory
WORKDIR /app

# Copy files dengan ownership yang benar
COPY --chown=appuser:appgroup . .

# Install dependencies
RUN pip install uv && uv sync --frozen

# Switch ke non-root user
USER appuser

# Tidak expose port yang tidak diperlukan
# Platform ini tidak membuka server HTTP (kecuali future REST API)
```

---

### 3.6 Dependency Security

```yaml
# Di CI pipeline — wajib ada:
- name: Security audit
  run: |
    uv run pip-audit  # Check known CVEs
    uv run bandit -r src/  # SAST scan
    uv run safety check  # Alternative CVE check
```

---

## 4. WhatsApp Terms of Service Compliance

| Rule | Implementation |
|------|---------------|
| Tidak spam | Rate limiting per JID, human-like delays |
| Tidak automation abuse | Platform ini hanya untuk personal/business automation yang legitimate |
| Session sharing dilarang | Session file tidak dishare, satu instance per nomor |
| Bulk messaging harus opt-in | Broadcast feature hanya ke kontak yang sudah interact |

---

## 5. Incident Response

### Jika Session Bocor (Paling Kritis)
1. Segera logout session dari aplikasi WhatsApp
2. Hapus session database
3. Rotasi semua credentials yang mungkin terekspos
4. Audit log untuk aktivitas mencurigakan
5. Report ke tim keamanan

### Jika API Key Bocor
1. Revoke key dari provider (OpenAI/Google dashboard)
2. Generate key baru
3. Update environment variable di semua deployment
4. Audit penggunaan API key di provider dashboard

---

## 6. Security Checklist (Pre-Deployment)

- [ ] `.env` tidak ada di git history (`git log --all --grep .env`)
- [ ] `data/` folder tidak ada di git
- [ ] Docker container berjalan sebagai non-root user
- [ ] `pip-audit` tidak ada critical CVE
- [ ] `bandit` pass tanpa HIGH severity
- [ ] Semua secrets menggunakan `SecretStr`
- [ ] Log tidak mengandung message content (jika privacy diperlukan)
- [ ] File permission: `.env` → 600, `data/*.db` → 600

---

## References

- [DOC-006: Tech Stack](./06_tech_stack.md)
- [DOC-021: Observability](./19_observability.md)
- [DOC-022: CI/CD Pipeline](./20_cicd_pipeline.md)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [STRIDE Threat Modeling](https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats)
