"""The agent's own wallet. Stored as a Solana-CLI-compatible JSON byte array, chmod 600."""

from __future__ import annotations

import json
import os
from pathlib import Path

from solders.keypair import Keypair

from heavymetal import paths


def load_or_create(path: Path | None = None) -> tuple[Keypair, bool]:
    """Returns (keypair, created_now)."""
    path = path or paths.wallet_path()
    if path.exists():
        data = json.loads(path.read_text())
        return Keypair.from_bytes(bytes(data)), False
    kp = Keypair()
    # create with 600 perms from the start (no window where it is world-readable)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(list(bytes(kp)), f)
    return kp, True
