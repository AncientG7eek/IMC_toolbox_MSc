from __future__ import annotations

import hashlib
from typing import Any


def normalize_signature_value(value: Any) -> str:
    """Return a stable normalized text token used in signatures."""
    return str(value or "").strip().casefold()


def default_channel_sort_key(channel: dict[str, Any]) -> tuple[int, str, str]:
    """Sort channels by number first, then stable text fields."""
    try:
        number = int(channel.get("channel_number") or 0)
    except (TypeError, ValueError):
        number = 0

    return (
        number,
        str(channel.get("channel_id") or ""),
        str(channel.get("raw_name") or ""),
    )


def marker_signature_token(
    *,
    biological_marker: Any,
    raw_name: Any = "",
    raw_fluor: Any = "",
) -> str:
    """Build one canonical marker token for panel signatures.

    If no parsed marker exists, a prefixed fallback token is used so that
    unknown channels are visible and deterministic in deduplication.
    """
    marker = normalize_signature_value(biological_marker)

    if marker:
        return marker

    raw_name_norm = normalize_signature_value(raw_name)
    raw_fluor_norm = normalize_signature_value(raw_fluor)
    fallback = raw_name_norm or raw_fluor_norm or "<unnamed-channel>"
    return f"unparsed:{fallback}"


def build_panel_signature(
    channels: list[dict[str, Any]],
    *,
    marker_key: str = "biological_marker",
    raw_name_key: str = "raw_name",
    raw_fluor_key: str = "raw_fluor",
    channel_sort_key=default_channel_sort_key,
) -> list[str]:
    """Build a canonical marker-set signature from channel records.

    Signature semantics:
      - marker-only (metal/fluor ignored)
      - order-independent (set semantics)
      - alphabetically sorted (stable representation)
    """
    _ = channel_sort_key
    marker_set = {
        marker_signature_token(
            biological_marker=channel.get(marker_key),
            raw_name=channel.get(raw_name_key),
            raw_fluor=channel.get(raw_fluor_key),
        )
        for channel in channels
    }

    return sorted(marker_set)


def build_panel_id(signature: list[str]) -> str:
    """Build a stable panel ID from a canonical signature."""
    signature_text = "\n".join(signature)
    digest = hashlib.sha1(signature_text.encode("utf-8")).hexdigest()[:10]
    return f"panel_{digest}"


def format_panel_signature(signature: list[str]) -> str:
    """Return a compact single-line representation for CSV/report fields."""
    return "; ".join(signature)