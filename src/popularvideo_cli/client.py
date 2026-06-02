from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

import httpx

from .config import Settings
from .dependencies import default_client_capabilities_from_dependencies
from .errors import CliError, normalize_remote_error


class RuntimeClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/v1/health", auth=False)

    def transcribe(self, input_path: Path, lang: str = "auto", out: Path | None = None, timeout: float | None = None) -> dict[str, Any]:
        payload = self._multipart("/v1/transcribe", input_path, {"source_lang": lang, "output_dir": str(out) if out else None})
        return self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)

    def translate(
        self,
        input_path: Path,
        from_lang: str = "auto",
        to_lang: str = "zh",
        bilingual: bool = False,
        delivery: str = "subtitle",
        out: Path | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        payload = self._multipart(
            "/v1/translate",
            input_path,
            {
                "from_lang": from_lang,
                "to_lang": to_lang,
                "bilingual": "true" if bilingual else "false",
                "delivery": delivery,
                "output_dir": str(out) if out else None,
            },
        )
        if isinstance(payload, dict) and "job_id" in payload and payload.get("status") not in {"done", "failed"}:
            return self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)
        return payload

    def summarize(self, input_path: Path, out: Path | None = None, max_highlights: int = 3) -> dict[str, Any]:
        return self._multipart("/v1/summarize", input_path, {"output_dir": str(out) if out else None, "max_highlights": str(max_highlights)})

    def shorten(self, video_path: Path, out: Path | None = None, max_clips: int = 5, target_duration: int = 45) -> dict[str, Any]:
        return self._multipart(
            "/v1/shorten",
            video_path,
            {
                "output_dir": str(out) if out else None,
                "max_clips": str(max_clips),
                "target_duration_sec": str(target_duration),
            },
        )

    def image(self, prompt: str, out: Path | None = None, aspect_ratio: str = "1:1", image_size: str = "1K", model: str | None = None) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/image",
            json_body={"prompt": prompt, "output_dir": str(out) if out else None, "aspect_ratio": aspect_ratio, "image_size": image_size, "model": model},
        )

    def video(
        self,
        prompt: str,
        out: Path | None = None,
        aspect_ratio: str = "16:9",
        resolution: str = "720P",
        duration: int = 5,
        generate_audio: bool = True,
        watermark: bool = False,
        first_frame_image_url: str | None = None,
        reference_image_urls: list[str] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/v1/video",
            json_body={
                "prompt": prompt,
                "output_dir": str(out) if out else None,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "duration_sec": duration,
                "generate_audio": generate_audio,
                "watermark": watermark,
                "first_frame_image_url": first_frame_image_url,
                "reference_image_urls": reference_image_urls or [],
            },
        )
        if isinstance(payload, dict) and "job_id" in payload:
            return self.wait_for_job(payload["job_id"], timeout or self.settings.timeout_sec)
        return payload

    def nlu(
        self,
        prompt: str,
        has_video: bool = False,
        has_subtitle: bool = False,
        pending_target_language: str | None = None,
        context_files: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/nlu",
            json_body={
                "prompt": prompt,
                "has_selected_video": has_video,
                "has_subtitle": has_subtitle,
                "pending_translation_target_language": pending_target_language,
                "context_files": context_files or [],
            },
        )

    def create_agent_run(
        self,
        prompt: str,
        conversation_id: str | None = None,
        context_files: list[Path] | None = None,
        mode: str = "execute",
        client_capabilities: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        request_files = [_context_file_payload(path) for path in (context_files or [])]
        return self._request(
            "POST",
            "/v1/agent/runs",
            json_body={
                "conversation_id": conversation_id or f"cli-{uuid4()}",
                "prompt": prompt,
                "context_files": request_files,
                "client_capabilities": client_capabilities or default_client_capabilities(),
                "mode": mode,
            },
        )

    def get_agent_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/agent/runs/{run_id}")

    def wait_for_agent_run(self, run_id: str, timeout: float | None = None) -> dict[str, Any]:
        deadline = time.time() + (timeout or self.settings.timeout_sec)
        while True:
            payload = self.get_agent_run(run_id)
            if payload.get("status") in {"done", "failed", "requires_user_input", "waiting_for_local"}:
                return payload
            if time.time() > deadline:
                raise CliError("timeout", f"Agent run did not finish within {timeout or self.settings.timeout_sec} seconds.", {"run_id": run_id})
            time.sleep(self.settings.poll_interval_sec)

    def list_local_tool_calls(self, run_id: str, device_id: str | None = None) -> dict[str, Any]:
        suffix = f"?device_id={device_id}" if device_id else ""
        return self._request("GET", f"/v1/agent/runs/{run_id}/local-tool-calls{suffix}")

    def report_local_tool_result(self, run_id: str, result: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/v1/agent/runs/{run_id}/local-tool-results", json_body=result)

    def wait_for_job(self, job_id: str, timeout: float) -> dict[str, Any]:
        deadline = time.time() + timeout
        while True:
            payload = self._request("GET", f"/v1/jobs/{job_id}")
            if payload.get("status") in {"done", "failed"}:
                if payload.get("status") == "failed":
                    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                    raise CliError(str(error.get("code") or "processing_failed"), str(error.get("message") or "Remote job failed."), {"job_id": job_id})
                return payload
            if time.time() > deadline:
                raise CliError("timeout", f"Job did not finish within {timeout} seconds.", {"job_id": job_id})
            time.sleep(self.settings.poll_interval_sec)

    def _multipart(self, path: str, input_path: Path, fields: dict[str, Any]) -> dict[str, Any]:
        checked = require_existing_file(input_path)
        data = {key: value for key, value in fields.items() if value is not None}
        with checked.open("rb") as file_handle:
            return self._request("POST", path, data=data, files={"file": (checked.name, file_handle)})

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = self.settings.runtime_base.rstrip("/")
        headers = self.settings.auth_headers if auth else {}
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.request(method, f"{base}{path}", headers=headers, json=json_body, data=data, files=files)
        except httpx.HTTPError as exc:
            raise CliError("network_error", f"Could not reach runtime service: {exc}") from exc
        try:
            payload: Any = response.json()
        except json.JSONDecodeError:
            payload = {"raw": response.text[:1000]}
        if response.status_code >= 400:
            raise normalize_remote_error(response.status_code, payload)
        if not isinstance(payload, dict):
            raise CliError("invalid_response", "Runtime returned a non-object JSON response.", {"type": type(payload).__name__})
        return payload


def require_existing_file(path: Path) -> Path:
    expanded = path.expanduser().resolve()
    if not expanded.exists():
        raise CliError("invalid_input", f"File does not exist: {expanded}")
    if not expanded.is_file():
        raise CliError("invalid_input", f"Path is not a file: {expanded}")
    return expanded


def default_client_capabilities() -> dict[str, bool]:
    return default_client_capabilities_from_dependencies()


def _context_file_payload(path: Path) -> dict[str, Any]:
    checked = require_existing_file(path)
    suffix = checked.suffix.lower()
    if suffix in {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".mpg", ".mpeg"}:
        kind = "video"
    elif suffix in {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}:
        kind = "audio"
    elif suffix in {".srt", ".vtt", ".ass", ".ssa", ".txt"}:
        kind = "subtitle"
    elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        kind = "image"
    else:
        kind = "other"
    return {"id": None, "name": checked.name, "kind": kind, "local_hint": str(checked), "metadata": {}}
