"""Vertex AI image refinement implementation."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from google import genai
from google.api_core import exceptions as gcp_exceptions
from google.genai import types

PROMPT_PATH = Path(__file__).parent / "prompts" / "default.txt"
MODEL_NAME = "gemini-3-pro-image-preview"


@dataclass(frozen=True)
class VertexConfig:
    project: str
    location: str


class VertexRefineError(RuntimeError):
    """Vertex image refinement error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def load_prompt(remove_corner_marks: bool) -> str:
    """Load the prompt template and inject corner mark behavior."""

    template = PROMPT_PATH.read_text(encoding="utf-8")
    if remove_corner_marks:
        corner_text = "Remove any corner marks or page indices if present."
    else:
        corner_text = "Preserve any corner marks or page indices if present."
    return template.replace("{{REMOVE_CORNER_MARKS}}", corner_text)


def build_vertex_config() -> VertexConfig:
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT is required for Vertex refine.")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    return VertexConfig(project=project, location=location)


def is_retryable_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            gcp_exceptions.TooManyRequests,
            gcp_exceptions.InternalServerError,
            gcp_exceptions.ServiceUnavailable,
        ),
    ):
        return True

    status_code = getattr(exc, "status_code", None)
    if status_code is None and isinstance(exc, gcp_exceptions.GoogleAPICallError):
        code = getattr(exc, "code", None)
        if callable(code):
            code = code()
        if isinstance(code, int):
            status_code = code
        elif hasattr(code, "value"):
            try:
                status_code = int(code.value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                status_code = None

    return bool(status_code == 429 or (status_code and 500 <= status_code <= 599))


def _extract_image_bytes(response: types.GenerateContentResponse) -> bytes:
    for candidate in response.candidates or []:
        if not candidate.content:
            continue
        for part in candidate.content.parts or []:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and inline_data.data:
                data = inline_data.data
                if isinstance(data, bytes):
                    return data
                if isinstance(data, str):
                    return base64.b64decode(data)
    raise RuntimeError("Vertex response did not include image bytes.")


def refine_with_vertex(
    raw_path: Path,
    enhanced_path: Path,
    prompt: str,
    config: VertexConfig,
) -> None:
    """Call Vertex Gemini image editing and write enhanced PNG."""

    enhanced_path.parent.mkdir(parents=True, exist_ok=True)
    image_bytes = raw_path.read_bytes()

    client = genai.Client(vertexai=True, project=config.project, location=config.location)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    ],
                )
            ],
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )
    except gcp_exceptions.GoogleAPICallError as exc:  # pragma: no cover - passthrough
        status_code = getattr(exc, "status_code", None)
        raise VertexRefineError(str(exc), status_code=status_code) from exc

    output_bytes = _extract_image_bytes(response)
    enhanced_path.write_bytes(output_bytes)
