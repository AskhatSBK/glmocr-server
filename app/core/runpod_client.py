"""
RunPod serverless backend client.

Submits base64-encoded images to a RunPod serverless endpoint,
polls for job completion, and returns OCR results.

Worker input format (one request per page):
  { "input": { "image": "<base64>" } }

Worker output format:
  { "markdown": "...", "json_result": [...] }
"""

import base64
import io
import logging
import time
from typing import Any, Dict, List

import httpx
from PIL import Image

logger = logging.getLogger(__name__)

POLL_INTERVAL = 2
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
        """Send each page to RunPod one at a time, then merge results."""
        all_markdown: List[str] = []
        all_json: List[Any] = []

        with httpx.Client(timeout=self.timeout) as client:
            for i, img in enumerate(images):
                logger.info("Submitting page %d/%d to RunPod", i + 1, len(images))
                output = self._process_one(client, img)
                if output.get("markdown"):
                    all_markdown.append(output["markdown"])
                if output.get("json_result") is not None:
                    all_json.append(output["json_result"])

        return {
            "markdown": "\n\n".join(all_markdown) if all_markdown else None,
            "json_result": all_json if all_json else None,
        }

    def _process_one(self, client: httpx.Client, img: Image.Image) -> Dict[str, Any]:
        """Submit one image, poll until done, return output dict."""
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        b64 = base64.b64encode(buf.getvalue()).decode()

        resp = client.post(
            f"{self.endpoint_url}/run",
            json={"input": {"image": b64}},
            headers=self._headers,
        )
        resp.raise_for_status()
        job_id: str = resp.json()["id"]
        logger.info("RunPod job submitted: %s", job_id)

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
                logger.info("RunPod job %s completed.", job_id)
                return data.get("output", {})

            if state in TERMINAL_STATES:
                error = data.get("error", "")
                raise RuntimeError(
                    f"RunPod job {job_id} ended with status '{state}': {error}"
                )

            logger.debug("RunPod job %s: %s", job_id, state)
            time.sleep(POLL_INTERVAL)

        raise TimeoutError(f"RunPod job {job_id} did not complete within {self.timeout}s")
