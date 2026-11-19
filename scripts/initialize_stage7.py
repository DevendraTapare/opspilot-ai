"""Create private credentials for the isolated review database; preserve existing files."""

import os
import secrets
from pathlib import Path


def main():
    target = Path(__file__).resolve().parents[1] / ".stage7.env"
    try:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(
                "STAGE7_DB_PORT=56437\nSTAGE7_POSTGRES_PASSWORD=" + secrets.token_hex(32) + "\n"
            )
        if os.name != "nt":
            target.chmod(0o600)
        print("Created private .stage7.env for the isolated Stage 7 database.")
    except FileExistsError:
        print("Preserved existing .stage7.env; credentials were not changed.")


if __name__ == "__main__":
    main()
