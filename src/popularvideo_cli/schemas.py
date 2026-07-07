from __future__ import annotations

from typing import Any


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "configure": {
        "description": "Store a CinLink API key and optional runtime/billing base URLs for later tool calls.",
        "input_schema": {
            "type": "object",
            "required": ["api_key"],
            "properties": {
                "api_key": {"type": "string", "description": "CinLink API key, for example ck_live_or_test_xxx."},
                "runtime_base": {"type": "string", "default": "https://runtime.cinlink.ai"},
                "billing_base": {"type": "string", "default": "https://app.cinlink.ai"},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "config_path": {"type": "string"},
                "runtime_base": {"type": "string"},
                "billing_base": {"type": "string"},
            },
        },
    },
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
    "add_subtitles": {
        "description": "App-parity workflow for adding subtitles to a video: use an existing subtitle if provided, otherwise transcribe the video, or translate to target_lang, then burn the subtitle into the local video with ffmpeg.",
        "input_schema": {
            "type": "object",
            "required": ["video_path"],
            "properties": {
                "video_path": {"type": "string"},
                "subtitle_path": {"type": "string", "description": "Optional existing .srt/.ass/.vtt file. If omitted, hosted transcribe or translate creates one first."},
                "source_lang": {"type": "string", "default": "auto"},
                "target_lang": {"type": "string", "description": "Optional target language. When set, the workflow translates subtitles before burning."},
                "bilingual": {"type": "boolean", "default": False},
                "out": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
                "font_size": {"type": "integer", "default": 18},
                "font_name": {"type": "string", "default": "Arial"},
                "font_color": {"type": "string", "description": "#RRGGBB", "default": "#FFFFFF"},
                "outline_color": {"type": "string", "description": "#RRGGBB", "default": "#000000"},
                "outline_width": {"type": "number", "default": 1.0},
                "margin_v": {"type": "integer", "default": 20},
                "position": {"type": "string", "enum": ["top", "bottom"], "default": "bottom"},
                "watermark_text": {"type": "string"},
                "watermark_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"], "default": "top-right"},
                "watermark_font_size": {"type": "integer"},
                "watermark_color": {"type": "string", "description": "#RRGGBB"},
                "watermark_opacity": {"type": "number", "default": 0.72},
                "watermark_margin": {"type": "integer", "default": 24},
                "watermark_image_path": {"type": "string"},
                "watermark_image_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"], "default": "top-right"},
                "watermark_image_width": {"type": "integer"},
                "watermark_image_opacity": {"type": "number", "default": 0.72},
                "watermark_image_margin": {"type": "integer", "default": 24},
            },
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "video_output_path": {"type": "string"},
                "subtitle_path": {"type": "string"},
                "steps": {"type": "array"},
            },
        },
    },
    "dub": {
        "description": "Generate dubbed speech/audio for a local video using an existing subtitle file.",
        "input_schema": {
            "type": "object",
            "required": ["video_path", "subtitle_path"],
            "properties": {
                "video_path": {"type": "string"},
                "subtitle_path": {"type": "string"},
                "reference_subtitle_path": {"type": "string"},
                "voice": {"type": "string"},
                "language": {"type": "string", "default": "zh"},
                "out": {"type": "string"},
                "timeout": {"type": "number", "default": 1800},
            },
        },
        "output_schema": {"type": "object"},
    },
    "burn": {
        "description": "Burn subtitles into a local video with ffmpeg. This is local-only and supports subtitle style and watermark options.",
        "input_schema": {
            "type": "object",
            "required": ["video_path", "subtitle_path"],
            "properties": {
                "video_path": {"type": "string"},
                "subtitle_path": {"type": "string"},
                "out": {"type": "string"},
                "font_size": {"type": "integer"},
                "font_name": {"type": "string"},
                "font_color": {"type": "string", "description": "#RRGGBB"},
                "outline_color": {"type": "string", "description": "#RRGGBB"},
                "outline_width": {"type": "number"},
                "margin_v": {"type": "integer"},
                "position": {"type": "string", "enum": ["top", "bottom"], "default": "bottom"},
                "watermark_text": {"type": "string"},
                "watermark_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"], "default": "top-right"},
                "watermark_font_size": {"type": "integer"},
                "watermark_color": {"type": "string", "description": "#RRGGBB"},
                "watermark_opacity": {"type": "number", "default": 0.72},
                "watermark_margin": {"type": "integer", "default": 24},
                "watermark_image_path": {"type": "string"},
                "watermark_image_position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"], "default": "top-right"},
                "watermark_image_width": {"type": "integer"},
                "watermark_image_opacity": {"type": "number", "default": 0.72},
                "watermark_image_margin": {"type": "integer", "default": 24},
            },
        },
        "output_schema": {"type": "object"},
    },
    "mix_dubbed_audio": {
        "description": "Mix a generated dubbed audio track with the original local video audio and mux the result into a video. This is local-only and requires ffmpeg.",
        "input_schema": {
            "type": "object",
            "required": ["video_path", "dubbed_audio_path"],
            "properties": {
                "video_path": {"type": "string"},
                "dubbed_audio_path": {"type": "string"},
                "out": {"type": "string"},
                "original_volume": {"type": "number", "default": 0.65},
                "dubbed_volume": {"type": "number", "default": 1.0},
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
                "style_preset": {"type": "string"},
                "music_mode": {"type": "string", "default": "none"},
                "music_prompt": {"type": "string"},
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
                "generation_mode": {"type": "string", "enum": ["text", "first_frame", "reference"], "default": "text"},
                "first_frame_image_url": {"type": "string"},
                "reference_image_urls": {"type": "array", "items": {"type": "string"}},
                "reference_video_urls": {"type": "array", "items": {"type": "string"}},
                "reference_audio_urls": {"type": "array", "items": {"type": "string"}},
                "model": {"type": "string"},
                "model_name": {"type": "string"},
                "model_version": {"type": "string"},
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
                "task_intent": {
                    "type": "string",
                    "description": "High-priority app-surface intent, for example add_subtitles, translate_and_burn_subtitles, dub_video, summarize_video, shorten_video, generate_image, or generate_video.",
                },
                "task_parameters": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Explicit app slot values such as output_delivery=burned_video, target_language=en, source_language=auto, subtitle_language=en, or translation_mode=subtitle.",
                },
                "conversation_state": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Optional persisted agent state. Current prompt and task_parameters override historical defaults.",
                },
                "wait": {"type": "boolean", "default": False},
                "timeout": {"type": "number", "default": 1800},
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
