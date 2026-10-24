from typing import Any
import os
from pathlib import Path

from app.core.config import settings
from app.db.models import AppSetting

try:
    from cryptography.fernet import Fernet
except ImportError:  # pragma: no cover - dependency is pinned in requirements
    Fernet = None


SETTING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "llm_provider": {"label": "LLM provider", "secret": False},
    "llm_api_key": {"label": "LLM API key", "secret": True},
    "llm_model": {"label": "LLM model", "secret": False},
    "llm_base_url": {"label": "LLM base URL", "secret": False},
    "paypal_mode": {"label": "PayPal mode", "secret": False},
    "paypal_client_id": {"label": "PayPal client ID", "secret": True},
    "paypal_client_secret": {"label": "PayPal client secret", "secret": True},
    "paypal_api_base_url": {"label": "PayPal API base URL", "secret": False},
    "paypal_return_url": {"label": "PayPal return URL", "secret": False},
    "paypal_cancel_url": {"label": "PayPal cancel URL", "secret": False},
    "generated_dir": {"label": "Generated artifact directory", "secret": False},
}


def _fernet():
    if not settings.settings_encryption_key:
        return None
    if Fernet is None:
        raise RuntimeError("cryptography is required for encrypted settings")
    return Fernet(settings.settings_encryption_key.encode())


def _encode(value: str, secret: bool) -> str:
    if secret:
        cipher = _fernet()
        if cipher:
            return "fernet:" + cipher.encrypt(value.encode()).decode()
        if settings.app_env.lower() == "production":
            raise RuntimeError("SETTINGS_ENCRYPTION_KEY is required for secret settings in production")
    return value


def _decode(value: str) -> str:
    if value.startswith("fernet:"):
        cipher = _fernet()
        if not cipher:
            raise RuntimeError("SETTINGS_ENCRYPTION_KEY is required to read encrypted settings")
        return cipher.decrypt(value[7:].encode()).decode()
    return value


def apply_runtime_setting(key: str, value: str) -> None:
    setattr(settings, key, value)


def apply_custom_env_var(key: str, value: str) -> None:
    """Apply a custom environment variable to os.environ"""
    os.environ[key] = value


def _configured_environment_names() -> set[str]:
    """Return configured variable names without reading values into logs or output."""
    names = {name.upper() for name in os.environ}
    env_file = settings.model_config.get("env_file")
    if not env_file:
        return names
    env_files = env_file if isinstance(env_file, (tuple, list)) else (env_file,)
    for candidate in env_files:
        path = Path(candidate)
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.lower().startswith("export "):
                stripped = stripped[7:].lstrip()
            name, separator, _value = stripped.partition("=")
            if separator and name.strip():
                names.add(name.strip().upper())
    return names


def load_runtime_settings(db) -> None:
    # Explicit process/.env configuration wins over stale database overrides.
    # The settings UI can still change values for the current process, but a
    # restart returns to the deployment's explicit environment configuration.
    environment_names = _configured_environment_names()
    for record in db.query(AppSetting).all():
        if record.key in SETTING_DEFINITIONS:
            if record.key.upper() in environment_names:
                continue
            apply_runtime_setting(record.key, _decode(record.value))
        elif record.is_custom:
            env_key = record.key[7:] if record.key.startswith("CUSTOM_") else record.key
            apply_custom_env_var(env_key, _decode(record.value))


def save_runtime_settings(db, values: dict[str, str]) -> None:
    for key, value in values.items():
        # Handle predefined settings
        if key in SETTING_DEFINITIONS:
            if value is None or value == "":
                continue
            definition = SETTING_DEFINITIONS[key]
            record = db.get(AppSetting, key)
            encoded = _encode(str(value), definition["secret"])
            if record is None:
                record = AppSetting(key=key, value=encoded, is_secret=definition["secret"], is_custom=False)
                db.add(record)
            else:
                record.value = encoded
            apply_runtime_setting(key, str(value))
        # Handle custom environment variables (keys prefixed with "CUSTOM_")
        elif key.startswith("CUSTOM_"):
            env_key = key[7:]  # Remove "CUSTOM_" prefix
            record = db.get(AppSetting, key)

            # Empty value means delete the custom variable
            if value is None or value == "":
                if record is not None:
                    db.delete(record)
                    # Remove from environment if present
                    if env_key in os.environ:
                        del os.environ[env_key]
            else:
                encoded = _encode(str(value), True)  # Always treat custom vars as secrets
                if record is None:
                    record = AppSetting(key=key, value=encoded, is_secret=True, is_custom=True)
                    db.add(record)
                else:
                    record.value = encoded
                apply_custom_env_var(env_key, str(value))
    db.commit()


def visible_settings(db) -> list[dict[str, Any]]:
    saved = {record.key: record for record in db.query(AppSetting).all()}
    result = []

    # Predefined settings
    for key, definition in SETTING_DEFINITIONS.items():
        record = saved.get(key)
        current = getattr(settings, key, "")
        result.append({
            "key": key,
            "label": definition["label"],
            "secret": definition["secret"],
            "configured": bool(record or current),
            "value": "" if definition["secret"] else str(current),
            "is_custom": False,
        })

    # Custom environment variables
    for key, record in saved.items():
        if record.is_custom:
            env_key = key[7:] if key.startswith("CUSTOM_") else key
            current = os.environ.get(env_key, "")
            result.append({
                "key": key,
                "label": f"Custom: {env_key}",
                "secret": True,
                "configured": bool(record or current),
                "value": "",  # Never show custom secret values
                "is_custom": True,
            })

    return result
