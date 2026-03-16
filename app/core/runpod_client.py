"""
RunPod serverless backend client.

Submits base64-encoded images to a RunPod serverless endpoint,
polls for job completion, and returns OCR results.

Expected worker input format:
  { "input": { "images": ["<base64>", ...], "output_format": "both" } }

Expected worker output format:
  { "markdown": "...", "json_result": [[...]] }
"""

import base64
import io
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2  # seconds between status polls
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"}


class RunPodClient:
    def __init__(self, endpoint_url: str, api_key: str, timeout: int = 300) -> None:
        self.endpoint_url = endpoint_url.rstrip("/")
        self.timeout = timeout
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def process_images(
        self,
        images: List[Image.Image],
        output_format: str = "both",
    ) -> Dict[str, Any]:
        """Encode images, submit to RunPod, poll until done, return output dict."""
        b64_images = []
        for img in images:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=95)
            b64_images.append(base64.b64encode(buf.getvalue()).decode())

        payload = {
            "input": {
                "images": b64_images,
                "output_format": output_format,
            }
        }

        with httpx.Client(timeout=self.timeout) as client:
            # Submit job
            resp = client.post(
                f"{self.endpoint_url}/run",
                json=payload,
                headers=self._headers,
            )
            resp.raise_for_status()
            job_id: str = resp.json()["id"]
            logger.info("RunPod job submitted: %s", job_id)

            # Poll for completion
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                status_resp = client.get(
                    f"{self.endpoint_url}/status/{job_id}",
                    headers=self._headers,
                )
                status_resp.raise_for_status()
                data = status_resp.json()
                state: str = data.get("status", "")

                if state == "COMPLETED":
                    output = data.get("output", {})
                    logger.info("RunPod job %s completed.", job_id)
                    return output

                if state in TERMINAL_STATES:
                    error = data.get("error", "")
                    raise RuntimeError(
                        f"RunPod job {job_id} ended with status '{state}': {error}"
                    )

                logger.debug("RunPod job %s status: %s — waiting...", job_id, state)
                time.sleep(POLL_INTERVAL)

        raise TimeoutError(
            f"RunPod job {job_id} did not complete within {self.timeout}s"
        )
