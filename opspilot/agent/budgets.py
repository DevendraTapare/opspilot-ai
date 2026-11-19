"""Offline, provider-neutral admission estimates, not a model tokenizer or quota oracle."""

import json

OUTPUT_RESERVATION = 1600


def estimate_input_tokens(value):
    # Deliberately conservative byte-equivalent accounting, including framing reserve.
    # Actual provider tokenization/quota admission can differ; never label this usage.
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) + 512
