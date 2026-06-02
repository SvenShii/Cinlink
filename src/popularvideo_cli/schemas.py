from __future__ import annotations

from typing import Any


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "doctor": {
        "description": "Check hosted runtime health and local dependency status. Use this before local-only tasks such as subtitle burn or voice separation.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "runtime_health": {"type": "object"},
                "local_dependencies": {"type": "object"},
            },
        },
    },
    "transcribe": {
        "description": "Transcribe a local video or audio file into subtitles.",
        "input_schema": {
            "type": "object",
            "required": ["input_path"],
            "properties": {
                "input_path": {"type": "string", "description": "Absolute path to a local media file."},
                "lang": {"type": "string", "default": "auto"},
                "out": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "subtitle_path": {"type": "string"},
                "preview_text": {"type": "string"},
                "engine": {"type": "string"},
            },
        },
    },
    "translate": {
        "description": "Translate subtitles, or transcribe then translate a local media file. Voice delivery uses hosted dubbing when available; it does not require user-side Demucs unless the user asks for local voice separation or preserved background music.",
        "input_schema": {
            "type": "object",
            "required": ["input_path"],
            "properties": {
                "input_path": {"type": "string"},
                "from_lang": {"type": "string", "default": "auto"},
                "to_lang": {"type": "string", "default": "zh"},
                "bilingual": {"type": "boolean", "default": False},
                "delivery": {"type": "string", "enum": ["subtitle", "voice"], "default": "subtitle"},
                "out": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {"type": "object"},
    },
    "burn": {
        "description": "Burn subtitles into a local video with ffmpeg. This is local-only.",
        "input_schema": {
            "type": "object",
            "required": ["video_path", "subtitle_path"],
            "properties": {
                "video_path": {"type": "string"},
                "subtitle_path": {"type": "string"},
                "out": {"type": "string"},
                "font_size": {"type": "integer"},
                "position": {"type": "string", "enum": ["top", "bottom"], "default": "bottom"},
            },
        },
        "output_schema": {"type": "object"},
    },
    "summarize": {
        "description": "Summarize a local video, audio file, or subtitle file.",
        "input_schema": {
            "type": "object",
            "required": ["input_path"],
            "properties": {
                "input_path": {"type": "string"},
                "out": {"type": "string"},
                "max_highlights": {"type": "integer", "default": 3, "minimum": 1, "maximum": 8},
            },
        },
        "output_schema": {"type": "object"},
    },
    "shorten": {
        "description": "Create a highlight plan for a long local video.",
        "input_schema": {
            "type": "object",
            "required": ["video_path"],
            "properties": {
                "video_path": {"type": "string"},
                "out": {"type": "string"},
                "max_clips": {"type": "integer", "default": 5},
                "target_duration": {"type": "integer", "default": 45},
            },
        },
        "output_schema": {"type": "object"},
    },
    "image": {
        "description": "Generate an image from a text prompt.",
        "input_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "out": {"type": "string"},
                "aspect_ratio": {"type": "string", "default": "1:1"},
                "image_size": {"type": "string", "default": "1K"},
                "model": {"type": "string"},
            },
        },
        "output_schema": {"type": "object"},
    },
    "video": {
        "description": "Generate a video from a text prompt or remote references.",
        "input_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "out": {"type": "string"},
                "aspect_ratio": {"type": "string", "default": "16:9"},
                "resolution": {"type": "string", "default": "720P"},
                "duration": {"type": "integer", "default": 5},
                "generate_audio": {"type": "boolean", "default": True},
                "watermark": {"type": "boolean", "default": False},
                "first_frame_image_url": {"type": "string"},
                "reference_image_urls": {"type": "array", "items": {"type": "string"}},
            },
        },
        "output_schema": {"type": "object"},
    },
    "nlu": {
        "description": "Route a natural-language media task into an action.",
        "input_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "has_video": {"type": "boolean", "default": False},
                "has_subtitle": {"type": "boolean", "default": False},
                "pending_target_language": {"type": "string"},
                "context_files": {"type": "array", "items": {"type": "string"}},
            },
        },
        "output_schema": {"type": "object"},
    },
    "agent_run": {
        "description": "Submit a server-side agent run and optionally wait for completion. Hosted-first: provider work runs on the server. Local voice separation/preserved background music requires user-installed ffmpeg, Demucs, and soundfile because the hosted server does not provide Demucs.",
        "input_schema": {
            "type": "object",
            "required": ["prompt"],
            "properties": {
                "prompt": {"type": "string"},
                "conversation_id": {"type": "string"},
                "context_file": {"type": "array", "items": {"type": "string"}},
                "mode": {"type": "string", "enum": ["plan", "execute"], "default": "execute"},
                "wait": {"type": "boolean", "default": False},
            },
        },
        "output_schema": {"type": "object"},
    },
}


def list_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": schema["description"],
            "input_schema": schema["input_schema"],
            "output_schema": schema["output_schema"],
        }
        for name, schema in TOOL_SCHEMAS.items()
    ]
