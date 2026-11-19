"""Review publishable source without staging files or disclosing matched secrets."""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    ".venv",
    ".uv-cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    ".next",
    ".cache",
    "artifacts",
    "test-results",
    "playwright-report",
    "checkpoints",
    "volumes",
    "pgdata",
    "secrets",
    ".secrets",
}
PRIVATE_SUFFIXES = {
    ".log",
    ".xml",
    ".pyc",
    ".db",
    ".db-journal",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".sql",
    ".dump",
    ".backup",
    ".gguf",
    ".safetensors",
    ".pt",
    ".pth",
    ".onnx",
    ".ckpt",
    ".bin",
    ".sqlite",
    ".sqlite3",
    ".wal",
    ".tsbuildinfo",
}
PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "provider-key": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "groq-key": re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}\b"),
    "github-token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
}
ASSIGNMENT = re.compile(
    r"(?i)(?:api_key|password|secret|token)\s*[=:]\s*[\"']([A-Za-z0-9_-]{32,})[\"']"
)


def private_path(path):
    parts = path.parts
    return (
        any(p in SKIP_DIRS for p in parts)
        or (path.name.startswith(".env") and path.name != ".env.example")
        or path.name.endswith(".env")
        or path.name.endswith((".credentials.json", ".tokens.json"))
        or path.suffix.lower() in PRIVATE_SUFFIXES
        or (path.suffix == ".jsonl" and parts[:2] != ("evaluations", "datasets"))
    )


def candidate_files(root):
    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (Path(folder) / d).is_symlink()]
        for name in files:
            path = Path(folder) / name
            if not private_path(path.relative_to(root)):
                yield path


def configured_secrets(root):
    values = set()
    for file in [*root.glob(".*.env"), root / ".env", root / "frontend/.env.local"]:
        for key, value in dotenv_values(file).items():
            if not value:
                continue
            if key.endswith(("KEY", "TOKEN", "PASSWORD")) and len(value) >= 20:
                values.add(value)
            if key.endswith("URL"):
                try:
                    if password := make_url(value).password:
                        values.add(password)
                except Exception:
                    pass
    return {v for v in values if len(v) >= 20}


def inspect_files(root, paths, secrets=()):
    findings, manifest = [], []
    for file in sorted(paths):
        path = file.relative_to(root)
        if private_path(path):
            findings.append({"path": path.as_posix(), "rule": "private-tracked-path"})
            continue
        if file.is_symlink() or not file.resolve().is_relative_to(root.resolve()):
            findings.append({"path": path.as_posix(), "rule": "symlink-or-external-path"})
            continue
        data = file.read_bytes()
        manifest.append(
            {
                "path": path.as_posix(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        if len(data) > 5_000_000:
            findings.append({"path": path.as_posix(), "rule": "oversized-release-file"})
        if file.suffix.lower() in {".png", ".jpg", ".webp", ".ico"}:
            continue  # Screenshots require visual inspection; not text-DLP evidence.
        text = data.decode("utf-8", errors="replace")
        for rule, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                findings.append(
                    {
                        "path": path.as_posix(),
                        "rule": rule,
                        "line": text.count("\n", 0, match.start()) + 1,
                    }
                )
        if any(s in text or s[:24] in text for s in secrets):
            findings.append({"path": path.as_posix(), "rule": "configured-credential-literal"})
        for match in ASSIGNMENT.finditer(text):
            value = match[1]
            entropy = -sum(
                (n / len(value)) * math.log2(n / len(value)) for n in Counter(value).values()
            )
            if entropy > 3.5 and not value.startswith(("replace", "generate", "stage", "test")):
                findings.append(
                    {
                        "path": path.as_posix(),
                        "rule": "high-entropy-assignment",
                        "line": text.count("\n", 0, match.start()) + 1,
                    }
                )
    return {
        "files": manifest,
        "findings": findings,
        "passed": not findings,
        "limitations": "Text/configured literals only; screenshots need visual review",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        parser.error("Write private hygiene evidence only inside project artifacts")
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False)
    paths = (
        [ROOT / p for p in tracked.stdout.decode().split("\0") if p]
        if tracked.returncode == 0
        else list(candidate_files(ROOT))
    )
    result = inspect_files(ROOT, paths, configured_secrets(ROOT))
    result["inventory_mode"] = "git-tracked" if tracked.returncode == 0 else "local-candidate-files"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "files": len(result["files"]),
                "findings": result["findings"],
                "mode": result["inventory_mode"],
            }
        )
    )
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
