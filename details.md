# Project details

## Product intent

AI Contractor PayPal is an outcome-based contracting prototype: an AI agent should not be paid for attempting work; it should be paid after a separate system verifies the promised outcome. It connects a customer brief, AI-generated browser software, independent verification, payment, and protected source-package delivery in one workflow.

The target users are small businesses and customers commissioning simple digital deliverables who want less ambiguity and fewer disputes. The product makes the acceptance terms visible before work starts and keeps those terms authoritative throughout generation and payment.

## Runtime flow

```text
DRAFT -> SPEC_APPROVED -> GENERATING -> VERIFYING -> VERIFIED or BILLABLE or FAILED
                                      \-> REPAIRING -> VERIFYING (max 2 repairs)
VERIFIED/BILLABLE -> PAYMENT_PENDING -> PAID -> DELIVERED
PAYMENT_PENDING -> CANCELLED -> VERIFIED/BILLABLE
```

A customer submits a brief and budget. NVIDIA NIM drafts the prompt-specific contract and validates the response with Pydantic. Price and currency remain server-controlled. The customer approves the contract. NIM generates a self-contained `index.html`, `style.css`, and `script.js` browser application. Beautiful Soup and optional Playwright checks verify its product-specific acceptance markers, structure, and browser rendering. Failed checks are persisted and can trigger at most two AI repair attempts. In API mode, provider failures never silently substitute a static template. The explicit offline demo mode is only a generic fixture for local tests. When final verification has passed criteria, each criterion receives an equal share of the approved budget; a job with any passing criteria becomes billable for those shares, while a job with no passing criteria remains failed and cannot be charged. PayPal order creation and capture use that computed amount. Only a completed, validated payment can download the ZIP.

The generated deliverable is a static browser application; it does not include a server or external API integration. A working browser preview must deliver its client-side files to the browser, so the payment gate protects the source ZIP endpoint and delivery workflow, not secrecy from someone inspecting the preview.

## File-by-file guide

### Application and configuration

- `app/main.py` creates the FastAPI application, initializes database tables, mounts static assets, serves the UI, and exposes `/health`.
- `app/core/config.py` owns environment-backed settings for SQLite, generated artifacts, NVIDIA NIM, PayPal Sandbox, and settings page protection. It never places secrets in frontend code.
- `app/db/database.py` creates the SQLAlchemy engine/session and provides the request-scoped `get_db` dependency.
- `app/db/models.py` defines `Job`, `VerificationRun`, `Payment`, and `AppSetting`. The verification-run table preserves every attempt, including repairs; the payment table records order, capture, amount, currency, and status; the app_settings table stores runtime configuration including custom environment variables.
- `app/schemas/jobs.py` contains Pydantic request/response models for briefs, contracts, approvals, and payment actions.
- `app/api/routes.py` implements the REST surface and enforces server-side lifecycle boundaries. The run worker persists generation, verification, repair attempts, and final status. Checkout accepts `VERIFIED` and partially passing `BILLABLE` jobs, calculates equal criterion shares, and captures only the matching order amount. Cancellation restores a retryable state. Downloads require a completed payment record.

### AI and deliverable services

- `app/services/llm_provider.py` is the real HTTPX OpenAI-compatible provider. It sends structured JSON prompts, parses fenced or plain JSON, and raises a provider error without exposing secrets.
- `app/services/contract_generator.py` asks NVIDIA NIM to interpret a software brief and return product-specific testable criteria. Pydantic validates the response, while server-owned budget/currency override any model-supplied commercial terms. The optional demo mode supplies deterministic fixture criteria only for local tests.
- `app/services/page_generator.py` asks the configured NVIDIA NIM model for a working browser application in exactly `index.html`, `style.css`, and `script.js`, validates the file set, and writes it to the job directory. `repair_page` feeds failed verifier results back to the configured model. The optional demo mode supplies a generic template fixture only for local tests.
- `app/services/verifier.py` is the entry point for verification. It delegates to enhanced verification.
- `app/services/verifier_enhanced.py` checks legacy records with their existing selectors and checks new generated software against approved product markers, with evidence for each result.
- `app/services/browser_verifier.py` smoke-checks generated software rendering, criterion visibility, mobile width, and JavaScript errors with Playwright. Existing legacy jobs retain their original selector checks. If Playwright or Chromium is unavailable, browser checks are explicitly marked skipped.
- `app/services/annotated_preview.py` inlines generated CSS into an isolated read-only preview, strips JavaScript and inline event handlers, adds green/red verification borders, and labels the view as payment-gated. The HTML and CSS used to display the preview remain visible to the browser; application behavior is kept in the gated JavaScript file.
- `app/services/artifact_service.py` packages only `index.html`, `style.css`, and `script.js`; the generated directory is never mounted as public static content.

### Payment services

- `app/services/paypal_service.py` supports two explicit modes. `mock` creates local IDs for tests. `sandbox` obtains an OAuth token from `api-m.sandbox.paypal.com`, creates a real USD-only Orders API v2 `CAPTURE` order, returns PayPal's approval URL, captures server-side, and validates completed order/capture status, job association, amount, and USD currency.
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
- `POST /api/jobs/{id}/paypal/order` — create a mock or real Sandbox order for `VERIFIED` or `BILLABLE` jobs using only the passed criteria's budget shares.
- `POST /api/jobs/{id}/paypal/reset` — abandon a stuck local pending order and restore the job to its verified or billable state so a fresh order can be created.
- `POST /api/jobs/{id}/paypal/capture` — capture the job's own pending order and validate the payment response.
- `GET /api/jobs/{id}/download` — release a ZIP only after persisted payment completion.
- `GET /api/settings` — read runtime settings (requires `X-Settings-Token` header when `SETTINGS_ADMIN_TOKEN` is configured). Secret values are never returned.
- `POST /api/settings` — update runtime settings (requires `X-Settings-Token` header). Supports both predefined settings and custom environment variables (prefixed with `CUSTOM_`).

## Environment modes

### Offline/local mode

```env
LLM_PROVIDER=nvidia-nim
PAYPAL_MODE=mock
```

Demo mode is not a production generation mode. It uses a static fixture so the automated tests do not spend API credits; configure an NIM model and API key for customer contract and software generation.

### Judge/demo mode

```env
LLM_PROVIDER=nvidia-nim
LLM_API_KEY=...
LLM_MODEL=your-nvidia-nim-model-id
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
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
- **Environment values**: Non-secret fields show the active values from the project-root `.env` file or saved runtime overrides. Secret values are never returned; the GUI only reports whether they are configured.

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
