from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.core.config import settings
from app.db.database import Base, SessionLocal, engine, migrate_legacy_columns
from app.api.routes import router
from app.services.runtime_settings import load_runtime_settings

Path(settings.generated_dir).mkdir(exist_ok=True)
Base.metadata.create_all(bind=engine)
migrate_legacy_columns(engine)
with SessionLocal() as startup_db:
    load_runtime_settings(startup_db)
app = FastAPI(title=settings.app_name, version="1.0.0", description="Outcome-based AI contracting with verification-gated PayPal delivery")
app.include_router(router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
@app.get("/", response_class=HTMLResponse)
def home(request: Request): return templates.TemplateResponse("index.html", {"request":request})

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request): return templates.TemplateResponse("settings.html", {"request":request})
@app.get("/health")
def health(): return {"status":"ok", "environment":settings.app_env}
