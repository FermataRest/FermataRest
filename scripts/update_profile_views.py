#!/usr/bin/env python3
"""Refresh the checked-in badge, retaining the last good SVG during outages.

Komarev counts GitHub Camo requests. This ordinary user agent reads the existing
counter without adding a view; the README's separate pixel records visits.
"""

from pathlib import Path
import os
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


BADGE_URL = "https://komarev.com/ghpvc/?username=FermataRest&style=flat"
BADGE_PATH = Path(__file__).resolve().parents[1] / "assets/profile-views.svg"
SVG_NS = "{http://www.w3.org/2000/svg}"
MAX_BYTES = 64 * 1024


class InvalidBadge(ValueError):
    pass


def badge_count(data):
    """Accept a real SVG badge with one unambiguous numeric count."""
    if not data or len(data) > MAX_BYTES or b"<!DOCTYPE" in data.upper():
        raise InvalidBadge("empty, oversized, or unsupported SVG")
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as error:
        raise InvalidBadge("malformed SVG") from error
    if root.tag != SVG_NS + "svg":
        raise InvalidBadge("response is not an SVG")
    texts = ["".join(node.itertext()).strip() for node in root.iter(SVG_NS + "text")]
    labels = [text for text in texts if text.casefold() == "profile views"]
    numbers = [text for text in texts if re.fullmatch(r"(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)", text)]
    counts = {int(text.replace(",", "")) for text in numbers}
    # Komarev duplicates the label and number to draw their shadows.
    if not labels or len(counts) != 1 or len(labels) + len(numbers) != len(texts):
        raise InvalidBadge("missing, ambiguous, or nonnumeric profile view count")
    return counts.pop()


def fetch_badge(minimum_count, opener=None, sleeper=time.sleep):
    opener = opener or urlopen
    request = Request(BADGE_URL, headers={
        "User-Agent": "profile-views-badge-updater/1.0",
        "Accept": "image/svg+xml",
    })
    for attempt in range(3):
        try:
            with opener(request, timeout=15) as response:
                if response.getcode() != 200:
                    raise InvalidBadge(f"HTTP {response.getcode()}")
                media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if media_type != "image/svg+xml":
                    raise InvalidBadge("response is not served as SVG")
                data = response.read(MAX_BYTES + 1)
            count = badge_count(data)
            if count < minimum_count:
                raise InvalidBadge(f"counter decreased from {minimum_count:,} to {count:,}")
            return data
        except HTTPError as error:
            error.close()
            if error.code != 429 and not 500 <= error.code < 600:
                raise
            last_error = error
        except (URLError, TimeoutError, OSError, InvalidBadge) as error:
            last_error = error
        if attempt < 2:
            sleeper(2 ** attempt)
    raise InvalidBadge(f"provider unavailable after 3 attempts: {last_error}")


def refresh_badge(path=BADGE_PATH, opener=None, sleeper=time.sleep):
    existing = path.read_bytes()
    count = badge_count(existing)
    try:
        updated = fetch_badge(count, opener=opener, sleeper=sleeper)
    except (HTTPError, URLError, TimeoutError, OSError, InvalidBadge) as error:
        print(f"Keeping the last good badge ({count:,} views): {error}", file=sys.stderr)
        return False
    if updated == existing:
        print(f"Badge already current ({count:,} views).")
        return False
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".profile-views-", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(updated)
        os.chmod(temporary_path, path.stat().st_mode & 0o777)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    print(f"Updated badge to {badge_count(updated):,} views.")
    return True


if __name__ == "__main__":
    try:
        refresh_badge()
    except (OSError, InvalidBadge) as error:
        # Never initialize/reset the counter if the committed badge is missing or invalid.
        print(f"Cannot refresh badge: {error}", file=sys.stderr)
        sys.exit(1)
