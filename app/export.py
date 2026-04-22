"""Export query results to CSV."""

import csv
import re
from datetime import datetime
from pathlib import Path


_EXPORTS_DIR = Path("exports")


def _sanitize_filename(text: str, max_len: int = 40) -> str:
    """Turn arbitrary text into a safe filename fragment."""
    text = re.sub(r"[^\w\s-]", "", text).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:max_len]


def export_rows_to_csv(
    columns: list[str],
    rows: list[dict[str, object]],
    label: str = "",
) -> str:
    """Write tabular query results to a timestamped CSV file."""
    if not columns:
        raise ValueError("No columns provided for export.")
    if not rows:
        raise ValueError("No query rows available to export.")

    _EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{_sanitize_filename(label)}" if label else ""
    filename = _EXPORTS_DIR / f"query_result_{timestamp}{suffix}.csv"

    with filename.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=columns,
            quoting=csv.QUOTE_ALL,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "")
                            for column in columns})

    return str(filename.resolve())
