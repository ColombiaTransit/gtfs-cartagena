#!/usr/bin/env python3
"""
calendar.txt and calendar_dates.txt for the feed.

The schedule (raw/m2m/departure/) has three day types, which become the
service_ids:

    weekday   Monday to Friday
    saturday  Saturday
    sunday    Sunday and public holidays

Colombian public holidays (festivos, from the `holidays` package, including
the holidays moved to Monday by the Ley Emiliani) run the Sunday schedule, as
the API shows for 2026-11-02 and 2026-11-16 and Transcaribe announces. In
calendar_dates.txt a holiday on a weekday removes `weekday` and adds `sunday`;
on a Saturday it removes `saturday` and adds `sunday`.

The service_ids are fixed names, so trip_ids built on them stay the same when
the feed is rebuilt (needed to match GTFS-Realtime later).

Usage: python scripts/gtfs_calendar.py START END [OUTDIR]   (YYYY-MM-DD; default
       OUTDIR data/gtfs) - writes the two files, for a look before the full build.
"""

from __future__ import annotations

import csv
import sys
from datetime import date, timedelta
from pathlib import Path

import holidays

SERVICES = {          # service_id -> weekdays (Monday = 0) it runs on
    "weekday": {0, 1, 2, 3, 4},
    "saturday": {5},
    "sunday": {6},
}
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def festivos(start: date, end: date) -> dict[date, str]:
    co = holidays.Colombia(years=range(start.year, end.year + 1))
    return {d: name for d, name in sorted(co.items()) if start <= d <= end}


def service_of(day: date) -> str:
    return next(s for s, wd in SERVICES.items() if day.weekday() in wd)


def calendar_rows(start: date, end: date) -> list[dict]:
    rows = []
    for sid, wd in SERVICES.items():
        row = {"service_id": sid, **{d: int(i in wd) for i, d in enumerate(DAYS)},
               "start_date": start.strftime("%Y%m%d"), "end_date": end.strftime("%Y%m%d")}
        rows.append(row)
    return rows


def calendar_date_rows(start: date, end: date) -> list[dict]:
    rows = []
    for day, name in festivos(start, end).items():
        usual = service_of(day)
        if usual == "sunday":
            continue
        ymd = day.strftime("%Y%m%d")
        rows.append({"service_id": usual, "date": ymd, "exception_type": 2, "holiday": name})
        rows.append({"service_id": "sunday", "date": ymd, "exception_type": 1, "holiday": name})
    return rows


def write(start: date, end: date, outdir: Path) -> tuple[int, int]:
    outdir.mkdir(parents=True, exist_ok=True)
    cal = calendar_rows(start, end)
    with (outdir / "calendar.txt").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cal[0]))
        w.writeheader()
        w.writerows(cal)
    dates = calendar_date_rows(start, end)
    with (outdir / "calendar_dates.txt").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["service_id", "date", "exception_type"], extrasaction="ignore")
        w.writeheader()
        w.writerows(dates)
    return len(cal), len(dates)


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    start, end = date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2])
    if end < start or end - start > timedelta(days=366):
        sys.exit("END must be after START and within a year")
    outdir = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).resolve().parent.parent / "data" / "gtfs"
    for day, name in festivos(start, end).items():
        print(day, DAYS[day.weekday()][:3], service_of(day), "->", "sunday", name)
    n_cal, n_dates = write(start, end, outdir)
    print(f"calendar.txt: {n_cal} services, calendar_dates.txt: {n_dates} rows -> {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
