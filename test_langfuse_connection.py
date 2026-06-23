#!/usr/bin/env python3
"""Verify that Langfuse credentials are configured and working."""

import sys

from dotenv import load_dotenv

load_dotenv(override=True)

from langfuse import Langfuse


def main() -> None:
    try:
        client = Langfuse()
    except Exception as e:
        print(f"FAIL: Could not create Langfuse client: {e}")
        sys.exit(1)

    if not client.auth_check():
        print("FAIL: Langfuse auth_check() returned False.")
        print("Check that LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST are set correctly in .env")
        client.shutdown()
        sys.exit(1)

    print("Langfuse connection OK")
    print(f"  Host: {client.base_url}")
    client.shutdown()


if __name__ == "__main__":
    main()
