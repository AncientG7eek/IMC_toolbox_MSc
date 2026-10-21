
import csv
from pathlib import Path
from typing import Any


def _write_csv(
    path: Path,
    fieldnames: list[str],
    rows: list[dict[str, Any]],
) -> None:
    """Write an editable CSV manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_marker_manifest(
    marker_input: dict[str, Any],
    output_path: Path,
) -> Path:
    """Create an editable marker mapping and new-entity review manifest."""
    manifest_rows = []

    for row in marker_input["rows"]:
        original_marker = row.get("biological_marker", "").strip()
        candidates = row.get("standardized_marker_candidates", [])

        unique_candidates = list(dict.fromkeys(candidates))

        if not unique_candidates:
            action = "ADD_NEW_ENTITY"
            suggestion = ""
            proposed_new_entity = original_marker
            comment = "No match found; review adding this marker"
        elif len(unique_candidates) == 1:
            action = "REVIEW_MATCH"
            suggestion = unique_candidates[0]
            proposed_new_entity = ""
            comment = "Please verify suggestion"
        else:
            action = "RESOLVE_AMBIGUITY"
            suggestion = ""
            proposed_new_entity = ""
            comment = "Multiple matches; select or correct the mapping"

        manifest_rows.append({
            "original_marker": original_marker,
            "channel": row.get("channel", ""),
            "channel_number": row.get("channel_number", ""),
            "metal_isotope": row.get("metal_isotope", ""),
            "candidate_standardized_markers": " | ".join(unique_candidates),
            "action": action,
            "suggested_standardized_marker": suggestion,
            "proposed_new_standardized_marker": proposed_new_entity,
            "approved": "0",
            "user_corrected_marker": "",
            "comment": comment,
        })

    fieldnames = [
        "original_marker",
        "channel",
        "channel_number",
        "metal_isotope",
        "candidate_standardized_markers",
        "action",
        "suggested_standardized_marker",
        "proposed_new_standardized_marker",
        "approved",
        "user_corrected_marker",
        "comment",
    ]

    _write_csv(output_path, fieldnames, manifest_rows)
    return output_path


def write_clinical_manifest(
    clinical_input: dict[str, Any],
    output_path: Path,
) -> Path:
    """Create an editable clinical mapping and new-entity review manifest."""
    manifest_rows = []

    for feature, values in clinical_input["matches"].items():
        for original_value, candidates in values.items():
            # Different cohorts may have duplicate mappings to the same
            # standardized pair. Only distinct pairs create ambiguity.
            standardized_pairs = list(dict.fromkeys(
                (
                    candidate["standardized_feature"],
                    candidate["standardized_value"],
                )
                for candidate in candidates
            ))

            candidate_text = " | ".join(
                f'{candidate["standardized_feature"]}='
                f'{candidate["standardized_value"]} '
                f'(cohort: {candidate["cohort"]})'
                for candidate in candidates
            )

            if not standardized_pairs:
                action = "ADD_NEW_ENTITY"
                suggested_feature = ""
                suggested_value = ""
                proposed_feature = feature
                proposed_value = original_value
                comment = (
                    "No match found; review adding this feature/value. "
                    "Confirm the standardized meaning before approval."
                )
            elif len(standardized_pairs) == 1:
                action = "REVIEW_MATCH"
                suggested_feature, suggested_value = standardized_pairs[0]
                proposed_feature = ""
                proposed_value = ""
                comment = "Please verify suggestion"
            else:
                action = "RESOLVE_AMBIGUITY"
                suggested_feature = ""
                suggested_value = ""
                proposed_feature = ""
                proposed_value = ""
                comment = (
                    "Multiple standardized mappings; resolve before approval"
                )

            manifest_rows.append({
                "original_feature": feature,
                "original_value": original_value,
                "candidate_mappings": candidate_text,
                "action": action,
                "suggested_standardized_feature": suggested_feature,
                "suggested_standardized_value": suggested_value,
                "proposed_new_standardized_feature": proposed_feature,
                "proposed_new_standardized_value": proposed_value,
                "approved": "0",
                "user_corrected_feature": "",
                "user_corrected_value": "",
                "comment": comment,
            })

    fieldnames = [
        "original_feature",
        "original_value",
        "candidate_mappings",
        "action",
        "suggested_standardized_feature",
        "suggested_standardized_value",
        "proposed_new_standardized_feature",
        "proposed_new_standardized_value",
        "approved",
        "user_corrected_feature",
        "user_corrected_value",
        "comment",
    ]

    _write_csv(output_path, fieldnames, manifest_rows)
    return output_path



def write_curation_manifests(
    project_dir: Path,
    marker_input: dict[str, Any],
    clinical_input: dict[str, Any],
) -> dict[str, Path]:
    """Write both review manifests for a project."""
    output_dir = project_dir / "curation_manifests" / "curate"

    marker_path = write_marker_manifest(
        marker_input,
        output_dir / "marker_mapping_review.csv",
    )

    clinical_path = write_clinical_manifest(
        clinical_input,
        output_dir / "clinical_mapping_review.csv",
    )

    return {
        "markers": marker_path,
        "clinical": clinical_path,
    }
