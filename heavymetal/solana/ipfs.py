"""Token metadata upload: bonk.fun uploader (keyless) or Pinata (needs a free JWT) for pump.fun."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import httpx

BONK_IMG = "https://nft-storage.letsbonk22.workers.dev/upload/img"
BONK_META = "https://nft-storage.letsbonk22.workers.dev/upload/meta"
PINATA = "https://uploads.pinata.cloud/v3/files"


def placeholder_png(rgb: tuple[int, int, int] = (153, 69, 255), size: int = 256) -> bytes:
    """A solid-colour PNG with no image library."""
    raw = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


async def load_image(http: httpx.AsyncClient, image: str | None) -> bytes:
    if not image:
        return placeholder_png()
    if image.startswith(("http://", "https://")):
        r = await http.get(image, timeout=30)
        r.raise_for_status()
        return r.content
    return Path(image).expanduser().read_bytes()


async def upload_bonk(http: httpx.AsyncClient, img: bytes, meta: dict) -> str:
    r = await http.post(BONK_IMG, files={"image": ("image.png", img, "image/png")}, timeout=60)
    r.raise_for_status()
    image_uri = r.text.strip()
    body = {"createdOn": "https://bonk.fun", "image": image_uri, **meta}
    r = await http.post(BONK_META, content=json.dumps(body), headers={"Content-Type": "application/json"}, timeout=60)
    r.raise_for_status()
    return r.text.strip()


async def upload_pinata(http: httpx.AsyncClient, jwt: str, img: bytes, meta: dict) -> str:
    if not jwt:
        raise RuntimeError("pump.fun launches need keys.pinata_jwt (free at pinata.cloud); or use pool='bonk'")
    h = {"Authorization": f"Bearer {jwt}"}
    r = await http.post(
        PINATA, headers=h, data={"network": "public"}, files={"file": ("image.png", img, "image/png")}, timeout=60
    )
    r.raise_for_status()
    image = f"https://ipfs.io/ipfs/{r.json()['data']['cid']}"
    r = await http.post(
        PINATA,
        headers=h,
        data={"network": "public"},
        files={"file": ("metadata.json", json.dumps({**meta, "image": image}), "application/json")},
        timeout=60,
    )
    r.raise_for_status()
    return f"https://ipfs.io/ipfs/{r.json()['data']['cid']}"
