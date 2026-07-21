document.addEventListener("DOMContentLoaded", () => {
    const runSelect = document.getElementById("runSelect");
    const plotGrid = document.getElementById("plotGrid");
    const loading = document.getElementById("loading");
    
    const modal = document.getElementById("imageModal");
    const modalImg = document.getElementById("modalImg");
    const modalCaption = document.getElementById("modalCaption");
    const closeModal = document.querySelector(".close-modal");

    let globalData = null;

    fetch("output/manifest.json")
        .then(response => {
            if (!response.ok) throw new Error("Manifest not found");
            return response.json();
        })
        .then(data => {
            globalData = data;
            loading.style.display = "none";
            
            if (!data.runs || data.runs.length === 0) {
                plotGrid.innerHTML = "<p style='text-align:center; color: var(--text-secondary);'>No forecast runs available.</p>";
                return;
            }

            data.runs.forEach(run => {
                const option = document.createElement("option");
                option.value = run.name;
                option.textContent = formatRunName(run.name);
                runSelect.appendChild(option);
            });

            renderPlots(data.runs[0].name);

            runSelect.addEventListener("change", (e) => {
                renderPlots(e.target.value);
            });
        })
        .catch(error => {
            loading.textContent = "Failed to load forecast data. Please check back later.";
            console.error("Error loading manifest:", error);
        });

    function formatRunName(name) {
        const parts = name.split("_");
        if (parts.length === 2) {
            const date = parts[0];
            const cycle = parts[1];
            return `${date.substring(0, 4)}-${date.substring(4, 6)}-${date.substring(6, 8)} @ ${cycle}Z Run`;
        }
        return name;
    }

    function renderPlots(runName) {
        plotGrid.innerHTML = "";
        const runObj = globalData.runs.find(r => r.name === runName);
        if (!runObj || !runObj.plots) return;

        runObj.plots.forEach(plot => {
            const card = document.createElement("div");
            card.className = "plot-card";

            const header = document.createElement("div");
            header.className = "plot-header";
            header.innerHTML = `<h3>${formatPlotTitle(plot.name)}</h3>`;

            const body = document.createElement("div");
            body.className = "plot-body";

            const imgPath = `output/${plot.path}`;
            const img = document.createElement("img");
            img.src = imgPath;
            img.alt = plot.name;
            img.loading = "lazy";

            body.appendChild(img);
            card.appendChild(header);
            card.appendChild(body);
            plotGrid.appendChild(card);

            body.addEventListener("click", () => {
                modal.style.display = "block";
                modalImg.src = imgPath;
                modalCaption.textContent = `${formatRunName(runName)} — ${formatPlotTitle(plot.name)}`;
            });
        });
    }

    function formatPlotTitle(plotName) {
        const clean = plotName.replace("plot_", "").replace(".png", "").toUpperCase();
        if (clean.startsWith("12HR_")) {
            return `12-Hour Accumulation (Hours ${clean.replace("12HR_", "")})`;
        } else if (clean.startsWith("24HR_")) {
            return `24-Hour Accumulation (Hours ${clean.replace("24HR_", "")})`;
        }
        return clean;
    }

    closeModal.addEventListener("click", () => {
        modal.style.display = "none";
    });

    window.addEventListener("click", (e) => {
        if (e.target === modal) {
            modal.style.display = "none";
        }
    });
});
