"""HuggingFace Inference API image provider.

Uses the HF Inference API endpoint with a configured model
(default: ``black-forest-labs/FLUX.1-schnell``).

Requires the ``HUGGINGFACE_API_TOKEN`` environment variable.
"""

from __future__ import annotations

import json
import random
import time
import urllib.request
import urllib.error
from pathlib import Path

from image_engine.base import (
    BaseProvider,
    ConfigurationError,
    GeneratedImage,
    GenerationError,
)


class HuggingFaceProvider(BaseProvider):
    """Provider that generates images via the HuggingFace Inference API.

    Uses the ``@cfhf/text-to-image`` style endpoint:

        https://api-inference.huggingface.co/models/{model}

    Requires ``HUGGINGFACE_API_TOKEN`` to be set in environment or settings.

    Attributes:
        name: Provider identifier (``"huggingface"``).
    """

    name: str = "huggingface"

    def __init__(
        self,
        api_token: str | None = None,
        model: str | None = None,
    ) -> None:
        """Initialise with optional overrides.

        Args:
            api_token: HuggingFace API token. Falls back to
                ``settings.HUGGINGFACE_API_TOKEN``.
            model:     Model ID on HuggingFace. Falls back to
                ``settings.HUGGINGFACE_MODEL``.
        """
        from config.settings import HUGGINGFACE_API_TOKEN, HUGGINGFACE_MODEL

        self._api_token: str = api_token or HUGGINGFACE_API_TOKEN
        self._model: str = model or HUGGINGFACE_MODEL or "black-forest-labs/FLUX.1-schnell"
        super().__init__()

    def _validate_config(self) -> None:
        """Raise :class:`ConfigurationError` if the API token is missing."""
        if not self._api_token:
            raise ConfigurationError(
                "HUGGINGFACE_API_TOKEN is not set. "
                "Set the environment variable or pass api_token explicitly."
            )

    def generate(self, prompt: str, seed: int | None = None) -> GeneratedImage:
        """Generate an image via the HuggingFace Inference API.

        Args:
            prompt: Text prompt describing the desired image.
            seed:   Optional seed (passed as a generation parameter).

        Returns:
            A :class:`GeneratedImage` with the downloaded file.

        Raises:
            GenerationError: If the API request fails or returns no data.
        """
        start = time.perf_counter()
        rng_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

        try:
            url = f"https://api-inference.huggingface.co/models/{self._model}"

            payload = json.dumps({
                "inputs": prompt,
                "parameters": {
                    "seed": rng_seed,
                },
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Authorization": f"Bearer {self._api_token}",
                    "Content-Type": "application/json",
                    "User-Agent": (
                        "BloggerAIPublisher/1.0 "
                        "(image-generation-engine)"
                    ),
                },
            )

            with urllib.request.urlopen(req, timeout=120) as response:
                image_data = response.read()

            if not image_data:
                raise GenerationError("HuggingFace returned empty response")

            # Check if response is JSON (error) or binary (image)
            if image_data[:1] == b"{":
                try:
                    err = json.loads(image_data)
                    error_msg = err.get("error", str(err))
                    raise GenerationError(
                        f"HuggingFace API error: {error_msg}"
                    )
                except json.JSONDecodeError:
                    pass  # Not JSON — proceed as binary

            temp_dir = Path("/tmp") / "huggingface_images"
            temp_dir.mkdir(parents=True, exist_ok=True)
            out_path = temp_dir / f"huggingface_{rng_seed}.webp"
            out_path.write_bytes(image_data)

            elapsed = int((time.perf_counter() - start) * 1000)

            return GeneratedImage(
                image_path=out_path,
                provider=self.name,
                generation_seed=rng_seed,
                generation_time_ms=elapsed,
            )

        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise GenerationError(
                f"HuggingFace HTTP {exc.code}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise GenerationError(
                f"HuggingFace API request failed: {exc}"
            ) from exc
        except OSError as exc:
            raise GenerationError(
                f"HuggingFace file write failed: {exc}"
            ) from exc
