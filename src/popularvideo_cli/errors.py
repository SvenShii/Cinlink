from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CliError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None
    exit_code: int = 1

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.details:
            payload["error"]["details"] = self.details
        return payload


def normalize_remote_error(status_code: int, data: Any) -> CliError:
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return CliError(
                code=str(error.get("code") or "remote_error"),
                message=str(error.get("message") or f"Remote request failed with HTTP {status_code}."),
                details={"status_code": status_code},
            )
    if status_code == 401:
        return CliError("auth_failed", "API key is missing or invalid.", {"status_code": status_code})
    if status_code == 404:
        return CliError("job_not_found", "The requested remote resource was not found.", {"status_code": status_code})
    return CliError("remote_error", f"Remote request failed with HTTP {status_code}.", {"status_code": status_code})
