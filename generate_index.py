import os
import json

# Compile manifest for static frontend viewer
runs = sorted(
    [
        d
        for d in os.listdir("output")
        if os.path.isdir(os.path.join("output", d))
    ],
    reverse=True,
)
manifest = {"runs": []}

for run in runs:
  run_path = os.path.join("output", run)
  plots = sorted(
      [
          f
          for f in os.listdir(run_path)
          if f.endswith(".png") and f.startswith("plot_")
      ]
  )
  run_plots = [
      {"name": plot.replace(".png", ""), "path": f"{run}/{plot}"}
      for plot in plots
  ]
  manifest["runs"].append({"name": run, "plots": run_plots})

with open(os.path.join("output", "manifest.json"), "w") as f:
  json.dump(manifest, f, indent=2)

print("Manifest JSON successfully updated.")
