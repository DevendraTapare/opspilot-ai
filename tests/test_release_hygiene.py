"""Release checks must fail visibly without printing credential content."""

import secrets
from pathlib import Path

import pytest

from scripts.release_hygiene import inspect_files, private_path


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        "frontend/.env.local",
        ".stage8.env",
        ".groq.env",
        "artifacts/private.json",
        "models/weights.gguf",
        "volumes/data",
        "checkpoints/run.json",
        "tests/session.credentials.json",
        "tests/runtime.tokens.json",
    ],
)
def test_private_release_paths_are_rejected(name):
    assert private_path(Path(name))


def test_configured_credential_is_detected_without_echoing_value(tmp_path):
    credential = secrets.token_hex(32)
    file = tmp_path / "README.md"
    file.write_text("Accidentally copied credential: " + credential)
    result = inspect_files(tmp_path, [file], [credential])
    assert not result["passed"]
    assert result["findings"][0]["rule"] == "configured-credential-literal"
    assert credential not in str(result)


def test_groq_shaped_credential_is_detected_without_local_secret_configuration(tmp_path):
    credential = "gsk_" + secrets.token_hex(28)
    file = tmp_path / "README.md"
    file.write_text("Accidentally copied credential: " + credential)
    result = inspect_files(tmp_path, [file])
    assert not result["passed"]
    assert any(f["rule"] == "groq-key" for f in result["findings"])
    assert credential not in str(result)


def test_tracked_private_file_fails_even_if_gitignore_would_exclude_it(tmp_path):
    file = tmp_path / ".env"
    file.write_text("synthetic=example")
    result = inspect_files(tmp_path, [file])
    assert not result["passed"]
    assert result["findings"][0]["rule"] == "private-tracked-path"


def test_public_examples_and_historical_aggregates_remain_publishable():
    assert not private_path(Path(".env.example"))
    assert not private_path(Path("evaluations/reports/held-out-final.json"))
