import re
from typing import Any

from imc_curator.config import load_ome_parser_config


def load_channel_parser_rules(
    *,
    required_groups: set[str],
) -> list[dict[str, Any]]:
    """Load enabled channel-parser rules from TOML and compile patterns.

    required_groups controls which named capture groups each enabled rule
    must define.
    """
    config = load_ome_parser_config()
    configured_rules = config.get("rules", [])

    if not isinstance(configured_rules, list):
        raise ValueError("The rules TOML must contain an array of [[rules]] tables.")

    rules: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for index, rule in enumerate(configured_rules, start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"Rule {index} must be a TOML table.")

        if not rule.get("enabled", True):
            continue

        rule_id = rule.get("id")
        pattern = rule.get("pattern")
        source = rule.get("source", "raw_name")

        if not isinstance(rule_id, str) or not rule_id.strip():
            raise ValueError(f"Enabled rule {index} must have a non-empty 'id'.")
        if rule_id in seen_ids:
            raise ValueError(f"Duplicate OME parser rule id: {rule_id}")
        if not isinstance(pattern, str) or not pattern:
            raise ValueError(f"Enabled rule {rule_id!r} must have a non-empty pattern.")
        if source not in {"raw_name", "raw_fluor"}:
            raise ValueError(
                f"Rule {rule_id!r} has unsupported source {source!r}; "
                "use 'raw_name' or 'raw_fluor'."
            )

        try:
            compiled_pattern = re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"Invalid regex in OME parser rule {rule_id!r}: {exc}"
            ) from exc

        group_names = set(compiled_pattern.groupindex)
        missing_groups = required_groups - group_names
        if missing_groups:
            raise ValueError(
                f"Rule {rule_id!r} must define named capture groups: "
                f"{', '.join(sorted(missing_groups))}"
            )

        rules.append({
            "id": rule_id,
            "description": str(rule.get("description", "")),
            "source": source,
            "pattern": pattern,
            "compiled_pattern": compiled_pattern,
        })
        seen_ids.add(rule_id)

    return rules
