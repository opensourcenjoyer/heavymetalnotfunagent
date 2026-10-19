"""Token metadata upload: bonk.fun uploader (keyless) or Pinata (needs a free JWT) for pump.fun."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import struct
import zlib
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from heavymetal import paths

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


class ImageSourceError(ValueError):
    pass


def resolve_local_image(image: str, images_dir: Path | None = None) -> Path:
    """Allow only files inside the images directory ($HEAVYMETAL_HOME/images).

    The `image` argument is written by the model, so any text the agent reads (token descriptions, memos,
    web pages) can steer it. Whatever this function returns is uploaded to public IPFS, so it must never
    resolve to wallet.json, config.toml or anything else outside the images folder.
    """
    root = (images_dir or paths.images_dir()).resolve()
    try:
        target = (root / Path(image).expanduser()).resolve(strict=True)
    except OSError as e:
        raise ImageSourceError(f"image not found: {image}") from e
    if root not in target.parents:
        raise ImageSourceError(f"image must be a URL or a file inside {root} (got {image})")
    if not target.is_file():
        raise ImageSourceError(f"image is not a file: {image}")
    return target


MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_REDIRECTS = 5


async def check_image_url(url: str) -> None:
    """Refuse URLs that point at this machine or the local network.

    Whatever the URL returns is uploaded to public IPFS, so a model-written URL must not be able to read
    localhost services, cloud metadata (169.254.169.254) or LAN hosts.
    """
    try:
        u = urlsplit(url)
    except ValueError as e:
        raise ImageSourceError(f"malformed image URL {url}") from e
    host = u.hostname or ""
    if u.scheme not in ("http", "https") or not host:
        raise ImageSourceError(f"image URL must be http(s) with a host (got {url})")
    try:
        # resolved off the event loop: a slow resolver must not stall the TUI and the scanner
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except OSError as e:
        raise ImageSourceError(f"cannot resolve image host {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise ImageSourceError(f"image URL resolves to a non-public address ({host} -> {ip})")


async def fetch_image_url(http: httpx.AsyncClient, url: str) -> bytes:
    """Download an image from a public URL.

    Redirects are not left to the client: each hop is checked before it is requested, so a public URL cannot
    bounce the fetch onto localhost or the LAN. The body is capped while it streams.
    """
    too_big = f"image larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB"
    try:
        for _ in range(MAX_IMAGE_REDIRECTS + 1):
            await check_image_url(url)
            async with http.stream("GET", url, timeout=30, follow_redirects=False) as r:
                if r.next_request is not None:
                    url = str(r.next_request.url)
                    continue
                r.raise_for_status()
                ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if not ctype.startswith("image/"):
                    raise ImageSourceError(f"image URL returned {ctype or 'no content-type'}, not an image")
                declared = r.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > MAX_IMAGE_BYTES:
                    raise ImageSourceError(too_big)
                data = bytearray()
                async for chunk in r.aiter_bytes():
                    data += chunk
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ImageSourceError(too_big)
                return bytes(data)
        raise ImageSourceError(f"image URL redirects more than {MAX_IMAGE_REDIRECTS} times")
    except httpx.HTTPError as e:
        raise ImageSourceError(f"cannot fetch image URL: {e}") from e


async def load_image(http: httpx.AsyncClient, image: str | None, images_dir: Path | None = None) -> bytes:
    image = (image or "").strip()
    if not image:
        return placeholder_png()
    if image.lower().startswith(("http://", "https://")):
        return await fetch_image_url(http, image)
    try:
        return resolve_local_image(image, images_dir).read_bytes()
    except OSError as e:
        raise ImageSourceError(f"cannot read image {image}: {e}") from e


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
