#!/usr/bin/env python3
"""Scan an inbound directory of batch files and build a batch index.

Usage: python3 -I build_index.py [inbound_dir] [output_dir]

Each batch file is named <WH>_<YYYYMMDD>_<HHMM>.csv and starts with three
header lines (#BID / #WH / #RECV) written by the inbound system, followed by
one line per item: sku,qty,note.

The header is the system of record (written at receive time); the file name
is only a delivery label (it can carry a pre-move warehouse code, a hand-
edited wrong date, or the time of a redelivery). Therefore all index values
come from the header, and the name check compares each file-name segment
against the corresponding header field.

Outputs (written to output_dir, full rebuild on every run):
  index.csv      batch_id,wh_code,recv_time,item_rows,qty_total (one row per batch)
  name_check.csv file_name,batch_id,wh_code,recv_time (files whose name disagrees with the header)
  summary.txt    scanned_files / indexed_batches / mismatched_batches
"""

import csv
import re
import sys
from decimal import Decimal
from pathlib import Path

NAME_RE = re.compile(r"^([A-Za-z0-9]+)_(\d{8})_(\d{4})\.csv$")


def parse_batch(path):
    """Return (batch_id, wh_code, recv_time, item_rows, qty_total) from the header and detail lines."""
    with path.open(newline="", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    header = {}
    detail = []
    for line in lines:
        if line.startswith("#"):
            tag, _, value = line[1:].partition(",")
            header[tag.strip()] = value.strip()
        else:
            detail.append(line)

    qty_total = Decimal(0)
    for line in detail:
        qty_total += Decimal(line.split(",")[1].strip())

    # Quantities are whole units or weighed to at most 3 decimals.
    qty_str = format(qty_total.quantize(Decimal("0.001")).normalize(), "f")
    return (
        header["BID"],
        header["WH"],
        header["RECV"],
        len(detail),
        qty_str,
    )


def main():
    inbound_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "inbound")
    output_dir = Path(sys.argv[2] if len(sys.argv) > 2 else ".")

    batches = {}  # batch_id -> index row (first delivery wins; redeliveries are identical)
    mismatches = []  # (file_name, batch_id, wh_code, recv_time) from the header
    scanned = 0

    for path in sorted(inbound_dir.glob("*.csv")):
        match = NAME_RE.match(path.name)
        if not match:
            continue
        scanned += 1
        batch_id, wh_code, recv_time, item_rows, qty_str = parse_batch(path)

        if batch_id not in batches:
            batches[batch_id] = (batch_id, wh_code, recv_time, item_rows, qty_str)

        name_wh, name_date, name_time = match.groups()
        recv_date = recv_time[:10].replace("-", "")  # YYYY-MM-DD -> YYYYMMDD
        recv_hhmm = recv_time[11:16].replace(":", "")  # HH:MM:SS -> HHMM
        if (name_wh, name_date, name_time) != (wh_code, recv_date, recv_hhmm):
            mismatches.append((path.name, batch_id, wh_code, recv_time))

    with (output_dir / "index.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["batch_id", "wh_code", "recv_time", "item_rows", "qty_total"])
        for row in sorted(batches.values()):
            writer.writerow(row)

    with (output_dir / "name_check.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "batch_id", "wh_code", "recv_time"])
        writer.writerows(mismatches)

    with (output_dir / "summary.txt").open("w", encoding="utf-8") as f:
        f.write(f"scanned_files {scanned}\n")
        f.write(f"indexed_batches {len(batches)}\n")
        f.write(f"mismatched_batches {len(mismatches)}\n")


if __name__ == "__main__":
    main()
