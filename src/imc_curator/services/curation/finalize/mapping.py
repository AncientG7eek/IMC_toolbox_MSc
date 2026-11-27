from __future__ import annotations


def _final_marker_name(
    row: dict[str, str], proceed: bool
) -> str:
    corrected = row.get("user_corrected_marker", "").strip()
    if corrected:
        return corrected

    action = row.get("action", "").strip().upper()
    suggested = row.get("suggested_standardized_marker", "").strip()

    if action in {
        "REVIEW_MATCH",
        "ADD_NEW_ENTITY",
    }:
        return suggested

    if action == "RESOLVE_AMBIGUITY" and proceed:
        return suggested

    return ""


def _final_clinical_mapping(
    row: dict[str, str], proceed: bool
) -> tuple[str, str]:
    corrected_feature = row.get("user_corrected_feature", "").strip()
    corrected_value = row.get("user_corrected_value", "").strip()

    if corrected_feature or corrected_value:
        return corrected_feature, corrected_value

    action = row.get("action", "").strip()

    if action in [
        "REVIEW_MATCH",
        "ADD_NEW_ENTITY",
    ]:
        return (
            row.get("suggested_standardized_feature", "").strip(),
            row.get("suggested_standardized_value", "").strip(),
        )

    if action == "RESOLVE_AMBIGUITY" and proceed:
        return (
            row.get("suggested_standardized_feature", "").strip(),
            row.get("suggested_standardized_value", "").strip(),
        )

    return "", ""


def _append_alias(existing: str, alias: str) -> str:
    aliases = [
        item.strip()
        for item in existing.replace("|", ";").split(";")
        if item.strip()
    ]
    if alias and alias not in aliases:
        aliases.append(alias)
    return "; ".join(aliases)


def _validate_final_mappings(
    marker_sources: list[tuple[Path, list[dict[str, str]]]],
    clinical_sources: list[tuple[Path, list[dict[str, str]]]],
    proceed: bool,
) -> None:
    errors = []

    for path, rows in marker_sources:
        for row_number, row in enumerate(rows, start=2):
            if not row.get("original_marker", "").strip():
                continue
            if not _final_marker_name(row, proceed):
                errors.append(
                    f"{path}, CSV row {row_number}: "
                    "no final standardized marker"
                )

    for path, rows in clinical_sources:
        for row_number, row in enumerate(rows, start=2):
            if not row.get("original_feature", "").strip():
                continue
            feature, value = _final_clinical_mapping(row, proceed)
            if not feature or not value:
                errors.append(
                    f"{path}, CSV row {row_number}: "
                    "no final standardized feature/value"
                )

    if errors:
        raise ValueError(
            "Some rows have no usable final mapping. Correct the manifests "
            "before finalizing:\n- " + "\n- ".join(errors)
        )
