from __future__ import annotations

from dataclasses import dataclass, asdict, field
import json
import os
from pathlib import Path
from typing import Any

from .errors import CliError


DEFAULT_RUNTIME_BASE = "https://runtime.cinlink.ai"
DEFAULT_BILLING_BASE = "https://app.cinlink.ai"
CONFIG_ENV = "CINLINK_CLI_CONFIG"
LEGACY_CONFIG_ENV = "POPULARVIDEO_CLI_CONFIG"


@dataclass
class Settings:
    api_key: str | None = None
    runtime_base: str = DEFAULT_RUNTIME_BASE
    billing_base: str = DEFAULT_BILLING_BASE
    timeout_sec: float = 1800.0
    poll_interval_sec: float = 2.0
    brand_kit: dict[str, Any] = field(default_factory=dict)

    @property
    def auth_headers(self) -> dict[str, str]:
        if not self.api_key:
            raise CliError("auth_failed", "API key is not configured. Run `cinlink onboarding --api-key <key>` first or set CINLINK_API_KEY.")
        return {"X-API-Key": self.api_key, "Authorization": f"Bearer {self.api_key}"}


def config_path() -> Path:
    explicit = os.environ.get(CONFIG_ENV) or os.environ.get(LEGACY_CONFIG_ENV)
    if explicit:
        return Path(explicit).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return root / "CinLinkCLI" / "config.json"
    return Path.home() / ".config" / "cinlink-cli" / "config.json"


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
        brand_kit=_normalize_brand_kit(data.get("brand_kit")),
    )
    if not settings.api_key and not allow_missing_api_key:
        raise CliError("auth_failed", "API key is not configured. Run `cinlink onboarding --api-key <key>` first or set CINLINK_API_KEY.")
    return settings


def save_settings(settings: Settings) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


BRAND_KIT_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "font_size": 18,
    "font_name": "Arial",
    "font_color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 1.0,
    "margin_v": 20,
    "position": "bottom",
    "watermark_text": None,
    "watermark_position": "top-right",
    "watermark_font_size": 28,
    "watermark_color": "#FFFFFF",
    "watermark_opacity": 0.72,
    "watermark_margin": 24,
    "watermark_image_path": None,
    "watermark_image_position": "top-right",
    "watermark_image_width": None,
    "watermark_image_opacity": 0.72,
    "watermark_image_margin": 24,
}


def brand_kit_payload(settings: Settings) -> dict[str, Any]:
    return {**BRAND_KIT_DEFAULTS, **_normalize_brand_kit(settings.brand_kit)}


def update_brand_kit(settings: Settings, changes: dict[str, Any], *, clear: bool = False) -> dict[str, Any]:
    current = {} if clear else brand_kit_payload(settings)
    for key, value in changes.items():
        if key not in BRAND_KIT_DEFAULTS:
            continue
        if key == "watermark_image_path" and value:
            image_path = Path(str(value)).expanduser().resolve()
            if not image_path.is_file():
                raise CliError("invalid_input", f"Brand Kit watermark image does not exist: {image_path}")
            value = str(image_path)
        current[key] = value
    settings.brand_kit = _normalize_brand_kit(current)
    save_settings(settings)
    return brand_kit_payload(settings)


def render_options(
    settings: Settings,
    overrides: dict[str, Any],
    *,
    use_brand_kit: bool = True,
) -> dict[str, Any]:
    values = dict(BRAND_KIT_DEFAULTS)
    kit = brand_kit_payload(settings)
    if use_brand_kit and kit.get("enabled"):
        values.update(kit)
    for key, value in overrides.items():
        if key in BRAND_KIT_DEFAULTS and value is not None:
            values[key] = value
    return values


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CliError("config_invalid", f"Could not read config file: {path}", {"reason": str(exc)}) from exc
    if not isinstance(payload, dict):
        raise CliError("config_invalid", f"Config file must contain a JSON object: {path}")
    return payload


def _normalize_brand_kit(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if key in BRAND_KIT_DEFAULTS}
