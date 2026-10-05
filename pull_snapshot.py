"""pull public nyiso day-ahead and real-time prices and the load forecast, and save one fixed snapshot.

run once, on a machine that can reach mis.nyiso.com:

    pip install requests pandas tzdata
    python pull_snapshot.py

what it does
  1. downloads the monthly zip archives into data/raw/nyiso/  (skips files already there, so it can be rerun)
  2. normalizes them into data/snapshot/*.csv.gz             (one file per market, native columns kept)
  3. writes data/snapshot/manifest.json                       (sources, window, row counts, hashes)

the four files, all public, no account and no key
  damlbmp   day-ahead zonal price, hourly
  realtime  real-time zonal price, about every five minutes
  rtlbmp    the publisher's own time-weighted hourly real-time price, the reconciliation target
  isolf     the zonal load forecast, one file per issue day, six days ahead

the publisher's time is local clock time with no time zone column: the hourly files carry hour-beginning
labels, the five-minute file carries interval-end stamps, and the fall-back day repeats an hour. the snapshot
keeps the labels as published; thyra/feeds.py counts hours by position in the day.

options
  --start 2025-10-01 --end 2026-01-31   the window, inclusive (default covers the 25-hour day on 2025-11-02)
  --normalize-only                      skip downloads, rebuild the snapshot from data/raw
"""
import argparse
import hashlib
import io
import json
import os
import sys
import time
import zipfile
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "data", "raw")
SNAP = os.path.join(HERE, "data", "snapshot")
UA = {"User-Agent": "thyra-data-quality/0.1 (public market data snapshot; contact via github.com/blakecodex)"}

log_lines = []


def log(msg):
    line = f"{datetime.now().strftime('%H:%M:%S')}  {msg}"
    print(line, flush=True)
    log_lines.append(line)


def fetch(session, url, tries=3, pause=0.0, ok_404=True):
    """get one url with retries. returns bytes, or none when the file does not exist (404)."""
    for attempt in range(1, tries + 1):
        try:
            r = session.get(url, headers=UA, timeout=120)
            if r.status_code == 404 and ok_404:
                return None
            if r.status_code == 429:
                log(f"  rate limited, sleeping 30s: {url}")
                time.sleep(30)
                continue
            r.raise_for_status()
            if pause:
                time.sleep(pause)
            return r.content
        except requests.RequestException as e:
            log(f"  attempt {attempt} failed: {e}")
            time.sleep(5 * attempt)
    return b""


def save_raw(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


def have(path):
    return os.path.exists(path) and os.path.getsize(path) > 0


def months(start, end):
    d = date(start.year, start.month, 1)
    while d <= end:
        yield d
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def days(start, end):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ----------------------------------------------------------------------------- nyiso

def pull_nyiso(session, start, end, missing):
    """monthly zip archives of daily csv files."""
    for kind in ("damlbmp", "realtime", "rtlbmp", "isolf"):
        for m in months(start, end):
            name = f"{m:%Y%m}01{kind}_zone_csv.zip" if kind != "isolf" else f"{m:%Y%m}01isolf_csv.zip"
            url = f"https://mis.nyiso.com/public/csv/{kind}/{name}"
            path = os.path.join(RAW, "nyiso", name)
            if have(path):
                continue
            log(f"nyiso {kind} {m:%Y-%m}")
            content = fetch(session, url)
            if not content:
                missing.append(url)
                continue
            save_raw(path, content)


def normalize_nyiso(start, end):
    out = {}
    for kind, label in (("damlbmp", "nyiso_da_zone_hourly"), ("realtime", "nyiso_rt_zone_5min"),
                        ("rtlbmp", "nyiso_rt_zone_hourly_integrated"), ("isolf", "nyiso_load_forecast_zone_hourly")):
        frames = []
        folder = os.path.join(RAW, "nyiso")
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if kind not in name or not name.endswith(".zip"):
                continue
            with zipfile.ZipFile(os.path.join(folder, name)) as z:
                for member in sorted(z.namelist()):
                    if not member.lower().endswith(".csv"):
                        continue
                    day = member[:8]
                    try:
                        d = date(int(day[:4]), int(day[4:6]), int(day[6:8]))
                    except ValueError:
                        continue
                    if d < start or d > end:
                        continue
                    df = pd.read_csv(io.BytesIO(z.read(member)))
                    df.columns = [c.strip() for c in df.columns]
                    if kind == "isolf":
                        # wide by zone: one column per zone plus a system total; keep it wide, add the file day
                        df.insert(0, "file_day", d.isoformat())
                        frames.append(df)
                        continue
                    ren = {}
                    for c in df.columns:
                        lc = c.lower()
                        if lc.startswith("time stamp"):
                            ren[c] = "time_stamp"
                        elif lc.startswith("time zone"):
                            ren[c] = "time_zone"
                        elif lc == "name":
                            ren[c] = "zone"
                        elif lc == "ptid":
                            ren[c] = "ptid"
                        elif lc.startswith("lbmp"):
                            ren[c] = "lbmp"
                        elif "losses" in lc:
                            ren[c] = "losses"
                        elif "congestion" in lc:
                            ren[c] = "congestion"
                    df = df.rename(columns=ren)
                    keep = [c for c in ("time_stamp", "time_zone", "zone", "ptid", "lbmp", "losses", "congestion") if c in df.columns]
                    df = df[keep].copy()
                    df.insert(0, "file_day", d.isoformat())
                    frames.append(df)
        if frames:
            out[label] = pd.concat(frames, ignore_index=True)
    return out


# ----------------------------------------------------------------------------- snapshot

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_snapshot(tables, start, end, isos, missing):
    os.makedirs(SNAP, exist_ok=True)
    manifest = {
        "snapshot_written_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "isos": isos,
        "time_conventions": {
            "nyiso": "local clock time with no time zone column; hourly files carry hour-beginning labels, the five-minute file carries interval-end stamps; the fall-back day repeats an hour and is counted by position; isolf is wide by zone, each file holds the forecasts issued that day for six days ahead",
        },
        "sources": {
            "nyiso": "https://mis.nyiso.com/public/csv/{damlbmp|realtime|rtlbmp}/{YYYYMM}01{kind}_zone_csv.zip and /isolf/{YYYYMM}01isolf_csv.zip",
        },
        "files": {},
        "raw_files": {},
        "missing": missing,
    }
    for iso in isos:
        folder = os.path.join(RAW, iso)
        if os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                path = os.path.join(folder, name)
                manifest["raw_files"][f"{iso}/{name}"] = {"bytes": os.path.getsize(path), "sha256": sha256(path)}
    for label, df in tables.items():
        path = os.path.join(SNAP, f"{label}.csv.gz")
        df.to_csv(path, index=False, compression="gzip")
        manifest["files"][f"{label}.csv.gz"] = {"rows": int(len(df)), "columns": list(df.columns), "sha256": sha256(path)}
        log(f"snapshot {label}: {len(df):,} rows")
    with open(os.path.join(SNAP, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(SNAP, "pull_log.txt"), "w") as f:
        f.write("\n".join(log_lines))
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2025-10-01")
    ap.add_argument("--end", default="2026-01-31")
    ap.add_argument("--normalize-only", action="store_true")
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    isos = ["nyiso"]
    missing = []
    t0 = time.time()
    log(f"window {start} to {end}; raw -> {RAW}")

    if not args.normalize_only:
        with requests.Session() as session:
            try:
                pull_nyiso(session, start, end, missing)
            except KeyboardInterrupt:
                raise
            except Exception as e:  # a failed pull leaves the raw files it got; rerun to resume
                log(f"nyiso: pull stopped with an error: {e!r}")

    tables = {}
    try:
        tables.update(normalize_nyiso(start, end))
    except Exception as e:
        log(f"nyiso: normalize stopped with an error: {e!r} (raw files are kept; rerun with --normalize-only after a fix)")

    manifest = write_snapshot(tables, start, end, isos, missing)
    log(f"done in {(time.time() - t0) / 60:.1f} minutes; {len(manifest['files'])} snapshot files; {len(missing)} missing raw files")
    if missing:
        log("missing (first 10): " + "; ".join(missing[:10]))


if __name__ == "__main__":
    main()
