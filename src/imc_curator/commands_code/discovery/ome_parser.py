from pathlib import Path

from imc_curator.commands_code.discovery.scripts.ome_parser.extract_ome_channels import (
    CHANNEL_COLUMNS,
    SCAN_COLUMNS,
    extract_all_tiff_metadata,
    write_csv,
)
from imc_curator.commands_code.discovery.scripts.ome_parser.ome_panel_parser import (
    assign_panels,
    load_regex_rules,
    parse_channel,
    write_panel_reports,
)


def examine_ome_metadata(
    input_dir: Path,
    output_dir: Path,
    rules_path: Path,
) -> dict[str, Path | int]:
    """Extract OME metadata, parse channel names, and identify candidate panels."""
    input_dir = input_dir.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    rules_path = rules_path.expanduser().resolve()

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Extract raw OME metadata.
    channels, scan_records = extract_all_tiff_metadata(input_dir)

    channels_csv = write_csv(
        output_dir / "raw_ome_channels.csv",
        CHANNEL_COLUMNS,
        channels,
    )
    scan_csv = write_csv(
        output_dir / "tiff_metadata_scan.csv",
        SCAN_COLUMNS,
        scan_records,
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

    return {
        "channels_csv": channels_csv,
        "scan_csv": scan_csv,
        "parsed_channels_csv": parsed_csv,
        "panel_count": len(panel_groups),
        "manifest_count": len(manifest_paths),
        "parsed_channel_count": sum(
            channel["parse_status"] == "parsed"
            for channel in parsed_channels
        ),
        "channels_needing_review": sum(
            channel["parse_status"] == "needs_review"
            for channel in parsed_channels
        ),
    }
