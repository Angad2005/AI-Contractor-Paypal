from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from app.core.config import settings


def make_zip(job_id: str, source_path: str | None = None) -> Path:
    job_folder = Path(settings.generated_dir) / job_id
    source = Path(source_path) if source_path else job_folder
    job_root = job_folder.resolve()
    source_root = source.resolve()
    if not source_root.is_dir() or not source_root.is_relative_to(job_root):
        raise ValueError("The deliverable is not inside this job's private artifact directory")
    target = job_folder / f"ai-contractor-{job_id[:8]}.zip"
    if target.is_symlink() or not target.resolve().is_relative_to(job_root):
        raise ValueError("The ZIP destination is not inside this job's private artifact directory")
    files = sorted(
        item for item in source_root.rglob("*")
        if item.is_file() and not item.is_symlink() and item.resolve() != target.resolve()
    )
    if not files:
        raise ValueError("No deliverable files are available to package")
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for item in files:
            archive.write(item, item.relative_to(source_root).as_posix())
    return target
