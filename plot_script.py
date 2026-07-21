from datetime import datetime, timedelta, timezone
import os
import cartopy.crs as ccrs
import cartopy.feature as cfg
import cfgrib
import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import requests

# Automatically determine the latest completed model run based on UTC time (lagged by ~3.5 hours)
target_time = datetime.now(timezone.utc) - timedelta(hours=3.5)
date_str = target_time.strftime("%Y%m%d")
hour = (target_time.hour // 6) * 6
cycle = f"{hour:02d}"

print(f"Targeting Model Run: {date_str} {cycle}z")

# Define all the 12-hr and 24-hr windows you want to generate plots for
windows_to_plot = [
    {"name": "12hr_01-12", "start": 1, "end": 12},
    {"name": "12hr_12-24", "start": 13, "end": 24},
    {"name": "12hr_24-36", "start": 25, "end": 36},
    {"name": "12hr_36-48", "start": 37, "end": 48},
    {"name": "24hr_01-24", "start": 1, "end": 24},
    {"name": "24hr_12-36", "start": 13, "end": 36},
    {"name": "24hr_24-48", "start": 25, "end": 48},
]

# Metric SPC-Style Colormap Configuration (up to 150mm)
spc_colors = [
    "#7fff00",
    "#32cd32",
    "#008000",
    "#104e8b",
    "#009acd",
    "#00e5ee",
    "#00f5ff",
    "#ab82ff",
    "#9400d3",
    "#551a8b",
    "#8b0000",
    "#ff0000",
    "#ff4500",
    "#ff8c00",
    "#ffd700",
    "#ffc0cb",
]
bounds = [0.2, 2, 5, 10, 15, 20, 25, 35, 45, 55, 65, 75, 90, 100, 125, 150]

cmap = mcolors.ListedColormap(spc_colors)
cmap.set_under("none")
norm = mcolors.BoundaryNorm(bounds, cmap.N)

# Fetch ECCC forecast zones ONCE to save time and API requests
print("Fetching ECCC forecast zones...")
bbox_str = "-71.0,41.0,-53.0,51.0"
geojson_url = f"https://api.weather.gc.ca/collections/public-standard-forecast-zones/items?f=json&bbox={bbox_str}&limit=500"
zones_gdf = None
try:
  zones_gdf = gpd.read_file(geojson_url)
  print(f"Successfully loaded {len(zones_gdf)} ECCC forecast zones.")
except Exception as e:
  print(f"Warning: Could not load ECCC forecast zones: {e}")

# Create a run-specific output directory
run_output_dir = os.path.join("output", f"{date_str}_{cycle}")
os.makedirs(run_output_dir, exist_ok=True)

# Loop through each defined window and generate a separate plot
for win in windows_to_plot:
  name = win["name"]
  start_f = win["start"]
  end_f = win["end"]
  hours_span = end_f - start_f + 1

  print(
      f"\n--- Processing Window: {name} (Hours {start_f} to {end_f}) ---"
  )

  accumulated_data = None
  lats, lons = None, None

  for f in range(start_f, end_f + 1):
    f_str = f"f{f:02d}"
    idx_url = f"https://nomads.ncep.noaa.gov/pub/data/nccf/com/href/prod/href.{date_str}/ensprod/href.t{cycle}z.conus.lpmm.{f_str}.grib2.idx"
    grib_url = idx_url.rsplit(".", 1)[0]
    target_query = f"{f-1}-{f} hour acc fcst"

    res = requests.get(idx_url)
    if res.status_code != 200:
      print(f"Skipping {f_str}: Index file not found.")
      continue

    lines = res.text.strip().split("\n")
    byte_range = None

    for i, line in enumerate(lines):
      parts = line.split(":")
      if "APCP" in line and target_query in line:
        start_byte = parts[1]
        if i < len(lines) - 1:
          end_byte = int(lines[i + 1].split(":")[1]) - 1
        else:
          end_byte = ""
        byte_range = f"bytes={start_byte}-{end_byte}"
        break

    if not byte_range:
      continue

    headers = {"Range": byte_range}
    grib_res = requests.get(grib_url, headers=headers)

    subset_filename = f"temp_{f_str}.grib2"
    with open(subset_filename, "wb") as file_obj:
      file_obj.write(grib_res.content)

    datasets = cfgrib.open_datasets(subset_filename)
    ds = datasets[0]
    var_name = list(ds.data_vars)[0]
    data = ds[var_name].values

    if lats is None:
      lats = ds["latitude"].values
      lons = ds["longitude"].values

    if accumulated_data is None:
      accumulated_data = np.zeros_like(data)

    accumulated_data += data
    os.remove(subset_filename)

  if accumulated_data is None:
    print(f"Skipping plot for {name}: No data collected.")
    continue

  plot_data = accumulated_data

  # Map Projection & Wide Layout Configuration
  proj = ccrs.LambertConformal(central_longitude=-63.0, central_latitude=45.0)
  fig, ax = plt.subplots(figsize=(13, 6.5), subplot_kw={"projection": proj})
  ax.set_extent([-73.0, -50.0, 41.0, 50.5], crs=ccrs.PlateCarree())

  ax.add_feature(cfg.COASTLINE, linewidth=0.8)
  ax.add_feature(cfg.BORDERS, linestyle=":", linewidth=0.5)

  # Plot Precipitation Mesh
  mesh = ax.pcolormesh(
      lons,
      lats,
      plot_data,
      transform=ccrs.PlateCarree(),
      cmap=cmap,
      norm=norm,
      shading="auto",
  )

  # Overlay ECCC Zones if successfully loaded
  if zones_gdf is not None:
    zones_gdf.plot(
        ax=ax,
        transform=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="gray",
        linewidth=0.6,
    )

  # Compact Legend formatting
  cbar = plt.colorbar(
      mesh, orientation="horizontal", pad=0.02, ticks=bounds, shrink=0.5
  )
  cbar.set_label(f"{hours_span}-hr QPF Accumulation (mm)", fontsize=9)
  cbar.ax.set_xticklabels([str(b) for b in bounds], fontsize=7)

  plt.title(
      f"HREF LPMM - {hours_span}-Hour Total Precipitation & ECCC Zones"
      f" (Run: {cycle}z | Window: {name})",
      fontsize=11,
  )

  fig.subplots_adjust(left=0.01, right=0.99, top=0.93, bottom=0.05)

  output_path = os.path.join(run_output_dir, f"plot_{name}.png")
  plt.savefig(output_path, dpi=150, bbox_inches="tight")
  plt.close()
  print(f"Successfully generated and saved: {output_path}")

print("\nAll requested plots generated successfully!")