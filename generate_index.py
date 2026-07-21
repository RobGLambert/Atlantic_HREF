import os

output_dir = "output"
runs = sorted(
    [
        d
        for d in os.listdir(output_dir)
        if os.path.isdir(os.path.join(output_dir, d))
    ],
    reverse=True,
)

html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Atlantic Canada HREF & ECCC Forecast Viewer</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f4f4f9; color: #333; }
        h1 { color: #003366; }
        .run-section { background: #fff; padding: 20px; margin-bottom: 25px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .plot-grid { display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; }
        .plot-card { flex: 1; min-width: 450px; max-width: 600px; background: #fafafa; padding: 12px; border: 1px solid #ddd; border-radius: 6px; text-align: center; }
        img { width: 100%; height: auto; border: 1px solid #ccc; border-radius: 4px; }
        h3 { margin-top: 0; color: #444; }
        a { color: #0066cc; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <h1>Atlantic Canada HREF Precipitation & ECCC Zones</h1>
    <p>Automated forecast viewer updated regularly via NOAA NOMADS & ECCC OGC API.</p>
"""

if not runs:
  html_content += "<p>No model runs available yet.</p>"

for run in runs:
  html_content += f'<div class="run-section"><h2>Model Run: {run}</h2><div class="plot-grid">'
  run_path = os.path.join(output_dir, run)
  plots = sorted(
      [
          f
          for f in os.listdir(run_path)
          if f.endswith(".png") and f.startswith("plot_")
      ]
  )

  for plot in plots:
    title = plot.replace("plot_", "").replace(".png", "").upper()
    html_content += f"""
        <div class="plot-card">
            <h3>{title}</h3>
            <a href="{run}/{plot}" target="_blank">
                <img src="{run}/{plot}" alt="{title}">
            </a>
            <p><a href="{run}/{plot}" target="_blank">View Full Size Image</a></p>
        </div>
        """
  html_content += "</div></div>"

html_content += """
</body>
</html>
"""

with open(os.path.join(output_dir, "index.html"), "w") as f:
  f.write(html_content)

print("Index HTML viewer generated successfully.")