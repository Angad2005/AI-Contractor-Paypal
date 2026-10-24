# AI Contractor PayPal: Project Details

This document describes the product, its runtime behavior, configuration, APIs, data model, verification and payment rules, deployment, tests, and known limitations. It is intended as the detailed technical companion to [README.md](README.md).

## 1. Project summary

AI Contractor PayPal is an outcome-based software contracting prototype. A customer describes a small browser-based product and sets a budget. The AI proposes a concrete acceptance contract, the customer approves it, and an AI contractor generates the product. A separate verifier checks the generated files against the approved criteria. PayPal checkout charges only for criteria that passed; the source ZIP is released only after the server records a validated completed payment.

The product is intended to make the terms of a small digital-services engagement visible before work begins and to tie payment to observable acceptance checks rather than to the model's assertion that it has completed the task.

### Submission-facing description

AI Contractor PayPal turns a plain-language software brief into an approved acceptance contract, generates a working browser application, verifies its contract criteria, and enables PayPal payment for passed outcomes. After payment confirmation, the customer can download the HTML, CSS, and JavaScript source as a ZIP. The project uses NVIDIA NIM for contract analysis, application generation, and repair, and PayPal Developer Sandbox for test checkout and server-side capture.

## 2. Hackathon requirements coverage

| Submission item | Project evidence |
|---|---|
| Project built with developer tools | Python 3.12-compatible FastAPI app, LangChain/LangGraph workflow, SQLite/SQLAlchemy persistence, Playwright browser checks, Docker, and GitHub Actions CI. |
| Text description | Product summary and feature/workflow description in `README.md`; technical detail in this file. |
| Functional demo | Run locally using the instructions in `README.md`; configure an NVIDIA NIM key for real model requests. PayPal defaults to mock mode until Sandbox credentials are configured. |
| AI tools identified and explained | NVIDIA NIM is the configured model API. The default model is `nvidia/nemotron-3.5-bolt-e4b`; it drafts acceptance contracts, generates the app files, and repairs failed criteria. LangChain and LangGraph orchestrate specialist workflow steps. |
| Payment tool identified and explained | PayPal Orders API v2 Developer Sandbox creates and captures USD orders; server-side checks protect delivery. |
| Public code repository | <https://github.com/Angad2005/AI-Contractor-Paypal> |
| Demo video | Record and link a public video shorter than three minutes in the hackathon submission. No demo-video URL is currently maintained in this repository. |

The final submission should include the public video URL and a confirmed end-to-end Sandbox payment demonstration. The repository's README checklist tracks these as submission actions.

## 3. NVIDIA NIM model and API configuration

### Default model

The project default is **`nvidia/nemotron-3.5-bolt-e4b`**. It is selected as a fast-response starting point for this prototype. This is a model choice, not a measured or guaranteed response-time claim: latency and output quality depend on NVIDIA service availability, account access and quotas, network conditions, prompt length, and service load.

The model can be changed to another NVIDIA NIM model available to the user's account by changing `LLM_MODEL` in `.env`, deployment environment variables, or the `/settings` page. Model access is controlled by the NIM account and endpoint. Users should choose a model based on their access and desired speed/capability balance.

### NVIDIA-only `.env.example`

The tracked [`.env.example`](.env.example) intentionally contains only the four NVIDIA NIM settings below. It does not include PayPal credentials, application/database options, or production settings-page secrets.

```env
LLM_PROVIDER=nvidia-nim
LLM_API_KEY=your_nvidia_nim_api_key
LLM_MODEL=nvidia/nemotron-3.5-bolt-e4b
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
```

Copy it to `.env` and replace the placeholder with an API key from an account authorized for the chosen model. Do not commit a populated `.env` file or expose the key in browser code. `.gitignore` excludes `.env`.

The NVIDIA API is OpenAI-compatible. Requests go to the configured base URL plus `/chat/completions`; the key is used as a server-side authorization credential. NVIDIA NIM requests ask for JSON output, and the app parses/validates the returned JSON. Provider errors are surfaced to the user/job rather than silently switching to the offline test fixture.

When `LLM_MODEL` names a model other than `nvidia/nemotron-3.5-bolt-e4b`, the direct NIM provider may retry with `nvidia/nemotron-3.5-bolt-e4b` after certain retryable errors. The configured model is attempted first. For predictable behavior, use the default model directly or ensure the account also has access to the fallback.

Other OpenAI-compatible endpoints have limited support in code, including LM Studio and Groq response-format handling. They are not represented in `.env.example`; the repository's documented/default setup is NVIDIA NIM.

### Remaining application configuration

NIM is the only provider configuration in `.env.example`; it is not the complete list of environment variables understood by the application. `app/core/config.py` also defines these defaults:

| Variable | Development default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | Environment label; production affects settings-page access and secret storage requirements. |
| `DATABASE_URL` | `sqlite:///./app.db` | SQLAlchemy database connection. PostgreSQL URLs are also adapted to the psycopg driver. |
| `GENERATED_DIR` | `generated` | Location for generated job files and ZIP packages. |
| `PAYPAL_MODE` | `mock` | `mock` for local/testing checkout; `sandbox` for PayPal Developer Sandbox. |
| `PAYPAL_CLIENT_ID` | empty | PayPal Sandbox REST app client ID. |
| `PAYPAL_CLIENT_SECRET` | empty | PayPal Sandbox REST app secret; server-side only. |
| `PAYPAL_API_BASE_URL` | `https://api-m.sandbox.paypal.com` | PayPal Sandbox API base. |
| `PAYPAL_RETURN_URL` | `http://localhost:8000/api/paypal/return` | PayPal buyer return URL. |
| `PAYPAL_CANCEL_URL` | `http://localhost:8000/api/paypal/cancel` | PayPal buyer cancel URL. |
| `SETTINGS_ADMIN_TOKEN` | empty | Protects settings API in production; a token is required when `APP_ENV=production`. |
| `SETTINGS_ENCRYPTION_KEY` | empty | Fernet key for encrypted secret values stored by the runtime settings UI. Required in production when saving secret runtime settings. |

Set these independently in the deployment environment or through the settings UI as appropriate. In production, prefer environment-managed secrets and a persistent database. Generate settings-page secrets with `python generate_secrets.py`; never add the resulting values to source control.

## 4. End-to-end customer workflow

1. **Submit a brief and budget.** `POST /api/jobs` accepts a brief of 20-2,000 characters and a positive USD budget up to 10,000 USD. The default budget is 10 USD.
2. **Draft the contract.** The configured model proposes named sections, features, and concrete criteria. The LangGraph analyst prompt requests 4-10 criteria; the direct JSON fallback prompt requests 4-12. Pydantic validates the model response. The application, not the model, owns the commercial terms: the submitted budget is retained and currency is USD.
3. **Approve the contract.** The user must explicitly approve the proposed specification before generation can start. The approved specification is persisted and used for subsequent generation, verification, and billing.
4. **Generate the product.** The AI workflow creates exactly three non-empty files: `index.html`, `style.css`, and `script.js`. The generated application is a static browser product; it is not a server-side application and should not rely on a backend or network services.
5. **Verify the deliverable.** HTML acceptance checks run against the approved criteria. When Playwright and Chromium are installed, browser checks also inspect rendering, visible acceptance markers, mobile overflow, and JavaScript errors. A missing browser runtime is represented as a skipped check, not a passing browser test.
6. **Repair failed work.** Failed criteria are sent to the AI repair workflow. A run can attempt up to two repairs after its initial generation. A job can be rebuilt while unpaid, up to six total verification attempts.
7. **Calculate the payable amount.** The approved budget is split across criteria in cents; any remainder cents are allocated in criterion order. Only passed, non-skipped criteria are billable. A zero-pass job cannot check out. All criteria passing yields `VERIFIED`; some criteria passing yields `BILLABLE`.
8. **Create PayPal order.** Checkout is available for a completed payable verification run. The order amount is computed server-side from passed criterion shares. The default local `mock` mode produces mock IDs; `sandbox` creates a real USD PayPal order and approval URL.
9. **Approve and capture.** The buyer approves the order at PayPal. The app resumes through its return route and the client requests server-side capture. Capture validation checks the order's status, capture status, job association, amount, and currency.
10. **Deliver the ZIP.** The download endpoint checks persisted payment state and job status. It creates and returns a ZIP containing the generated source files only after completed payment has been recorded.

### Lifecycle states

```text
DRAFT -> SPEC_APPROVED -> GENERATING -> VERIFYING
                                      -> REPAIRING -> VERIFYING (up to 2 repairs per run)
                                      -> VERIFIED / BILLABLE / FAILED
VERIFIED or BILLABLE -> PAYMENT_PENDING -> PAID -> DELIVERED
PAYMENT_PENDING -> CANCELLED -> VERIFIED or BILLABLE
```

`REBUILDING` is used when starting a replacement build for an unpaid completed job. It clears the previous preview path before rebuilding so a failed rebuild cannot leave an old deliverable available for checkout.

## 5. AI workflow and generated deliverable

### Contract analysis

`app/services/contract_generator.py` first invokes the LangGraph contract analyst with LangChain's OpenAI-compatible chat client. Its prompt requests 4-10 criteria. If that path raises or produces no result, it uses the direct JSON-completion provider, whose prompt requests 4-12 criteria and explicitly asks for an app shell and core workflow criterion. In either path, the result is validated as a `Contract`; model-supplied price/currency cannot override the server-owned budget and USD currency. An empty criteria list is rejected.

### Application generation and repair

`app/services/page_generator.py` first tries the LangGraph workflow:

- **Architect:** produces semantic HTML and places `data-acceptance-key` markers on elements representing approved criteria.
- **Stylist:** produces responsive CSS and includes reduced-motion considerations.
- **Engineer:** produces client-side JavaScript for interactions and is prompted not to make backend or remote network calls.
- **Assembler:** combines the output into the required file set.
- **Repair specialist:** receives the failed checks and current files and attempts targeted corrections.

The graph runs styling and client-side engineering after the HTML stage, then assembles the result. If the agent workflow raises, the page generator falls back to a direct JSON-completion request for the three files. Both paths use the configured LLM in normal provider mode. The explicit `LLM_PROVIDER=demo` mode is a deterministic local fixture for tests, not an AI-generated customer deliverable.

Before writing, the page generator validates the three required files, normalizes/creates links to `style.css` and deferred `script.js`, adds a doctype where absent, and writes the files in `GENERATED_DIR/<job-id>/`. A malformed or incomplete AI response fails generation rather than being packaged as a valid deliverable.

### Verification behavior

- **Product-specific HTML checks:** Each approved criterion is checked for a corresponding `data-acceptance-key` element. The `app_shell`, `responsive`, `navigation`, and `core_workflow` criteria have specialized structural/control checks.
- **Legacy compatibility checks:** Older landing-page fixture contracts retain checks for hero, features, pricing, signup, responsive viewport, navigation, and semantic HTML.
- **Browser checks:** Playwright opens the generated page, checks visible content and criterion markers, tests a 375px viewport for horizontal overflow, and records browser console/runtime errors.
- **Optional browser dependency:** If Playwright or Chromium is unavailable, browser verification is marked skipped. Skipped browser checks do not count as passed acceptance criteria.
- **Repair history:** Verification results and each generation version are persisted. The UI can show history and annotated feedback.

### Preview and ZIP delivery

`GET /api/jobs/{id}/preview` serves the generated page with sandbox and `nosniff` response headers. The annotated preview inlines CSS, removes scripts and inline event handlers, marks matching elements green/red, includes pass/fail/skip counts, and makes the view inert/read-only.

The preview has to send HTML and CSS to the browser to render it. Therefore the payment gate protects source-package delivery; it does not make markup or visual styling secret from someone inspecting browser content. The packaged ZIP contains `index.html`, `style.css`, and `script.js` and is generated within the job's artifact directory.

## 6. Billing and PayPal

### Outcome-based billing

The approved contract's criteria define the billable units. The server converts the approved total budget to cents, divides it across the criteria, and assigns remainder cents to the first criteria in order. A criterion is billable only when its latest criterion-level result passed and was not skipped. Browser smoke checks sharing a key do not replace the actual criterion-level result.

The response exposes total budget, amount payable, passed/total criteria, and an itemized bill. If no criteria passed, checkout is rejected. Partial success is billable for passed shares; it is not billed as the full budget.

### PayPal modes

- **Mock:** Default local mode. Produces mock order and capture IDs for deterministic development/tests; it does not contact PayPal and is not evidence of a real payment.
- **Sandbox:** Uses PayPal OAuth and Orders API v2 with `CAPTURE` intent. It creates USD orders, returns PayPal's approval URL, and captures server-side after buyer approval.

For Sandbox mode, set:

```env
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=your_sandbox_client_id
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret
PAYPAL_API_BASE_URL=https://api-m.sandbox.paypal.com
PAYPAL_RETURN_URL=http://localhost:8000/api/paypal/return
PAYPAL_CANCEL_URL=http://localhost:8000/api/paypal/cancel
```

The order stores the job ID in PayPal `reference_id` and `custom_id`. The server validates the captured order association, completed order/capture status, exact expected amount, and USD currency before persisting payment completion. Repeated completed capture calls return the saved capture as idempotent. Order and capture request IDs are retained to support request idempotency.

The app supports USD only. A Sandbox business seller must accept USD. If PayPal reports unsupported payee currency, adjust that seller's receiving preferences or use credentials for an eligible Sandbox seller, reset the failed pending order, and create a new order. The app does not silently convert currency.

The browser return URL alone is not proof of payment. The app looks up the pending payment, then performs capture server-side. Delivery independently checks the database for a completed payment and a paid/delivered job state before creating the ZIP.

## 7. User interface and runtime settings

### Main page

`app/templates/index.html`, `app/static/css/app.css`, and `app/static/js/app.js` implement the browser dashboard. The UI coordinates job creation, specification approval, generation and status polling, preview/verification display, repair/version history, PayPal order approval, capture status, and download. Eligibility is determined by the API, not client-side UI state.

### Settings page

`/settings` is a web UI and API for runtime configuration. The page supports the LLM provider, API key, model, base URL; PayPal mode, client ID/secret, API URLs; generated artifact directory; and user-defined custom environment variables.

- In non-production mode, the settings API is accessible without an admin token if none is configured.
- In production, configure `SETTINGS_ADMIN_TOKEN`; settings API calls require `X-Settings-Token`.
- Secret fields are write-only in the UI/API responses.
- If `SETTINGS_ENCRYPTION_KEY` is set, secret database values are encrypted with Fernet. In production, saving secret settings without this key fails explicitly.
- Process and `.env` values take precedence over stale database overrides at startup; values changed through the settings UI apply to the current process.
- Custom settings are stored with a `CUSTOM_` prefix and treated as secrets.
- Deployment environment variables remain the production source of truth.

Generate both production settings values with:

```bash
python generate_secrets.py
```

Store the generated values in the deployment's secret environment configuration; do not commit them.

## 8. HTTP API reference

All application API routes are under `/api`. Interactive OpenAPI documentation is available at `/docs`.

| Method and path | Purpose |
|---|---|
| `POST /api/jobs` | Create a job and draft its AI acceptance contract. Request: `prompt` (20-2,000 chars), optional `budget` (default 10 USD, greater than 0 and at most 10,000). |
| `GET /api/jobs/{job_id}` | Return job status, contract, verification runs, billing summary, preview readiness, payment status, and action eligibility. |
| `POST /api/jobs/{job_id}/approve-spec` | Approve the contract. Requires `{"approved": true}`. |
| `POST /api/jobs/{job_id}/run` | Queue generation and verification as a FastAPI background task; returns HTTP 202. |
| `GET /api/jobs/{job_id}/preview` | Serve the generated preview when available. |
| `GET /api/jobs/{job_id}/preview/annotated` | Serve a read-only preview with visual verification annotations. |
| `GET /api/jobs/{job_id}/versions` | Return version attempt numbers, timestamps, checks, pass counts, and browser-check availability. |
| `POST /api/jobs/{job_id}/paypal/order` | Create/reuse a PayPal order for the computed payable amount. Accepts optional `PayPal-Request-Id` header. |
| `POST /api/jobs/{job_id}/paypal/reset` | Cancel a pending checkout locally so a new order can be made. |
| `GET /api/jobs/{job_id}/paypal/diagnostics` | Return a limited set of fields for the job's own PayPal order; does not expose the full PayPal response. |
| `POST /api/jobs/{job_id}/paypal/capture` | Capture and validate the pending order. Optional body: `{"order_id": "..."}`; accepts optional `PayPal-Request-Id` header. |
| `GET /api/jobs/{job_id}/download` | Return a ZIP only after persisted payment completion; otherwise returns HTTP 403. |
| `GET /api/paypal/return` | PayPal buyer return route; redirects the browser to the dashboard. It does not itself mark payment completed. |
| `GET /api/paypal/cancel` | PayPal cancellation route; updates a still-pending local payment to cancelled. |
| `GET /api/settings` | Return visible settings, never secret values. Requires `X-Settings-Token` in protected production. |
| `POST /api/settings` | Save runtime settings; requires `X-Settings-Token` in protected production. |
| `GET /health` | Return service health and environment label. |

## 9. Data model and persistence

SQLAlchemy models in `app/db/models.py`:

- **`Job`**: prompt, title, approved contract JSON, USD budget/currency, lifecycle status, preview file path, creation time.
- **`VerificationRun`**: attempt number, pass/fail state, timestamp, JSON results and evidence for each check.
- **`GenerationVersion`**: generated HTML/CSS/JS content and separate HTML/browser verification results for each attempt.
- **`Payment`**: one record per job, PayPal order/capture IDs, approval URL, idempotency request IDs, amount, currency, status.
- **`AppSetting`**: runtime configuration overrides, secret/custom flags, and update time.

`app/main.py` creates tables and applies additive legacy-column updates at startup. `migrate_db.py` provides the same action for manual upgrades. The migration checks existing columns before adding them and can be safely run more than once. Updates include settings custom-variable metadata and PayPal approval/idempotency fields. New tables are created with SQLAlchemy metadata.

SQLite is the local default. A PostgreSQL URL is supported through psycopg. Generated artifacts are stored on the local filesystem under `GENERATED_DIR`; deploys need persistent storage if files must survive restarts.

## 10. Repository map

| Path | Responsibility |
|---|---|
| `app/main.py` | FastAPI construction, table initialization, settings load, static mount, UI routes, health route. |
| `app/core/config.py` | Environment-backed settings and project-root `.env` loading. |
| `app/api/routes.py` | Job lifecycle API, verification worker, previews, settings, PayPal and download routes. |
| `app/schemas/jobs.py` | Pydantic request, contract, and response schema definitions. |
| `app/db/database.py` | SQLAlchemy engine/session, request-scoped DB dependency, additive legacy migration. |
| `app/db/models.py` | Job, verification, payment, settings, and version-history models. |
| `app/services/llm_provider.py` | OpenAI-compatible HTTPX JSON completion, JSON extraction/sanitization, provider retry and error handling. |
| `app/services/agent_workflow.py` | LangChain/LangGraph analyst and specialized frontend workflow agents. |
| `app/services/contract_generator.py` | Contract prompt, demo fixture path, Pydantic validation, server-owned price/currency. |
| `app/services/page_generator.py` | Generated file validation, normalization, write, and repair integration. |
| `app/services/verifier.py` | Backward-compatible verification entry point. |
| `app/services/verifier_enhanced.py` | HTML acceptance checks and evidence for criteria. |
| `app/services/browser_verifier.py` | Optional Playwright browser checks and explicit skip results. |
| `app/services/annotated_preview.py` | Read-only visual verification markup. |
| `app/services/artifact_service.py` | ZIP creation from generated source files. |
| `app/services/paypal_service.py` | Mock and real Sandbox PayPal API adapters and response verification. |
| `app/services/runtime_settings.py` | Runtime override loading/saving, Fernet secret encoding, settings visibility. |
| `app/templates/index.html` | Main job workflow dashboard. |
| `app/templates/settings.html` | Runtime settings form. |
| `app/static/css/app.css` | Responsive dashboard styling. |
| `app/static/js/app.js` | Browser-side API coordination and status updates. |
| `tests/` | Unit and service tests for app, LLM behavior, and PayPal behavior. |
| `.env.example` | NVIDIA NIM configuration only; contains a placeholder, not a credential. |
| `.github/workflows/ci.yml` | GitHub Actions dependency installation and pytest run on push/PR. |
| `Dockerfile` | Python container build and Uvicorn startup. |
| `render.yaml` | Render service defaults, NIM model default, secret placeholders, generated-files disk. |
| `migrate_db.py` | Manual schema creation and safe additive updates. |
| `generate_secrets.py` | Production settings token and Fernet key generator. |
| `generated/.gitkeep` | Preserves empty local artifact directory; generated job data is ignored by Git. |
| `LICENSE` | MIT license. |

## 11. Install, run, and test

From the repository root:

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set LLM_API_KEY to your NVIDIA NIM key.
playwright install chromium
uvicorn app.main:app --reload
```

Open <http://localhost:8000>. The health endpoint is <http://localhost:8000/health>, and API docs are <http://localhost:8000/docs>. Chromium installation is optional: HTML verification still runs without it, but browser checks are marked skipped. Do not use `LLM_PROVIDER=demo` for a real AI demonstration; it activates a deterministic fixture.

Run tests from the project root:

```bash
pytest -q tests
```

The test suite includes health and schema migration checks, settings visibility, USD job/contract behavior, contract and page generation, verifier behavior, mock checkout/capture, ZIP packaging, provider JSON parsing and error handling, and PayPal Sandbox request/validation behavior using mocks. GitHub Actions runs the project's tests on pushes and pull requests.

## 12. Deployment

### Docker

```bash
docker build -t ai-contractor-paypal .
docker run -p 8000:8000 --env-file .env ai-contractor-paypal
```

### Render

`render.yaml` configures a Python web service, Uvicorn startup, NVIDIA NIM provider/model defaults, secret environment values to be entered in Render, and a persistent disk mounted for generated files. Configure the NIM key and PayPal Sandbox credentials in the Render dashboard. Set `SETTINGS_ADMIN_TOKEN` and `SETTINGS_ENCRYPTION_KEY` before using protected production settings.

The blueprint's default `DATABASE_URL` is SQLite. The generated-files disk does not make an SQLite database persistent unless the database file is also stored on persistent storage. For deployments that require durable transactional data, configure a managed PostgreSQL database and persistent artifact storage. Set public PayPal return/cancel URLs to the deployed app's correct HTTPS address.

## 13. Security boundaries and known limitations

### Implemented protections

- The model cannot replace the server-controlled approved budget or USD currency.
- The customer approves the contract before generation.
- The payment amount is derived from persisted verification results and passed criteria.
- PayPal captures are validated server-side for job, status, amount, and currency.
- ZIP delivery checks persisted payment completion; browser redirects or guessed download URLs do not unlock it.
- PayPal and NIM credentials are server-side configuration and are not included in frontend assets.
- Secret settings are write-only in the API/UI and can be Fernet-encrypted in the database.
- Annotated previews remove scripts and inline event handlers; preview responses include sandbox-related security headers.

### Prototype limitations (not a production escrow/payment platform)

- There is no customer authentication, account ownership, or per-user authorization for jobs. Do not expose sensitive jobs on a public multi-user service without adding access control.
- The real payment flow is PayPal Developer Sandbox, not production-money processing. The local default is mock mode.
- PayPal webhooks/signature verification are not implemented; capture is initiated and checked server-side after the buyer returns.
- The generated application is static client-side software. It has no server or persistent backend. Preview HTML/CSS must be sent to the browser and can be inspected; payment gates the packaged source ZIP, not secrecy of visible markup.
- Generated pages are not executed in a separate network-isolated worker. Do not run untrusted generated code as a production service without stronger isolation.
- FastAPI background tasks are used for generation; long-running distributed workloads should move to a durable queue/worker system.
- Local SQLite and filesystem artifacts require persistent storage and backup planning when hosted.
- Playwright checks are optional and limited smoke checks, not comprehensive security, accessibility, or product-quality certification.
- AI output and automated acceptance markers can be incorrect or incomplete. Human review remains important; the verifier is not a guarantee of correctness.

## 14. Three-minute demo outline

1. Submit a clear product brief and show the AI-generated acceptance contract.
2. Approve the contract; start generation and show the product preview, verification results, and repair/version history.
3. Demonstrate the locked download before payment.
4. Create a PayPal Sandbox order and approve it with a Sandbox buyer.
5. Show server-side capture confirmation, the amount tied to passed checks, and the unlocked ZIP.

Keep the central message explicit: the approved criteria and independent checks determine payment eligibility, not the model's own completion claim. The recorded public demo must be shorter than three minutes and linked in the hackathon submission.
