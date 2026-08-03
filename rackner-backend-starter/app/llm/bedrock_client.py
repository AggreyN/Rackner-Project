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

from app import config


def _client():
    # Imported here (not at module top) so mock mode never touches boto3/AWS.
    import boto3

    return boto3.client("bedrock-runtime", region_name=config.AWS_REGION)


def invoke(system: str, user_prompt: str, max_tokens: int | None = None) -> str:
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
    response = _client().invoke_model(
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
