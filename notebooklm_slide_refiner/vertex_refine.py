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
MODEL_ENV_VAR = "VERTEX_MODEL_NAME"
MODEL_NAME_DEFAULT = "gemini-3-pro-image-preview"


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
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    return VertexConfig(project=project, location=location)


def get_model_name() -> str:
    return os.getenv(MODEL_ENV_VAR, MODEL_NAME_DEFAULT)


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


def _extract_image_bytes_from_generate(
    response: types.GenerateContentResponse,
) -> bytes:
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


def _extract_image_bytes_from_edit(response: types.EditImageResponse) -> bytes:
    for generated in response.generated_images or []:
        image = generated.image
        if not image or not image.image_bytes:
            continue
        return image.image_bytes
    raise RuntimeError("Vertex edit response did not include image bytes.")


def _extract_text_response(response: types.GenerateContentResponse) -> str | None:
    for candidate in response.candidates or []:
        if not candidate.content:
            continue
        for part in candidate.content.parts or []:
            text = getattr(part, "text", None)
            if text:
                return text
    return None


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
    model_name = get_model_name()

    try:
        response = client.models.generate_content(
            model=model_name,
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
        output_bytes = _extract_image_bytes_from_generate(response)
    except RuntimeError as exc:
        if "did not include image bytes" not in str(exc):
            raise
        try:
            edit_response = client.models.edit_image(
                model=model_name,
                prompt=prompt,
                reference_images=[
                    {
                        "reference_image": {
                            "image_bytes": image_bytes,
                            "mime_type": "image/png",
                        }
                    }
                ],
            )
            output_bytes = _extract_image_bytes_from_edit(edit_response)
        except Exception as edit_exc:  # noqa: BLE001 - normalize genai client errors
            status_code = getattr(edit_exc, "status_code", None)
            text_response = _extract_text_response(response)
            message = str(edit_exc)
            if status_code == 404 or "NOT_FOUND" in message:
                message = (
                    f"Vertex model not found or access denied: {model_name}. "
                    f"Set {MODEL_ENV_VAR} to a model available to your project."
                )
            if text_response:
                message = f"{message} Response text: {text_response}"
            raise VertexRefineError(message, status_code=status_code) from edit_exc
    except gcp_exceptions.GoogleAPICallError as exc:  # pragma: no cover - passthrough
        status_code = getattr(exc, "status_code", None)
        raise VertexRefineError(str(exc), status_code=status_code) from exc
    except Exception as exc:  # noqa: BLE001 - normalize genai client errors
        status_code = getattr(exc, "status_code", None)
        message = str(exc)
        if status_code == 404 or "NOT_FOUND" in message:
            message = (
                f"Vertex model not found or access denied: {model_name}. "
                f"Set {MODEL_ENV_VAR} to a model available to your project."
            )
        raise VertexRefineError(message, status_code=status_code) from exc
    enhanced_path.write_bytes(output_bytes)
