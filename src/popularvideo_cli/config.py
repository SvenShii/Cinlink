from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
from typing import Any

from .errors import CliError


DEFAULT_RUNTIME_BASE = "https://runtime.cinlink.ai"
DEFAULT_BILLING_BASE = "https://app.cinlink.ai"
CONFIG_ENV = "POPULARVIDEO_CLI_CONFIG"


@dataclass
class Settings:
    api_key: str | None = None
    runtime_base: str = DEFAULT_RUNTIME_BASE
    billing_base: str = DEFAULT_BILLING_BASE
    timeout_sec: float = 1800.0
    poll_interval_sec: float = 2.0

    @property
    def auth_headers(self) -> dict[str, str]:
        if not self.api_key:
            raise CliError("auth_failed", "API key is not configured. Run `popularvideo onboarding --api-key <key>` first.")
        return {"X-API-Key": self.api_key, "Authorization": f"Bearer {self.api_key}"}


def config_path() -> Path:
    explicit = os.environ.get(CONFIG_ENV)
    if explicit:
        return Path(explicit).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return root / "PopularVideoCLI" / "config.json"
    return Path.home() / ".config" / "popularvideo-cli" / "config.json"


def legacy_addsubtitle_config_path() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return root / "addsubtitle" / "config.json"
    return Path.home() / ".config" / "addsubtitle" / "config.json"


def load_settings(allow_missing_api_key: bool = False) -> Settings:
    data: dict[str, Any] = {}
    path = config_path()
    if path.exists():
        data.update(_read_json(path))
    else:
        legacy = legacy_addsubtitle_config_path()
        if legacy.exists():
            data.update(_read_json(legacy))

    api_key = os.environ.get("CINLINK_API_KEY") or os.environ.get("ADDSUBTITLE_API_KEY") or data.get("api_key")
    runtime_base = (
        os.environ.get("CINLINK_RUNTIME_BASE")
        or os.environ.get("ADDSUBTITLE_RUNTIME_BASE")
        or data.get("runtime_base")
        or data.get("api_base")
        or DEFAULT_RUNTIME_BASE
    )
    billing_base = (
        os.environ.get("CINLINK_BILLING_BASE")
        or os.environ.get("ADDSUBTITLE_BILLING_BASE")
        or data.get("billing_base")
        or data.get("billing_api_base")
        or DEFAULT_BILLING_BASE
    )
    settings = Settings(
        api_key=str(api_key) if api_key else None,
        runtime_base=str(runtime_base).rstrip("/"),
        billing_base=str(billing_base).rstrip("/"),
        timeout_sec=float(data.get("timeout_sec") or 1800.0),
        poll_interval_sec=float(data.get("poll_interval_sec") or 2.0),
    )
    if not settings.api_key and not allow_missing_api_key:
        raise CliError("auth_failed", "API key is not configured. Run `popularvideo onboarding --api-key <key>` first.")
    return settings


def save_settings(settings: Settings) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CliError("config_invalid", f"Could not read config file: {path}", {"reason": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise CliError("config_invalid", f"Config file must contain a JSON object: {path}")
    return payload
