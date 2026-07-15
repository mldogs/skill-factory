#!/usr/bin/env python3
"""Generate an image via OpenRouter (IMG_MODEL) and cache it on disk.

Usage:
    python3 generate_image.py "<prompt>" <out_path> [--force]

Reads OPEN_ROUTER_API_KEY and IMG_MODEL from the environment. If they are not
already set, it loads them from the nearest .env file (walking up from the cwd
and from this script's directory). No third-party packages required — stdlib only.

Caching: if <out_path> already exists and is non-empty, the API call is SKIPPED
(prints "cached: <path>") unless --force is passed. Re-running the build is
therefore free after the first generation.

OpenRouter image-generation contract (verified against openrouter.ai/docs):
    POST https://openrouter.ai/api/v1/chat/completions
    headers: Authorization: Bearer <key>, Content-Type: application/json
    body:    {"model", "messages":[{"role":"user","content":<prompt>}],
              "modalities":["image","text"]}
    image:   choices[0].message.images[0].image_url.url  (base64 data URL)
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"


def normalize_to_extension(img_bytes, out_path):
    """Return bytes matching the format the extension promises.

    Image models sometimes return JPEG even when the cache path says .png;
    the lesson validator flags that as image_signature_mismatch. Convert via
    macOS `sips` (always present on darwin). If conversion is impossible the
    original bytes are kept with a warning — a mismatched image is still
    better than no image."""
    ext = os.path.splitext(out_path)[1].lower()
    want = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg"}.get(ext)
    is_png = img_bytes.startswith(PNG_MAGIC)
    is_jpeg = img_bytes.startswith(JPEG_MAGIC)
    if want is None or (want == "png" and is_png) or (want == "jpeg" and is_jpeg):
        return img_bytes
    src_suffix = ".jpg" if is_jpeg else ".png" if is_png else ".img"
    src = dst = None
    try:
        with tempfile.NamedTemporaryFile(suffix=src_suffix, delete=False) as fh:
            fh.write(img_bytes)
            src = fh.name
        dst = src + "." + want
        subprocess.run(
            ["sips", "-s", "format", want, src, "--out", dst],
            check=True, capture_output=True,
        )
        with open(dst, "rb") as fh:
            return fh.read()
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"warning: could not convert image to {want} ({e}); keeping "
              f"original bytes — the cached file will keep a mismatched "
              f"signature until regenerated with --force", file=sys.stderr)
        return img_bytes
    finally:
        for p in (src, dst):
            if p and os.path.exists(p):
                os.unlink(p)

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.1-flash-image-preview"

# Centralized art direction — appended to EVERY prompt so all lesson images share
# one consistent look. lesson.json prompts should describe the SUBJECT only.
# Override per-run with the IMG_STYLE env var, or skip with --no-style.
DEFAULT_STYLE = (
    "Art direction: clean modern FLAT EDITORIAL VECTOR illustration, friendly and minimal. "
    "Use only this cohesive palette: soft blue #5b8def, deep blue-ink #2d4f9e, "
    "warm coral #ff7a59 accents, gentle teal #2bb3a3, muted cream #f7f8fc background. "
    "Flat geometric shapes, subtle paper grain, soft long shadows, rounded forms, "
    "consistent thin line weight, generous negative space, a single centered subject, "
    "wide 16:9 composition. No text, no letters, no numbers, no UI chrome, no logos, no watermark."
)


def load_dotenv():
    """Populate os.environ from the nearest .env (never overwrites existing vars)."""
    seen = set()
    for start in (os.getcwd(), os.path.dirname(os.path.abspath(__file__))):
        d = start
        while d and d not in seen:
            seen.add(d)
            candidate = os.path.join(d, ".env")
            if os.path.isfile(candidate):
                with open(candidate, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        os.environ.setdefault(
                            key.strip(), val.strip().strip('"').strip("'")
                        )
                return candidate
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    return None


def generate_image(prompt, out_path, force=False, apply_style=True):
    if os.path.isfile(out_path) and os.path.getsize(out_path) > 0 and not force:
        print(f"cached: {out_path}")
        return out_path

    load_dotenv()
    api_key = os.environ.get("OPEN_ROUTER_API_KEY")
    if not api_key:
        sys.exit("ERROR: OPEN_ROUTER_API_KEY not set (and not found in any .env)")
    model = os.environ.get("IMG_MODEL", DEFAULT_MODEL)

    style = os.environ.get("IMG_STYLE", DEFAULT_STYLE) if apply_style else ""
    full_prompt = prompt.rstrip() + ("\n\n" + style if style else "")

    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": full_prompt}],
            "modalities": ["image", "text"],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "podcast-deepdive",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"ERROR: HTTP {e.code} from OpenRouter: {body[:600]}")
    except urllib.error.URLError as e:
        sys.exit(f"ERROR: network error: {e.reason}")

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError):
        sys.exit(f"ERROR: unexpected response shape: {json.dumps(data)[:600]}")

    images = message.get("images") or []
    if not images:
        sys.exit(
            "ERROR: no image returned. assistant text="
            f"{message.get('content')!r}; raw={json.dumps(data)[:400]}"
        )

    url = images[0]["image_url"]["url"]
    if not url.startswith("data:"):
        sys.exit(f"ERROR: image url is not a data URI: {url[:80]}")
    img_bytes = base64.b64decode(url.split(",", 1)[1])

    img_bytes = normalize_to_extension(img_bytes, out_path)

    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        prefix="." + os.path.basename(out_path) + ".", suffix=".tmp", dir=parent
    )
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(img_bytes)
        os.chmod(tmp, 0o644)
        os.replace(tmp, out_path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print(f"generated: {out_path} ({len(img_bytes)} bytes, model={model})")
    return out_path


def main(argv):
    force = "--force" in argv
    apply_style = "--no-style" not in argv
    args = [a for a in argv if a not in ("--force", "--no-style")]
    if len(args) < 2:
        sys.exit('Usage: generate_image.py "<prompt>" <out_path> [--force] [--no-style]')
    generate_image(args[0], args[1], force=force, apply_style=apply_style)


if __name__ == "__main__":
    main(sys.argv[1:])
