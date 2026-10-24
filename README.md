# AI Contractor PayPal

> **Pay for what ships.** An outcome-based contracting MVP where an AI contractor builds a browser-based software product from a customer brief, an independent verifier checks its approved acceptance contract, and a PayPal-gated ZIP download releases the source package only after payment is confirmed.

## Hackathon Submission

**PayPal AI Hackathon 2026**

This project demonstrates:
- **AI Integration**: NVIDIA NIM for contract analysis, deliverable generation, and automated repair
- **PayPal Capability**: Real PayPal Developer Sandbox orders API with server-side capture verification
- **Payment-Gated Delivery**: Source code is released only after verified payment completion
- **Enhanced Verification**: Browser-based functional testing with Playwright for actual form, navigation, and responsive validation
- **Visual Feedback**: Annotated preview with green/red borders showing verification results
- **Version History**: Track all generation attempts with detailed verification results

## Quick Start (For Judges)

The fastest way to evaluate this project is to run it locally:

```bash
# Clone the repository
git clone <repository-url>
cd AI-Contractor-Paypal

# Create virtual environment
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright's Chromium browser (optional; HTML verification still completes if omitted)
playwright install chromium

# Configure environment
copy .env.example .env  # Windows; use cp on macOS/Linux

# Run database migration (if upgrading from an older version)
python migrate_db.py

# Run the application
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000) to access the application. Interactive API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

**Default Configuration**: PayPal starts in mock mode. Contract drafting, software generation, and repair use the configured NVIDIA NIM model and require its API key. An explicit `LLM_PROVIDER=demo` setting selects the generic offline fixture for local tests only; do not use that mode for customer jobs.

## Project Overview

AI Contractor PayPal generates small, self-contained browser applications from customer briefs. The LLM returns an `index.html`, `style.css`, and `script.js` application, which can be previewed and verified before the source package is released. The complete flow:

1. **Brief Submission**: Customer submits a plain-language brief and budget
2. **Contract Analysis**: A real structured-output LLM turns the brief into testable acceptance criteria
3. **Contract Approval**: Customer approves the specification before generation begins
4. **Software Generation**: AI builds the requested browser app as `index.html`, `style.css`, and `script.js`
5. **Independent Verification**: The verifier checks required product elements and acceptance markers against the approved criteria
6. **Repair Loop**: Failed checks can be returned to the AI for at most two repair attempts
7. **Outcome Billing**: The contract budget is split equally across acceptance criteria; only passing criteria contribute to the payable amount
8. **PayPal Order**: Server creates and captures a real PayPal Developer Sandbox order (or mock in local mode)
9. **Gated Delivery**: Download endpoint independently checks the database before creating a protected ZIP

**Key Innovation**: The payment gate eligibility is determined by an approved contract and an independent verifier—not just a checkout button.

The generated product runs entirely in the browser and has no backend integration. The annotated preview is read-only: it serves the generated page and styles with verification marks, while removing JavaScript and inline event handlers. The ZIP endpoint releases all source files only after verified payment. The preview still sends HTML and CSS to the browser, so those visual files can be inspected; a browser-rendered preview cannot make its visual markup secret.

## Configuration

### AI Provider Configuration

Configure NVIDIA NIM in `.env` (NIM provides an OpenAI-compatible chat-completions endpoint):

```env
LLM_PROVIDER=nvidia-nim
LLM_API_KEY=your_api_key_here
LLM_MODEL=your-nvidia-nim-model-id
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
```

**Note**: The model ID and API key are read from `.env` or `/settings`. If NIM is unavailable or returns an invalid response, the job reports an AI error instead of silently switching to the offline fixture.

### LM Studio Configuration

Load a model in LM Studio and start its local server on port 1234. Find the exact model identifier at http://localhost:1234/v1/models, then configure:

LLM_PROVIDER=lm-studio
LLM_API_KEY=
LLM_MODEL=your-loaded-lm-studio-model-id
LLM_BASE_URL=http://localhost:1234/v1

The local LM Studio server does not require an API key by default; leave it blank unless you enabled server authentication, then enter the LM Studio token. If this app runs inside WSL or a container and localhost cannot reach LM Studio on Windows, use the Windows host address that LM Studio exposes on your local network.

LM Studio does not accept OpenAI's `json_object` response format, so the app requests text output from LM Studio and parses the JSON required by its prompts.

Groq also uses text response mode because some model generations fail Groq's JSON-mode validation; the app parses and validates the JSON returned in the response.

### PayPal Sandbox Configuration

Create a PayPal Developer Sandbox business app and buyer account at [developer.paypal.com](https://developer.paypal.com), then configure:

```env
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=your_sandbox_client_id
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret
PAYPAL_API_BASE_URL=https://api-m.sandbox.paypal.com
PAYPAL_RETURN_URL=http://localhost:8000/api/paypal/return
PAYPAL_CANCEL_URL=http://localhost:8000/api/paypal/cancel
```

**Note**: `PAYPAL_MODE=mock` (default) uses a safe mock adapter for local development and unit tests.
All contracts and PayPal orders use USD ($). The PayPal Sandbox Business seller account must be able to receive USD. If PayPal returns an unsupported payee-currency error, update the receiving preferences for the seller account that owns the configured REST app credentials, or configure credentials for a US Sandbox seller that accepts USD. Reset the failed order and create a fresh one after changing the seller settings; the app will not silently convert or capture a non-USD order.

### Settings Page Configuration

The application includes a runtime settings page at `/settings` where you can configure providers without editing source files. A "Settings" button is available in the header of the main page for easy access.

- **For Development**: Access the settings page directly (no token required in non-production environments)
- **For Production**: Set `SETTINGS_ADMIN_TOKEN` and `SETTINGS_ENCRYPTION_KEY` in your environment variables for secure encrypted storage

The settings page supports:
- LLM provider configuration (API key, model, base URL, timeout)
- PayPal configuration (mode, client ID, client secret, API URLs)
- **Custom environment variable definitions**: Add any additional environment variables your application needs (e.g., third-party API keys, feature flags, etc.) without modifying the code
- The settings page provides a user-friendly GUI with explanations for each field, making it easy to understand what values go where
- Non-secret fields show the active runtime values loaded from the project-root `.env` file (and any saved runtime overrides), regardless of the directory used to launch the app. Secret values remain write-only; the GUI only indicates whether they are configured.

### Additional Environment Variables

```env
# Application
APP_ENV=development
DATABASE_URL=sqlite:///./app.db
GENERATED_DIR=generated

# Settings page protection (production)
# Generate encryption key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SETTINGS_ADMIN_TOKEN=your_admin_token
SETTINGS_ENCRYPTION_KEY=your_fernet_encryption_key
```

**Note**: The application applies safe, additive schema updates at startup. You can also run `python migrate_db.py` manually if needed. These updates cover:
- `is_custom` column to `app_settings` table for custom environment variables
- `generation_versions` table for version history tracking
- `approval_url`, `order_request_id`, and `capture_request_id` columns to `payments` table for PayPal integration

## Testing

Run the test suite:

```bash
pytest -q
```

The included tests cover:
- Contract generator
- Generated artifact structure
- Deterministic verifier
- Mock payment adapter
- ZIP packaging
- Health endpoint

**Note**: The test suite uses deterministic service-level tests to ensure CI compatibility across platforms.

## PayPal Integration Details

The real PayPal Sandbox flow:

1. A verified or partially billable job calls `POST /api/jobs/{id}/paypal/order`; the order amount is calculated from passed criteria only
2. Server obtains OAuth access token and creates a `CAPTURE` order through PayPal Orders API v2
3. Job ID is stored in PayPal `reference_id` and `custom_id`
4. Dashboard opens PayPal's returned approval URL for the Sandbox buyer
5. PayPal returns the buyer to `/api/paypal/return`; the app resumes the job and captures the approved order server-side
6. Server verifies order status, capture status, job association, the computed passed-check amount, and currency
7. Only after the database records a completed capture does the download endpoint release the ZIP

### Sandbox currency troubleshooting

Contracts and orders use USD only. If PayPal displays “This seller doesn’t accept payments in your currency,” the Sandbox Business seller attached to the REST app credentials cannot receive USD. In the Sandbox site, sign in as that exact Business account, open **Account Settings → Payment preferences → Block payments**, and allow payments in currencies the account does not hold (including USD). Alternatively, configure the app with the REST app credentials of a Sandbox seller that accepts USD. This preference is controlled by the merchant account, as described in PayPal’s [currency code guide](https://developer.paypal.com/api/codes/currency/) and [unsupported payee currency guidance](https://developer.paypal.com/api/errors/unsupported-payee-currency/).

After saving that preference, reset the old order and create a fresh PayPal order from the app. The integration sends USD and rejects non-USD orders before capture.

**Security**: Payment state is verified server-side. The download endpoint checks persisted payment state rather than trusting browser callbacks or guessed URLs.

## Security Model

- **Contract Immutability**: Approved contract is stored before generation; generator cannot modify price or acceptance criteria
- **Status Enforcement**: Job status transitions are enforced server-side
- **Outcome Billing**: Checkout accepts `VERIFIED` and `BILLABLE` results; each passed contract criterion contributes an equal share of the budget
- **Payment Verification**: Capture requires the job's own pending order and the exact computed amount/currency
- **Independent Verification**: `/download` checks persisted payment state rather than browser callbacks
- **Artifact Isolation**: Generated artifacts are kept outside the static directory

**Production Recommendations**:
- Run generated pages in an isolated worker/container with outbound network disabled
- Verify PayPal webhook signatures
- Use PostgreSQL and object storage for persistence
- Add isolated Playwright browser tests
- Configure `SETTINGS_ADMIN_TOKEN` and `SETTINGS_ENCRYPTION_KEY`

## Three-Minute Demo Script

1. **Brief Submission**: Submit a software brief and show the AI-proposed criteria
2. **Contract Approval**: Approve the contract and show generation, verification checks, and repair history
3. **Gate Demonstration**: Try the download before payment and show the server-side `403` gate
4. **PayPal Sandbox**: Create a real Sandbox order, open the approval URL with a Sandbox buyer, return to the app, and confirm server-side capture
5. **Delivery**: Show the confirmed capture ID and download the verified source ZIP

## Deployment

### Local Development

Follow the Quick Start instructions above.

### Docker

```bash
docker build -t ai-contractor-paypal .
docker run -p 8000:8000 --env-file .env ai-contractor-paypal
```

### Render (Recommended for Hosting)

The repository includes `render.yaml` for deployment. For a hosted demo:

1. Connect your GitHub repository to Render
2. Configure environment variables in the Render dashboard:
   - `PAYPAL_MODE=sandbox` (or mock for testing)
   - `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`
   - `LLM_PROVIDER=nvidia-nim`
   - `LLM_API_KEY`
   - `SETTINGS_ADMIN_TOKEN` (for settings page protection - generate a secure random token)
   - `SETTINGS_ENCRYPTION_KEY` (for encrypted settings storage - generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
3. **Important**: Render's default filesystem is ephemeral. For production:
   - Use a managed PostgreSQL database instead of SQLite
   - Configure persistent disk storage for generated artifacts
   - Or use the local-run instructions for judge-facing demos
4. **First-time deployment**: The application will automatically create the database schema on startup

### GitHub Actions

The repository includes a CI workflow that runs tests on push and pull requests.

## Repository Structure

- `app/main.py` - FastAPI application entry point
- `app/core/config.py` - Configuration and environment variable management
- `app/api/routes.py` - API endpoints
- `app/services/` - Business logic (LLM provider, PayPal adapter, verifier, runtime settings)
- `app/db/` - Database models and session management
- `app/templates/` - HTML templates (includes settings page with GUI for configuration)
- `app/static/` - Static assets
- `tests/` - Test suite
- `migrate_db.py` - Database migration script for adding new columns

See [`details.md`](details.md) for a file-by-file explanation, lifecycle diagram, API contract, provider behavior, and extension points.

## Submission Checklist

- [x] Register for the hackathon on Devpost
- [x] Publish GitHub repository with MIT license
- [x] Add project description with AI model/provider and PayPal capability details
- [x] Verify README enables judges to install, configure, and run the prototype
- [ ] Record a public YouTube demo shorter than three minutes
- [ ] Run final demo end-to-end with actual PayPal Sandbox buyer and payment capture
- [ ] Verify demo video and assets use no unauthorized copyrighted material

## License

MIT License - See LICENSE file for details
