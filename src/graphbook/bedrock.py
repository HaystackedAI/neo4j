"""AWS Bedrock text generation.

One client per process, same reasoning as the Neo4j driver: it holds a
connection pool and TLS session, so building one per call is wasteful.
"""

from functools import lru_cache
from typing import Any

import boto3

from graphbook.config import get_settings


@lru_cache(maxsize=1)
def get_client() -> Any:
    """Return the process-wide Bedrock runtime client.

    Credentials are boto3's problem, not ours -- it resolves them from the
    standard chain. Only the region comes from our settings.
    """
    return boto3.client(
        "bedrock-runtime",
        region_name=get_settings().bedrock.region,
    )


def generate_text(
    prompt: str,
    *,
    max_tokens: int = 300,
    temperature: float = 0.0,
) -> str:
    """Send one prompt to the configured text model; return the reply text.

    Uses the Converse API rather than `invoke_model`: Converse takes the same
    request shape for every model on Bedrock, so switching Nova -> Claude ->
    Llama is a config change. `invoke_model` requires each vendor's own JSON
    body, which is what makes older examples model-specific.
    """
    settings = get_settings().bedrock
    response = get_client().converse(
        modelId=settings.text_model,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
    )
    return response["output"]["message"]["content"][0]["text"]
