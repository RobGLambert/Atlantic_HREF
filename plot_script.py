#!/usr/bin/env python3
"""
HREF LPMM QPF plots over the Maritimes with ECCC forecast zones overlaid.

Design:
  * Find the latest HREF run that is actually complete on NOMADS (no guessing a lag).
  * Download each forecast hour ONCE, validate it, retry on failure, cache it on disk.
  * Build every accumulation window by summing cached hourly arrays.
  * Skip (and say so) any window with a missing hour instead of plotting a partial sum.

Usage:
    python href_qpf_plots.py                 # latest complete run
    python href_qpf_plots.py --run 2026111606  # a specific run (YYYYMMDDHH)
"""
from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta, timezone

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import cfgrib
import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import requests

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
BASE_URL = "https://nomads.ncep.noaa.gov/pub/data/nccf/com/refs/prod"
OUTPUT_ROOT = "output"
CACHE_ROOT = "cache"

# Each window is (span_hours, last_forecast_hour).
# A 12 h window ending at f24 sums the hourly accumulations ending at f13..f24.
WINDOWS = [
    (12, 12), (12, 24), (12, 36), (12, 48), (12, 60),
    (24, 24), (24, 36), (24, 48), (24, 60),
    (48, 48), (48, 60),
]
MAX_FHOUR = max(end for _, end in WINDOWS)

RETRIES = 3
REQUEST_PAUSE_S = 0.5          # politeness delay between successful downloads
RUN_LOOKBACK_CYCLES = 6        # how many 6-hourly cycles to search back for a complete run

ZONES_BBOX = "-71.0,41.0,-53.0,51.0"
ZONES_URL = (
    "https://api.weather.gc.ca/collections/public-standard-forecast-zones/items"
    f"?f=json&bbox={ZONES_BBOX}&limit=500"
)

MAP_EXTENT = [-73.0, -50.0, 41.0, 50.5]  # lon_min, lon_max, lat_min, lat_max

# SPC-style colour table (mm)
SPC_COLORS = [
    "#7fff00", "#32cd32", "#008000", "#104e8b", "#009acd", "#00e5ee",
    "#00f5ff", "#ab82ff", "#9400d3", "#551a8b", "#8b0000", "#ff0000",
    "#ff4500", "#ff8c00", "#ffd700", "#FFFF00", "#ffc0cb", "#000000",
]
BOUNDS = [0.2, 2, 5, 10, 15, 20, 25, 35, 45, 55, 65, 75, 90, 100, 125, 150, 200, 250, 300]

CMAP = mcolors.ListedColormap(SPC_COLORS)
CMAP.set_under("none")
CMAP.set_over("black")          # anything above 300 mm stays visible
NORM = mcolors.BoundaryNorm(BOUNDS, CMAP.N)


# --------------------------------------------------------------------------- #
# Run selection
# --------------------------------------------------------------------------- #
def idx_url_for(date_str: str, cycle: str, f: int) -> str:
    return (f"{BASE_URL}/refs.{date_str}/{cycle}/ensprod/"
            f"refs.t{cycle}z.lpmm.f{f:02d}.conus.grib2.idx")


def run_is_complete(session: requests.Session, date_str: str, cycle: str) -> bool:
    """A run is usable once the LAST forecast hour we need has been posted."""
    try:
        r = session.get(idx_url_for(date_str, cycle, MAX_FHOUR), timeout=30)
        return r.status_code == 200 and "APCP" in r.text
    except requests.RequestException:
        return False


def find_latest_run(session: requests.Session) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    latest_cycle = now.replace(hour=(now.hour // 6) * 6, minute=0, second=0, microsecond=0)
    for k in range(RUN_LOOKBACK_CYCLES):
        t = latest_cycle - timedelta(hours=6 * k)
        date_str, cycle = t.strftime("%Y%m%d"), f"{t.hour:02d}"
        print(f"Checking run {date_str} {cycle}z ...", end=" ")
        if run_is_complete(session, date_str, cycle):
            print("complete.")
            return date_str, cycle
        print("not ready.")
    raise RuntimeError("No complete HREF run found in the lookback window.")


# --------------------------------------------------------------------------- #
# Hourly data fetching (download once, validate, retry, cache)
# --------------------------------------------------------------------------- #
class HourlyQPF:
    """Fetches 1-hour APCP for one HREF run and caches each hour as a .npy file."""

    def __init__(self, session: requests.Session, date_str: str, cycle: str):
        self.session = session
        self.date_str = date_str
        self.cycle = cycle
        self.cache_dir = os.path.join(CACHE_ROOT, f"{date_str}_{cycle}")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._grid_path = os.path.join(self.cache_dir, "grid.npz")
        self.lats: np.ndarray | None = None
        self.lons: np.ndarray | None = None

    # -- grid ------------------------------------------------------------- #
    def grid(self) -> tuple[np.ndarray, np.ndarray]:
        if self.lats is None and os.path.exists(self._grid_path):
            g = np.load(self._grid_path)
            self.lats, self.lons = g["lats"], g["lons"]
        if self.lats is None:
            raise RuntimeError("Grid not available: no hour has been downloaded yet.")
        return self.lats, self.lons

    # -- public ----------------------------------------------------------- #
    def get(self, f: int) -> np.ndarray | None:
        """Return the 1-hour accumulation ending at forecast hour f, or None on failure."""
        cache_file = os.path.join(self.cache_dir, f"f{f:02d}.npy")
        if os.path.exists(cache_file):
            return np.load(cache_file)

        data = self._download(f)
        if data is not None:
            np.save(cache_file, data)
        return data

    # -- internals -------------------------------------------------------- #
    @staticmethod
    def _find_byte_range(idx_text: str, f: int) -> str | None:
        """Locate the APCP message for the hour ending at f and return an HTTP Range value."""
        target = f":{f - 1}-{f} hour acc fcst"
        lines = idx_text.strip().split("\n")
        for i, line in enumerate(lines):
            if "APCP" in line and target in line:
                start = line.split(":")[1]
                end = int(lines[i + 1].split(":")[1]) - 1 if i < len(lines) - 1 else ""
                return f"bytes={start}-{end}"
        return None

    def _download(self, f: int) -> np.ndarray | None:
        f_str = f"f{f:02d}"
        idx_url = idx_url_for(self.date_str, self.cycle, f)
        grib_url = idx_url[: -len(".idx")]
        tmp_file = os.path.join(self.cache_dir, f"tmp_{f_str}.grib2")

        for attempt in range(1, RETRIES + 1):
            try:
                idx = self.session.get(idx_url, timeout=30)
                if idx.status_code != 200:
                    raise RuntimeError(f"idx HTTP {idx.status_code}")

                byte_range = self._find_byte_range(idx.text, f)
                if byte_range is None:
                    # Not a transient problem, retrying won't help.
                    print(f"  {f_str}: no APCP '{f-1}-{f} hour acc fcst' entry in idx")
                    return None

                r = self.session.get(grib_url, headers={"Range": byte_range}, timeout=120)
                # 206 = server honoured the Range. A 200 would be the whole file.
                if r.status_code != 206 or not r.content.startswith(b"GRIB"):
                    raise RuntimeError(
                        f"grib HTTP {r.status_code}, body starts with {r.content[:20]!r}"
                    )

                with open(tmp_file, "wb") as fh:
                    fh.write(r.content)

                ds = cfgrib.open_datasets(tmp_file, backend_kwargs={"indexpath": ""})[0]
                var = list(ds.data_vars)[0]
                data = np.squeeze(ds[var].values).astype(np.float32)
                if data.ndim != 2:
                    raise RuntimeError(f"unexpected array shape {data.shape}")

                if self.lats is None:
                    self.lats = ds["latitude"].values
                    self.lons = ds["longitude"].values
                    np.savez(self._grid_path, lats=self.lats, lons=self.lons)
                ds.close()

                time.sleep(REQUEST_PAUSE_S)
                print(f"  {f_str}: ok")
                return data

            except Exception as exc:  # noqa: BLE001 - we want to retry on anything here
                print(f"  {f_str}: attempt {attempt}/{RETRIES} failed: {exc}")
                time.sleep(5 * attempt)
            finally:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)

        return None


# --------------------------------------------------------------------------- #
# Plotting
# --------------------------------------------------------------------------- #
def load_zones() -> gpd.GeoDataFrame | None:
    print("Fetching ECCC forecast zones...")
    try:
        gdf = gpd.read_file(ZONES_URL)
        print(f"  loaded {len(gdf)} zones")
        return gdf
    except Exception as exc:  # noqa: BLE001
        print(f"  warning: could not load zones: {exc}")
        return None


def make_plot(lons, lats, data, zones_gdf, span, first_f, end_f, cycle, out_path):
    proj = ccrs.LambertConformal(central_longitude=-63.0, central_latitude=45.0)
    fig, ax = plt.subplots(figsize=(13, 6.5), subplot_kw={"projection": proj})
    ax.set_extent(MAP_EXTENT, crs=ccrs.PlateCarree())

    ax.add_feature(cfeature.COASTLINE, linewidth=0.8)
    ax.add_feature(cfeature.BORDERS, linestyle=":", linewidth=0.5)

    mesh = ax.pcolormesh(
        lons, lats, data,
        transform=ccrs.PlateCarree(), cmap=CMAP, norm=NORM, shading="auto",
    )

    if zones_gdf is not None:
        zones_gdf.plot(
            ax=ax, transform=ccrs.PlateCarree(),
            facecolor="none", edgecolor="gray", linewidth=0.6,
        )

    cbar = plt.colorbar(mesh, orientation="horizontal", pad=0.02, ticks=BOUNDS, shrink=0.5)
    cbar.set_label(f"{span}-hr QPF Accumulation (mm)", fontsize=9)
    cbar.ax.set_xticklabels([str(b) for b in BOUNDS], fontsize=7)

    plt.title(
        f"HREF LPMM - {span}-Hour Total Precipitation & ECCC Zones "
        f"(Run: {cycle}z | f{first_f:02d}-f{end_f:02d})",
        fontsize=11,
    )
    fig.subplots_adjust(left=0.01, right=0.99, top=0.93, bottom=0.05)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def window_hours(span: int, end_f: int) -> range:
    """Forecast hours whose 1-hr accumulations make up the window (inclusive of end_f)."""
    return range(end_f - span + 1, end_f + 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", help="Specific run as YYYYMMDDHH (default: latest complete)")
    args = parser.parse_args()

    session = requests.Session()

    if args.run:
        date_str, cycle = args.run[:8], args.run[8:10]
    else:
        date_str, cycle = find_latest_run(session)
    print(f"Using model run: {date_str} {cycle}z")

    out_dir = os.path.join(OUTPUT_ROOT, f"{date_str}_{cycle}")
    os.makedirs(out_dir, exist_ok=True)

    # 1) Download every hour we need exactly once.
    qpf = HourlyQPF(session, date_str, cycle)
    needed = sorted({f for span, end in WINDOWS for f in window_hours(span, end)})
    print(f"\nFetching {len(needed)} hourly fields (cached ones are reused)...")
    missing = {f for f in needed if qpf.get(f) is None}
    if missing:
        print(f"\nMissing hours: {sorted(missing)}")

    if len(missing) == len(needed):
        raise SystemExit("No data could be downloaded, nothing to plot.")

    lats, lons = qpf.grid()
    zones_gdf = load_zones()

    # 2) Build and plot each window from the cache.
    for span, end_f in WINDOWS:
        hours = window_hours(span, end_f)
        first_f = hours[0]
        name = f"{span}hr_f{first_f:02d}-f{end_f:02d}"

        bad = [f for f in hours if f in missing]
        if bad:
            print(f"\nSkipping {name}: missing hours {bad}")
            continue

        print(f"\n--- {name} ---")
        total = np.sum([qpf.get(f) for f in hours], axis=0)
        out_path = os.path.join(out_dir, f"plot_{name}.png")
        make_plot(lons, lats, total, zones_gdf, span, first_f, end_f, cycle, out_path)
        print(f"Saved {out_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
