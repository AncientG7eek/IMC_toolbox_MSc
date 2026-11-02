
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
    """Create a review manifest for one parsed marker table."""
    manifest_rows = []

    for row in marker_input["rows"]:
        original_marker = row.get("biological_marker", "").strip()
        if not original_marker:
            continue

        candidates = row.get("standardized_marker_candidates", [])
        unique_candidates = list(dict.fromkeys(candidates))

        if not unique_candidates:
            action = "ADD_NEW_ENTITY"
            suggestion = original_marker
            comment = "No match found; review adding this marker"
        elif len(unique_candidates) == 1:
            action = "REVIEW_MATCH"
            suggestion = unique_candidates[0]
            comment = "Please verify suggestion"
        else:
            action = "RESOLVE_AMBIGUITY"
            suggestion = ""
            comment = "Multiple matches; select or correct the mapping"

        manifest_rows.append({
            "source_file": marker_input["source_file"],
            "panel_id": marker_input["panel_id"],
            "original_marker": original_marker,
            "channel": row.get("channel", ""),
            "channel_number": row.get("channel_number", ""),
            "metal_isotope": row.get("metal_isotope", ""),
            "candidate_standardized_markers": " | ".join(
                str(candidate) for candidate in unique_candidates
            ),
            "action": action,
            "suggested_standardized_marker": suggestion,
            "approved": "0",
            "user_corrected_marker": "",
            "comment": comment,
        })

    fieldnames = [
        "source_file",
        "panel_id",
        "original_marker",
        "channel",
        "channel_number",
        "metal_isotope",
        "candidate_standardized_markers",
        "action",
        "suggested_standardized_marker",
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
    """Create a review manifest for one clinical matching table."""
    manifest_rows = []

    for feature, values in clinical_input["matches"].items():
        for original_value, candidates in values.items():
            # Distinct standardized pairs determine ambiguity.
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
                f'(cohort: {candidate.get("cohort", "")})'
                for candidate in candidates
            )

            if not standardized_pairs:
                action = "ADD_NEW_ENTITY"
                suggested_feature = feature
                suggested_value = original_value
                comment = (
                    "No match found; review adding this feature/value. "
                    "Confirm the standardized meaning before approval."
                )
            elif len(standardized_pairs) == 1:
                action = "REVIEW_MATCH"
                suggested_feature, suggested_value = standardized_pairs[0]
                comment = "Please verify suggestion"
            else:
                action = "RESOLVE_AMBIGUITY"
                suggested_feature = ""
                suggested_value = ""
                comment = (
                    "Multiple standardized mappings; resolve before approval"
                )

            manifest_rows.append({
                "source_file": clinical_input["source_file"],
                "original_feature": feature,
                "original_value": original_value,
                "candidate_mappings": candidate_text,
                "action": action,
                "suggested_standardized_feature": suggested_feature,
                "suggested_standardized_value": suggested_value,
                "approved": "0",
                "user_corrected_feature": "",
                "user_corrected_value": "",
                "comment": comment,
            })

    fieldnames = [
        "source_file",
        "original_feature",
        "original_value",
        "candidate_mappings",
        "action",
        "suggested_standardized_feature",
        "suggested_standardized_value",
        "approved",
        "user_corrected_feature",
        "user_corrected_value",
        "comment",
    ]

    _write_csv(output_path, fieldnames, manifest_rows)
    return output_path


def write_curation_manifests(
    project_dir: Path,
    marker_input: list[dict[str, Any]],
    clinical_input: list[dict[str, Any]],
) -> dict[str, list[Path]]:
    """Write one editable review manifest per extracted source table."""
    output_dir = project_dir / "curation_manifests" / "curate"
    marker_dir = output_dir / "markers"
    clinical_dir = output_dir / "clinical"

    # Remove only previously generated review CSVs in these dedicated
    # subdirectories, preventing stale manifests after source files change.
    for directory, suffix in (
        (marker_dir, "_marker_mapping_review.csv"),
        (clinical_dir, "_clinical_mapping_review.csv"),
    ):
        if directory.exists():
            for old_path in directory.glob(f"*{suffix}"):
                old_path.unlink()

    marker_paths: list[Path] = []
    clinical_paths: list[Path] = []

    for bundle in marker_input:
        stem = Path(bundle["source_file"]).stem.removesuffix("_parsed")
        path = marker_dir / f"{stem}_marker_mapping_review.csv"
        marker_paths.append(write_marker_manifest(bundle, path))

    for bundle in clinical_input:
        stem = Path(bundle["source_file"]).stem.removesuffix(
            "_image_clinical_matches"
        )
        path = clinical_dir / f"{stem}_clinical_mapping_review.csv"
        clinical_paths.append(write_clinical_manifest(bundle, path))

    return {
        "markers": marker_paths,
        "clinical": clinical_paths,
    }
