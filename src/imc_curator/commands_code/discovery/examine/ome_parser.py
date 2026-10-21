from pathlib import Path

from imc_curator.commands_code.discovery.examine.submodules.extract_ome_channels import (
    CHANNEL_COLUMNS,
    SCAN_COLUMNS,
    extract_all_tiff_metadata,
    write_csv,
)
from imc_curator.commands_code.discovery.examine.submodules.ome_panel_parser import (
    assign_panels,
    load_regex_rules,
    parse_channel,
    write_panel_reports,
)


def examine_ome_metadata(
    input_dir: Path,
    output_dir: Path,
    logs_dir: Path,
    rules_path: Path,
) -> str:
    """Extract OME metadata, parse channel names, and identify candidate panels."""
    input_dir = input_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    logs_dir = logs_dir.expanduser().resolve()
    rules_path = rules_path.expanduser().resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Extract raw OME metadata.
    channels, scan_records = extract_all_tiff_metadata(input_dir)

    scan_csv = write_csv(
        logs_dir / "tiff_metadata_scan.csv",
        SCAN_COLUMNS,
        scan_records,
    )

    if not channels:
        return (
            "OME metadata examination finished with a warning.\n"
            "No channel information was found in the TIFF files.\n"
            f"TIFF scan report: {scan_csv}\n"
            "Channel parsing and panel identification were skipped."
        )

    channels_csv = write_csv(
        output_dir / "raw_ome_channels.csv",
        CHANNEL_COLUMNS,
        channels,
    )

    # 2. Parse channel names using the configured regex rules.
    rules = load_regex_rules(rules_path)
    parsed_channels = [
        parse_channel(channel, rules)
        for channel in channels
    ]

    # 3. Group TIFFs by their parsed channel signatures.
    panel_groups = assign_panels(parsed_channels)

    # 4. Write parsed-channel and panel-manifest reports.
    parsed_csv, manifest_paths = write_panel_reports(
        parsed_channels=parsed_channels,
        panel_groups=panel_groups,
        output_dir=output_dir,
    )

    parsed_channel_count = sum(
        channel["parse_status"] == "parsed"
        for channel in parsed_channels
    )
    channels_needing_review = sum(
        channel["parse_status"] == "needs_review"
        for channel in parsed_channels
    )

    report = [
        "",
        "OME metadata examination complete",
        "=" * 34,
        "",
        "Output files:",
        f"  Raw OME channels:       {channels_csv}",
        f"  TIFF metadata scan:     {scan_csv}",
        f"  Parsed channels:        {parsed_csv}",
        "",
        "Summary:",
        f"  TIFF panel groups:      {len(panel_groups)}",
        f"  Panel manifests:        {len(manifest_paths)}",
        f"  Parsed channels:        {parsed_channel_count}",
        f"  Channels needing review: {channels_needing_review}",
    ]

    return "\n".join(report)
