# Project details

## Product intent

AI Contractor PayPal is an outcome-based contracting prototype: an AI agent should not be paid for attempting work; it should be paid after a separate system verifies the promised outcome. The project connects contract, AI generation, independent verification, payment, and protected delivery in one demonstrable workflow.

The target users are small businesses and customers commissioning simple digital deliverables who want less ambiguity and fewer disputes. The product makes the acceptance terms visible before work starts and keeps those terms authoritative throughout generation and payment.

## Runtime flow

```text
DRAFT -> SPEC_APPROVED -> GENERATING -> VERIFYING -> VERIFIED
                                      \-> REPAIRING -> VERIFYING (max 2 repairs)
VERIFIED -> PAYMENT_PENDING -> PAID -> DELIVERED
```

A customer submits a brief and budget. The contract generator calls a configured structured-output LLM when available and validates the response with Pydantic. Price and currency remain server-controlled. The customer approves the contract. The page generator asks the same provider for the three source files, while the fallback generator keeps offline development reproducible. Beautiful Soup independently checks the generated HTML. Failed checks are persisted and can trigger at most two AI repair attempts. Only a verified job can create an order. Only a completed, validated payment can download the ZIP.

## File-by-file guide

### Application and configuration

- `app/main.py` creates the FastAPI application, initializes database tables, mounts static assets, serves the UI, and exposes `/health`.
- `app/core/config.py` owns environment-backed settings for SQLite, generated artifacts, the LLM provider, PayPal Sandbox, and settings page protection. It keeps mock/demo defaults safe and never places secrets in frontend code.
- `app/db/database.py` creates the SQLAlchemy engine/session and provides the request-scoped `get_db` dependency.
- `app/db/models.py` defines `Job`, `VerificationRun`, `Payment`, and `AppSetting`. The verification-run table preserves every attempt, including repairs; the payment table records order, capture, amount, currency, and status; the app_settings table stores runtime configuration including custom environment variables.
- `app/schemas/jobs.py` contains Pydantic request/response models for briefs, contracts, approvals, and payment actions.
- `app/api/routes.py` implements the REST surface and enforces server-side lifecycle boundaries. The run worker persists generation, verification, repair attempts, and final status. Checkout is restricted to `VERIFIED`; capture is restricted to the matching pending order; downloads are restricted to completed payment records. It also exposes `/api/settings` endpoints for runtime configuration.

### AI and deliverable services

- `app/services/llm_provider.py` is the real HTTPX OpenAI-compatible provider. It sends structured JSON prompts, parses fenced or plain JSON, and raises a provider error without exposing secrets.
- `app/services/contract_generator.py` asks the model to interpret the brief and return testable criteria. Pydantic validates the response, while server-owned budget/currency override any model-supplied commercial terms. Deterministic fallback is used only when the provider is not configured or temporarily fails.
- `app/services/page_generator.py` asks the configured model for exactly `index.html`, `style.css`, and `script.js`, validates the file set, and writes it to the job directory. It also contains the polished deterministic fallback and `repair_page`, which feeds failed verifier results back to the model.
- `app/services/verifier.py` is the entry point for verification. It delegates to enhanced verification.
- `app/services/verifier_enhanced.py` provides enhanced verification with evidence collection using multiple methods (CSS selector, content check, attribute check, regex). Each check includes detailed evidence of what was found vs expected.
- `app/services/browser_verifier.py` provides browser-based functional verification using Playwright. It tests actual functionality (form submission, navigation scrolling, responsive layout, JavaScript errors) in a real headless browser. Falls back gracefully if Playwright is not installed.
- `app/services/annotated_preview.py` creates visual annotations on the generated page, adding green/red borders to elements to show which verification checks passed or failed.
- `app/services/artifact_service.py` packages only generated HTML/CSS/JS and never exposes the generated directory as a public static directory.

### Payment services

- `app/services/paypal_service.py` supports two explicit modes. `mock` creates local IDs for tests. `sandbox` obtains an OAuth token from `api-m.sandbox.paypal.com`, creates a real Orders API v2 `CAPTURE` order, returns PayPal's approval URL, captures server-side, and validates completed order/capture status, job association, amount, and currency.
- `app/services/runtime_settings.py` manages runtime configuration stored in the database. It supports predefined settings (LLM provider, PayPal configuration, etc.) and custom environment variables. Secret values are encrypted using Fernet when `SETTINGS_ENCRYPTION_KEY` is configured. Custom variables are prefixed with `CUSTOM_` in the database and applied to `os.environ` at runtime.
- `app/templates/index.html` presents the brief, contract approval, verification results, repair-aware status, PayPal approval action, capture confirmation, and download action. Includes a "Settings" button in the header for easy access to the settings page.
- `app/templates/settings.html` provides a user-friendly GUI for configuring runtime settings, including both predefined provider settings and custom environment variables. Each field includes clear labels and explanations of what values should go where. Secret values are write-only and never displayed back.
- `app/static/css/app.css` contains the custom responsive visual system: green/lime verification palette, editorial typography, lifecycle cards, and mobile rules.
- `app/static/js/app.js` coordinates API calls and status polling. It never decides eligibility; it reflects server responses and shows the real PayPal approval URL when Sandbox mode is active.

### Tests, deployment, and documentation

- `tests/test_app.py` covers the health function, contract generation, generated-page verification, mock payment capture, and ZIP packaging. It uses deterministic service-level tests because the local Windows Python 3.14 runtime hangs in Starlette's synchronous `TestClient`; the real API is still available through Uvicorn and `/docs`.
- `requirements.txt` pins FastAPI, HTTPX, SQLAlchemy, Beautiful Soup, Pydantic Settings, Uvicorn, pytest, and cryptography.
- `.env.example` documents all real AI and PayPal Sandbox keys, settings page protection tokens, and encryption keys without containing secrets.
- `.gitignore` prevents credentials, databases, caches, local virtual environments, working files, and generated artifacts entering Git.
- `Dockerfile` provides a Python 3.12 container for Render or another host.
- `render.yaml` describes a production-ready Render web service with persistent disk storage, comprehensive environment variable configuration, and proper secret handling.
- `.github/workflows/ci.yml` installs dependencies and runs tests on pushes and pull requests.
- `migrate_db.py` provides a simple database migration script to add new columns (e.g., `is_custom` for custom environment variables) without requiring a full migration framework.
- `generated/.gitkeep` preserves the local artifact directory while ignoring its contents.
- `LICENSE` is the MIT license.
- `README.md` is the judge-facing setup, product, security, provider, deployment, and demo entry point with hackathon-specific sections.

## API reference

- `POST /api/jobs` — create a draft and return the proposed contract.
- `GET /api/jobs/{id}` — read status, criteria, all verification runs, and payment readiness.
- `POST /api/jobs/{id}/approve-spec` — approve the immutable contract.
- `POST /api/jobs/{id}/run` — queue generation and verification; returns `202`.
- `GET /api/jobs/{id}/preview` — serve the generated HTML preview after generation.
- `GET /api/jobs/{id}/preview/annotated` — serve the annotated preview with visual verification feedback (green/red borders).
- `GET /api/jobs/{id}/versions` — get version history showing all generation attempts with verification results.
- `POST /api/jobs/{id}/paypal/order` — create a mock or real Sandbox order only for `VERIFIED` jobs.
- `POST /api/jobs/{id}/paypal/capture` — capture the job's own pending order and validate the payment response.
- `GET /api/jobs/{id}/download` — release a ZIP only after persisted payment completion.
- `GET /api/settings` — read runtime settings (requires `X-Settings-Token` header when `SETTINGS_ADMIN_TOKEN` is configured). Secret values are never returned.
- `POST /api/settings` — update runtime settings (requires `X-Settings-Token` header). Supports both predefined settings and custom environment variables (prefixed with `CUSTOM_`).

## Environment modes

### Offline/local mode

```env
LLM_PROVIDER=demo
PAYPAL_MODE=mock
```

This mode requires no provider credentials and is used by the automated tests.

### Judge/demo mode

```env
LLM_PROVIDER=openai-compatible
LLM_API_KEY=...
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYPAL_API_BASE_URL=https://api-m.sandbox.paypal.com
PAYPAL_RETURN_URL=http://localhost:8000/
PAYPAL_CANCEL_URL=http://localhost:8000/
```

All credentials stay server-side. The browser receives only a PayPal approval URL and non-sensitive order/capture identifiers.

### Settings page and custom environment variables

The application includes a runtime settings page at `/settings` that allows configuration without editing source files. A "Settings" button in the main page header provides easy access:

- **Predefined settings**: LLM provider (API key, model, base URL, timeout), PayPal configuration (mode, client ID, client secret, API URLs), and generated directory
- **Custom environment variables**: Users can define additional environment variables (e.g., third-party API keys, feature flags) through the settings UI. These are stored with a `CUSTOM_` prefix in the database and applied to `os.environ` at runtime
- **User-friendly GUI**: Each setting field includes clear labels and explanations of what values should go where, making configuration easy without needing to understand the underlying code
- **Security**: Secret values are encrypted using Fernet when `SETTINGS_ENCRYPTION_KEY` is configured. In production, `SETTINGS_ADMIN_TOKEN` is required to access the settings page
- **Persistence**: Settings are stored in the `app_settings` database table and loaded at application startup

## Security and production hardening

The approved contract is stored before generation and the AI cannot modify its price or criteria. PayPal order creation is gated by independent verification. Capture checks the pending order association and, in Sandbox mode, PayPal's returned status, capture status, job reference, amount, and currency. Delivery checks the database independently, so a guessed URL or forged browser callback cannot unlock the ZIP.

Runtime settings are protected by `SETTINGS_ADMIN_TOKEN` in production environments. Secret values are encrypted using Fernet when `SETTINGS_ENCRYPTION_KEY` is configured. Custom environment variables are treated as secrets and never displayed back to the user.

For production, run generated pages in an isolated worker/container with outbound network disabled, verify PayPal webhook signatures, add idempotency keys, use PostgreSQL and object storage (with persistent disk for Render), add authentication/ownership, add a CSP and sandboxed preview origin, use isolated Playwright browser tests, and configure strong `SETTINGS_ADMIN_TOKEN` and `SETTINGS_ENCRYPTION_KEY` values. Move long-running work from FastAPI `BackgroundTasks` to Redis/RQ when scaling beyond a single process.

## Submission readiness checklist

- [x] Real LLM integration path for contract, deliverable, and repair work.
- [x] Customer explicitly approves the contract.
- [x] Independent verifier checks the deliverable against approved criteria.
- [x] Enhanced verification with evidence collection and multiple verification methods.
- [x] Browser-based functional verification with Playwright (optional but recommended).
- [x] Visual feedback through annotated preview with verification results.
- [x] Version history tracking for all generation attempts.
- [x] Real PayPal Sandbox order path with server-side OAuth, creation, approval URL, capture, and response verification.
- [x] ZIP download remains blocked until the database records completed payment.
- [x] README, project details, public-repository guidance, and MIT license.
- [x] Runtime settings page with custom environment variable support and user-friendly GUI.
- [x] Production-ready Render deployment configuration with persistent storage.
- [x] Secrets generation helper script for production deployment.
- [x] Database migration script for adding new columns without requiring full migration framework.
- [x] Settings button in main page header for easy access to configuration.
- [x] Enhanced documentation explaining the settings page GUI and migration process.
- [ ] Public GitHub repository URL confirmed in the hackathon submission.
- [ ] Public YouTube demo under three minutes recorded and linked in the hackathon submission.

## Database migrations

The project uses a simple migration script approach rather than a full migration framework:

- `migrate_db.py` provides a standalone script to add new columns to existing database tables
- The script checks if a column exists before attempting to add it, making it safe to run multiple times
- Run `python migrate_db.py` after updating the code to add new database features:
  - `is_custom` column to `app_settings` table for custom environment variables
  - `generation_versions` table for version history tracking
  - `approval_url`, `order_request_id`, and `capture_request_id` columns to `payments` table for PayPal integration
- For new installations, the application automatically creates the database schema on startup

## Three-minute demo script

Submit a brief, approve the six criteria, show generated work and verification results, attempt the locked download, create a real Sandbox order, open PayPal approval with a Sandbox buyer, return to the app, capture server-side, show the capture ID, and download the ZIP. Keep the key message visible: verification—not the model's own claim—makes payment eligible.

**Optional settings page demo**: Show how the settings page at `/settings` allows configuring AI and PayPal providers without editing source files, and demonstrate adding a custom environment variable for additional configuration flexibility.
