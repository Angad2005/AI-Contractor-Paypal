from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from app.core.config import settings

def make_zip(job_id: str) -> Path:
    source = Path(settings.generated_dir) / job_id
    target = source / f"ai-contractor-{job_id[:8]}.zip"
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for name in ("index.html", "style.css", "script.js"):
            item = source / name
            if item.is_file():
                archive.write(item, item.name)
    return target
