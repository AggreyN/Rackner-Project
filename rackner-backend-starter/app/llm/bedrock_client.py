"""Amazon Bedrock invocation for Claude Sonnet 4.5 (the real LLM path).

This module is only reached when LLM_MODE=bedrock. It is written and kept in the
repo so turning the gateway on is a config change, not a code change — but it is
imported lazily (inside the gateway) so `mock` mode needs neither boto3 wired to
AWS nor any credentials.

Transport: boto3 `bedrock-runtime.invoke_model` with the Anthropic Messages API
body (`anthropic_version: "bedrock-2023-05-31"`). Auth is standard AWS credential
resolution (env vars / profile / IAM role) — nothing is stored here.

Requirements to actually run this: AWS creds with `bedrock:InvokeModel`, and
Claude Sonnet 4.5 model access granted in the Bedrock console for AWS_REGION.
See docs/LLM_GATEWAY.md.
"""

import json
import logging
import threading

from app import config

_client_lock = threading.Lock()
_clients: dict[str, object] = {}


def _client(profile: str = "default"):
    """Shared bedrock-runtime clients (one per timeout profile), built under a
    lock — clients are thread-safe to SHARE; racing their creation is not.

    "default": generation work (extraction/analysis/chat) — patient reads and
    adaptive retries, because the caller is a background warm or a polling UI.
    "interactive": calls sitting inside a front-door request (the search-page
    pre-screen) — fail FAST and let the caller fall back; a wedged model call
    must never hold request threads and DB connections hostage.
    """
    if profile not in _clients:
        with _client_lock:
            if profile not in _clients:
                import boto3
                from botocore.config import Config as BotoConfig

                knobs = (
                    {"retries": {"max_attempts": 1}, "read_timeout": 20, "connect_timeout": 3}
                    if profile == "interactive"
                    else {
                        "retries": {"max_attempts": 6, "mode": "adaptive"},
                        "read_timeout": 120,
                        "connect_timeout": 5,
                    }
                )
                _clients[profile] = boto3.client(
                    "bedrock-runtime",
                    region_name=config.AWS_REGION,
                    config=BotoConfig(**knobs),
                )
    return _clients[profile]


def invoke(
    system: str,
    user_prompt: str,
    max_tokens: int | None = None,
    *,
    profile: str = "default",
) -> str:
    """Send one message to Claude on Bedrock and return the concatenated text.

    Raises whatever boto3 raises on failure (credentials, throttling, access) —
    the caller decides how to surface it. We do NOT silently fall back to the
    mock here; a misconfigured Bedrock should be a visible error, not fake data.
    """
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens or config.LLM_MAX_TOKENS,
        "system": system,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": user_prompt}]}
        ],
    }
    response = _client(profile).invoke_model(
        modelId=config.BEDROCK_MODEL_ID,
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )
    payload = json.loads(response["body"].read())

    # Token usage goes to the structured logs (cost visibility in CloudWatch).
    # Counts only — never prompt or completion text, which is document content.
    usage = payload.get("usage") or {}
    logging.getLogger("llm").info(
        "bedrock_invoke",
        extra={
            "model_id": config.BEDROCK_MODEL_ID,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        },
    )

    # Anthropic Messages response: `content` is a list of blocks.
    return "".join(
        block.get("text", "")
        for block in payload.get("content", [])
        if block.get("type") == "text"
    )
