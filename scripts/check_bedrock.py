"""Smoke test: prove we can reach Bedrock and summarize a patent abstract.

No Neo4j involved, on purpose -- if this fails, the problem is AWS, not the
graph. Run it before ch6_summarize.py.

    uv run scripts/check_bedrock.py
"""

import sys

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from graphbook.bedrock import generate_text
from graphbook.config import get_settings

# A real abstract from the patents graph would do, but hardcoding one keeps
# this test independent of the database.
ABSTRACT = (
    "A method for training a machine learning model includes receiving a "
    "plurality of training samples, each comprising an input tensor and a "
    "corresponding label; partitioning the plurality of training samples into "
    "a training subset and a validation subset; iteratively adjusting a "
    "plurality of weights of the model by backpropagation of a loss computed "
    "over the training subset; and terminating the adjusting responsive to a "
    "loss computed over the validation subset failing to decrease across a "
    "predetermined number of successive iterations."
)

PROMPT = (
    "Summarize the following patent abstract in laymen's terms in fewer than "
    f"100 words: {ABSTRACT}"
)


def main() -> int:
    settings = get_settings().bedrock
    print(f"calling {settings.text_model} in {settings.region}")

    try:
        summary = generate_text(PROMPT)
    except NoCredentialsError:
        print(
            "no AWS credentials found — boto3 looks at env vars, "
            "~/.aws/credentials, and SSO",
            file=sys.stderr,
        )
        return 1
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "AccessDeniedException":
            print(
                f"access denied for {settings.text_model} — model access is "
                f"granted per model per region in the Bedrock console; check "
                f"it is enabled in {settings.region}",
                file=sys.stderr,
            )
        elif code == "ValidationException":
            print(f"bad request: {exc}", file=sys.stderr)
        else:
            print(f"bedrock call failed ({code}): {exc}", file=sys.stderr)
        return 1
    except BotoCoreError as exc:
        print(f"cannot reach bedrock: {exc}", file=sys.stderr)
        return 1

    print()
    print(summary)
    print()
    print(f"{len(summary.split())} words")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
