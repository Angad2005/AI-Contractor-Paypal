# AI Contractor PayPal

> **Pay for what ships.** An outcome-based contracting MVP where an AI contractor generates a landing page, an independent verifier checks the approved acceptance contract, and a PayPal-gated ZIP download releases the source only after payment is confirmed.

## Hackathon Submission

**PayPal AI Hackathon 2026**

This project demonstrates:
- **AI Integration**: OpenAI-compatible LLM for contract analysis, deliverable generation, and automated repair
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

# Install Playwright browsers (optional, for browser-based verification)
playwright install chromium

# Configure environment
copy .env.example .env  # Windows; use cp on macOS/Linux

# Run database migration (if upgrading from an older version)
python migrate_db.py

# Run the application
uvicorn app.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000) to access the application. Interactive API documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

**Default Configuration**: The application starts in mock mode for both PayPal and AI provider, allowing immediate testing without API keys. Configure real providers for the full experience (see Configuration section below).

## Project Overview

AI Contractor PayPal focuses on one deliverable type: AI-generated landing pages. The complete flow:

1. **Brief Submission**: Customer submits a plain-language brief and budget
2. **Contract Analysis**: A real structured-output LLM turns the brief into testable acceptance criteria
3. **Contract Approval**: Customer approves the specification before generation begins
4. **Deliverable Generation**: AI generates `index.html`, `style.css`, and `script.js`
5. **Independent Verification**: Beautiful Soup verifier checks the artifact against approved criteria
6. **Repair Loop**: Failed checks can be returned to the AI for at most two repair attempts
7. **Payment Gate**: Checkout is unavailable until verification passes
8. **PayPal Order**: Server creates and captures a real PayPal Developer Sandbox order (or mock in local mode)
9. **Gated Delivery**: Download endpoint independently checks the database before creating a protected ZIP

**Key Innovation**: The payment gate eligibility is determined by an approved contract and an independent verifier—not just a checkout button.

## Configuration

### AI Provider Configuration

Configure any OpenAI-compatible chat-completions provider in `.env`:

```env
LLM_PROVIDER=openai-compatible
LLM_API_KEY=your_api_key_here
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_TIMEOUT_SECONDS=60
```

**Note**: `LLM_PROVIDER=demo` (default) uses a deterministic generator for local testing without requiring an API key.

### PayPal Sandbox Configuration

Create a PayPal Developer Sandbox business app and buyer account at [developer.paypal.com](https://developer.paypal.com), then configure:

```env
PAYPAL_MODE=sandbox
PAYPAL_CLIENT_ID=your_sandbox_client_id
PAYPAL_CLIENT_SECRET=your_sandbox_client_secret
PAYPAL_API_BASE_URL=https://api-m.sandbox.paypal.com
PAYPAL_RETURN_URL=http://localhost:8000/
PAYPAL_CANCEL_URL=http://localhost:8000/
```

**Note**: `PAYPAL_MODE=mock` (default) uses a safe mock adapter for local development and unit tests.

### Settings Page Configuration

The application includes a runtime settings page at `/settings` where you can configure providers without editing source files. A "Settings" button is available in the header of the main page for easy access.

- **For Development**: Access the settings page directly (no token required in non-production environments)
- **For Production**: Set `SETTINGS_ADMIN_TOKEN` and `SETTINGS_ENCRYPTION_KEY` in your environment variables for secure encrypted storage

The settings page supports:
- LLM provider configuration (API key, model, base URL, timeout)
- PayPal configuration (mode, client ID, client secret, API URLs)
- **Custom environment variable definitions**: Add any additional environment variables your application needs (e.g., third-party API keys, feature flags, etc.) without modifying the code
- The settings page provides a user-friendly GUI with explanations for each field, making it easy to understand what values go where

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

**Note**: If you're upgrading from an older version, run `python migrate_db.py` to add the new columns to the database:
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

1. A verified job calls `POST /api/jobs/{id}/paypal/order`
2. Server obtains OAuth access token and creates a `CAPTURE` order through PayPal Orders API v2
3. Job ID is stored in PayPal `reference_id` and `custom_id`
4. Dashboard opens PayPal's returned approval URL for the Sandbox buyer
5. `POST /api/jobs/{id}/paypal/capture` captures the pending order server-side
6. Server verifies order status, capture status, job association, amount, and currency
7. Only after the database records a completed capture does the download endpoint release the ZIP

**Security**: Payment state is verified server-side. The download endpoint checks persisted payment state rather than trusting browser callbacks or guessed URLs.

## Security Model

- **Contract Immutability**: Approved contract is stored before generation; generator cannot modify price or acceptance criteria
- **Status Enforcement**: Job status transitions are enforced server-side
- **Payment Verification**: Checkout requires `VERIFIED` status; capture requires the job's own pending order
- **Independent Verification**: `/download` checks persisted payment state rather than browser callbacks
- **Artifact Isolation**: Generated artifacts are kept outside the static directory

**Production Recommendations**:
- Run generated pages in an isolated worker/container with outbound network disabled
- Verify PayPal webhook signatures
- Use PostgreSQL and object storage for persistence
- Add isolated Playwright browser tests
- Configure `SETTINGS_ADMIN_TOKEN` and `SETTINGS_ENCRYPTION_KEY`

## Three-Minute Demo Script

1. **Brief Submission**: Submit a landing-page brief and show the AI-proposed criteria
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
   - `LLM_PROVIDER=openai-compatible` (or demo for testing)
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
