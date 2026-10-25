from pathlib import Path, PurePosixPath

from app.core.config import settings
from app.services.llm_provider import complete_json, is_demo_mode

MAX_PROJECT_FILES = 40
MAX_FILE_BYTES = 300_000
MAX_PROJECT_BYTES = 2_000_000


def _validate_files(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ValueError("The model did not return a source project file map")
    if len(value) > MAX_PROJECT_FILES:
        raise ValueError(f"The source project exceeds the {MAX_PROJECT_FILES}-file limit")

    files: dict[str, str] = {}
    total_bytes = 0
    for raw_name, content in value.items():
        if not isinstance(raw_name, str) or not isinstance(content, str):
            raise ValueError("Source project paths and contents must be strings")
        path = PurePosixPath(raw_name)
        if (
            not raw_name
            or "\\" in raw_name
            or not path.parts
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or ":" in path.parts[0]
            or "\x00" in raw_name
            or any(part.lower() in {".git", "__pycache__", "node_modules"} for part in path.parts)
            or path.name.lower() in {".env", "id_rsa", "id_ed25519"}
        ):
            raise ValueError(f"Unsafe source project path: {raw_name}")
        if not content.strip():
            raise ValueError(f"Source project file is empty: {raw_name}")
        size = len(content.encode("utf-8"))
        if size > MAX_FILE_BYTES:
            raise ValueError(f"Source project file is too large: {raw_name}")
        total_bytes += size
        files[raw_name] = content

    if total_bytes > MAX_PROJECT_BYTES:
        raise ValueError("The source project exceeds the 2 MB size limit")
    if "README.md" not in files:
        raise ValueError("The source project must include a README.md")
    if len(files) < 2:
        raise ValueError("The source project must include source files as well as its README.md")
    return files


def generate_source_project(job_id: str, prompt: str, attempt: int) -> str:
    folder = Path(settings.generated_dir) / job_id / f"source-project-{attempt}"
    folder.mkdir(parents=True, exist_ok=False)

    if is_demo_mode():
        files = {
            "README.md": "# Custom software project\n\nThis is a demo source package. Configure an LLM provider to generate a project from the brief.",
            "src/main.py": 'def main():\n    print("Custom software project scaffold")\n\n\nif __name__ == "__main__":\n    main()\n',
        }
    else:
        result = complete_json(
            """You are a senior software engineer generating a custom software source
project. Return only a JSON object with one key, "files", whose value maps relative
POSIX file paths to complete UTF-8 text file contents. Build the requested product,
not a generic scaffold. Include a useful README.md with setup and usage instructions,
plus the source/configuration files needed by the project. Never include credentials,
secrets, binary data, generated dependencies, or a real .env file. Do not run or claim
to have run the software. Keep the project compact: at most 40 files and 2 MB total.""",
            f"Customer brief:\n{prompt}",
        )
        files = _validate_files(result.get("files"))

    root = folder.resolve()
    for name, content in files.items():
        target = folder.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            raise ValueError(f"Source project path escapes its private build directory: {name}")
        target.write_text(content, encoding="utf-8")
    return str(folder)


def verify_source_project(path: str) -> dict:
    root = Path(path)
    files = [
        item
        for item in root.rglob("*")
        if item.is_file() and not item.is_symlink()
    ] if root.is_dir() else []
    has_readme = any(item.relative_to(root).as_posix() == "README.md" for item in files)
    passed = len(files) >= 2 and has_readme and all(item.stat().st_size > 0 for item in files)
    return {
        "key": "source_package",
        "label": "Downloadable source project",
        "passed": passed,
        "evidence": (
            f"Found {len(files)} non-empty project files and a README.md"
            if passed
            else "The project needs at least one source file and a non-empty README.md"
        ),
        "method": "project_structure",
    }
