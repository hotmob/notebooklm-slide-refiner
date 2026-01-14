"""Image refinement via stub or Gemini Nano Banana."""

from __future__ import annotations

import base64
import os
import shutil
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

PROMPT_PATH = Path(__file__).parent / "prompts" / "default.txt"
DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_VERTEX_REGION = "us-central1"


class Refiner(ABC):
    """Abstract refiner interface."""

    @abstractmethod
    def refine(self, raw_path: Path, enhanced_path: Path, prompt: str) -> None:
        """Refine a raw image and write enhanced output."""


class StubRefiner(Refiner):
    """Stub refiner that copies raw image to enhanced output."""

    def refine(self, raw_path: Path, enhanced_path: Path, prompt: str) -> None:
        enhanced_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(raw_path, enhanced_path)


class GeminiNanoBananaRefiner(Refiner):
    """Gemini Nano Banana image editor refiner."""

    def __init__(
        self,
        auth_token: str,
        model: str,
        endpoint: str | None = None,
        use_oauth: bool = False,
    ) -> None:
        self.auth_token = auth_token
        self.model = model
        self.endpoint = endpoint or "https://generativelanguage.googleapis.com/v1beta"
        self.use_oauth = use_oauth

    def refine(self, raw_path: Path, enhanced_path: Path, prompt: str) -> None:
        enhanced_path.parent.mkdir(parents=True, exist_ok=True)
        image_bytes = raw_path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("utf-8")

        # TODO: Adapt request body for your Gemini/Vertex endpoint.
        url = f"{self.endpoint}/models/{self.model}:generateContent"
        headers = None
        if self.use_oauth:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
        else:
            url = f"{url}?key={self.auth_token}"
        payload: dict[str, Any] = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": encoded,
                            }
                        },
                    ]
                }
            ]
        }

        with httpx.Client(timeout=120) as client:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                raise GeminiAPIError(
                    status_code=response.status_code,
                    message=response.text,
                )
            data = response.json()

        # TODO: Adjust response parsing for your endpoint.
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini API returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise RuntimeError("Gemini API response missing parts.")
        image_part = next((part for part in parts if "inline_data" in part), None)
        if not image_part:
            raise RuntimeError("Gemini API response missing inline_data.")
        image_data = image_part["inline_data"]["data"]
        output_bytes = base64.b64decode(image_data)
        enhanced_path.write_bytes(output_bytes)


def load_prompt(remove_corner_marks: bool) -> str:
    """Load prompt template and inject options."""

    template = PROMPT_PATH.read_text(encoding="utf-8")
    if remove_corner_marks:
        corner_text = "Remove any corner marks or page indices if present."
    else:
        corner_text = "Preserve any corner marks or page indices if present."
    return template.replace("{{REMOVE_CORNER_MARKS}}", corner_text)


def _is_vertex_endpoint(endpoint: str) -> bool:
    return "aiplatform.googleapis.com" in endpoint


def _vertex_credentials_path() -> Path | None:
    credentials_path = os.getenv("GEMINI_CREDENTIALS") or os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS"
    )
    if not credentials_path:
        return None
    return Path(credentials_path)


def _load_vertex_credentials(credentials_file: Path) -> tuple[str, str | None]:
    if not credentials_file.is_file():
        raise RuntimeError(f"Credentials file not found: {credentials_file}")

    try:
        from google.auth import load_credentials_from_file
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise RuntimeError(
            "google-auth is required to use credentials JSON. "
            "Install it with `pip install google-auth`."
        ) from exc

    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    credentials, project_id = load_credentials_from_file(str(credentials_file), scopes=scopes)
    credentials.refresh(Request())
    if not credentials.token:
        raise RuntimeError("Failed to obtain access token from credentials file.")
    return credentials.token, project_id


def _load_vertex_token(credentials_file: Path | None = None) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        return api_key

    credentials_file = credentials_file or _vertex_credentials_path()
    if not credentials_file:
        raise RuntimeError(
            "Vertex endpoint requires GEMINI_API_KEY (access token) or "
            "GEMINI_CREDENTIALS/GOOGLE_APPLICATION_CREDENTIALS."
        )

    token, _ = _load_vertex_credentials(credentials_file)
    return token


def _build_vertex_endpoint(project_id: str, region: str) -> str:
    return (
        f"https://{region}-aiplatform.googleapis.com/v1/projects/{project_id}"
        f"/locations/{region}/publishers/google"
    )


def get_refiner() -> Refiner:
    """Get refiner based on environment variables."""

    mode = os.getenv("REFINER_MODE", "stub").lower()
    if mode == "gemini":
        model = os.getenv("GEMINI_MODEL", "nano-banana")
        endpoint = os.getenv("GEMINI_ENDPOINT")
        credentials_file = _vertex_credentials_path()

        if endpoint:
            resolved_endpoint = endpoint
            if _is_vertex_endpoint(resolved_endpoint):
                token = _load_vertex_token(credentials_file)
                return GeminiNanoBananaRefiner(
                    auth_token=token,
                    model=model,
                    endpoint=resolved_endpoint,
                    use_oauth=True,
                )

            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY is required for gemini mode.")
            return GeminiNanoBananaRefiner(
                auth_token=api_key,
                model=model,
                endpoint=resolved_endpoint,
            )

        if credentials_file:
            token, project_id = _load_vertex_credentials(credentials_file)
            if not project_id:
                raise RuntimeError(
                    "Project ID not found in credentials file. "
                    "Set GEMINI_ENDPOINT explicitly."
                )
            region = os.getenv("GEMINI_VERTEX_REGION", DEFAULT_VERTEX_REGION).strip()
            if not region:
                raise RuntimeError("GEMINI_VERTEX_REGION is empty.")
            resolved_endpoint = _build_vertex_endpoint(project_id, region)
            return GeminiNanoBananaRefiner(
                auth_token=token,
                model=model,
                endpoint=resolved_endpoint,
                use_oauth=True,
            )

        resolved_endpoint = DEFAULT_ENDPOINT
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is required for gemini mode.")
        return GeminiNanoBananaRefiner(
            auth_token=api_key,
            model=model,
            endpoint=resolved_endpoint,
        )
    return StubRefiner()


def rate_limit_wait(rate_limit_path: Path, rps: float) -> None:
    """Simple file-based rate limiter to cap requests per second."""

    if rps <= 0:
        return
    interval = 1.0 / rps
    rate_limit_path.parent.mkdir(parents=True, exist_ok=True)
    rate_limit_path.touch(exist_ok=True)
    with rate_limit_path.open("r+") as handle:
        try:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX)
        except ImportError:
            pass
        handle.seek(0)
        content = handle.read().strip()
        last = float(content) if content else 0.0
        now = time.monotonic()
        wait = interval - (now - last)
        if wait > 0:
            time.sleep(wait)
        handle.seek(0)
        handle.truncate()
        handle.write(str(time.monotonic()))
        handle.flush()
        try:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_UN)
        except ImportError:
            pass


def is_retryable(status_code: int) -> bool:
    """Return True if status code should be retried."""

    return status_code == 429 or 500 <= status_code <= 599


def backoff_sleep(attempt: int) -> None:
    """Exponential backoff with jitter."""

    base = 1.5 ** attempt
    jitter = 0.1 * attempt
    time.sleep(base + jitter)


class GeminiAPIError(RuntimeError):
    """Gemini API error with status code."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Gemini API error {status_code}: {message}")
        self.status_code = status_code
