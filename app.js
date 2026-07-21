document.addEventListener("DOMContentLoaded", () => {
    const runSelect = document.getElementById("runSelect");
    const timelineContainer = document.getElementById("timelineContainer");
    const loading = document.getElementById("loading");
    const viewerContainer = document.getElementById("viewerContainer");
    
    const activePlotImg = document.getElementById("activePlotImg");
    const plotTitle = document.getElementById("plotTitle");
    const plotBody = document.getElementById("plotBody");
    
    const categoryBtns = document.querySelectorAll(".category-btn");
    
    const modal = document.getElementById("imageModal");
    const modalImg = document.getElementById("modalImg");
    const modalCaption = document.getElementById("modalCaption");
    const closeModal = document.querySelector(".close-modal");

    let globalData = null;
    let currentCategory = "12hr"; // Default tab
    let currentIndex = 0;

    fetch("output/manifest.json")
        .then(response => {
            if (!response.ok) throw new Error("Manifest not found");
            return response.json();
        })
        .then(data => {
            globalData = data;
            loading.style.display = "none";
            viewerContainer.style.display = "block";
            
            if (!data.runs || data.runs.length === 0) {
                viewerContainer.innerHTML = "<p style='text-align:center; color: var(--text-secondary);'>No forecast runs available.</p>";
                return;
            }

            // Populate run dropdown
            data.runs.forEach(run => {
                const option = document.createElement("option");
                option.value = run.name;
                option.textContent = formatRunName(run.name);
                runSelect.appendChild(option);
            });

            updateView();

            // Event Listeners
            runSelect.addEventListener("change", () => {
                currentIndex = 0;
                updateView();
            });

            categoryBtns.forEach(btn => {
                btn.addEventListener("click", (e) => {
                    categoryBtns.forEach(b => b.classList.remove("active"));
                    e.target.classList.add("active");
                    currentCategory = e.target.getAttribute("data-category");
                    currentIndex = 0;
                    updateView();
                });
            });

            plotBody.addEventListener("click", () => {
                const activePlots = getActivePlots();
                if (activePlots.length > 0 && activePlots[currentIndex]) {
                    const plot = activePlots[currentIndex];
                    modal.style.display = "block";
                    modalImg.src = `output/${plot.path}`;
                    modalCaption.textContent = `${formatRunName(runSelect.value)} — ${formatPlotTitle(plot.name)}`;
                }
            });

            // Keyboard arrow support (Left / Right keys to step through timeline)
            document.addEventListener("keydown", (e) => {
                const activePlots = getActivePlots();
                if (activePlots.length === 0) return;

                if (e.key === "ArrowLeft") {
                    currentIndex = (currentIndex - 1 + activePlots.length) % activePlots.length;
                    updateActivePlot();
                } else if (e.key === "ArrowRight") {
                    currentIndex = (currentIndex + 1) % activePlots.length;
                    updateActivePlot();
                }
            });
        })
        .catch(error => {
            loading.textContent = "Failed to load forecast data. Please check back later.";
            console.error("Error loading manifest:", error);
        });

    function getActivePlots() {
        const runObj = globalData.runs.find(r => r.name === runSelect.value);
        if (!runObj || !runObj.plots) return [];
        return runObj.plots.filter(p => p.name.toLowerCase().includes(currentCategory));
    }

    function updateView() {
        const activePlots = getActivePlots();
        timelineContainer.innerHTML = "";

        if (activePlots.length === 0) {
            plotTitle.textContent = "No plots available for this category";
            activePlotImg.src = "";
            return;
        }

        if (currentIndex >= activePlots.length) {
            currentIndex = 0;
        }

        // Build timeline steps
        activePlots.forEach((plot, index) => {
            const step = document.createElement("div");
            step.className = `timeline-step ${index === currentIndex ? "active" : ""}`;
            step.textContent = formatStepLabel(plot.name);
            step.addEventListener("click", () => {
                currentIndex = index;
                updateActivePlot();
            });
            timelineContainer.appendChild(step);
        });

        updateActivePlot();
    }

    function updateActivePlot() {
        const activePlots = getActivePlots();
        if (activePlots.length === 0) return;

        // Highlight correct timeline step
        const steps = timelineContainer.querySelectorAll(".timeline-step");
        steps.forEach((step, idx) => {
            if (idx === currentIndex) {
                step.classList.add("active");
                step.scrollIntoView({ behavior: "smooth", inline: "nearest", block: "nearest" });
            } else {
                step.classList.remove("active");
            }
        });

        const plot = activePlots[currentIndex];
        activePlotImg.src = `output/${plot.path}`;
        plotTitle.textContent = formatPlotTitle(plot.name);
    }

    function formatRunName(name) {
        const parts = name.split("_");
        if (parts.length === 2) {
            const date = parts[0];
            const cycle = parts[1];
            return `${date.substring(0, 4)}-${date.substring(4, 6)}-${date.substring(6, 8)} @ ${cycle}Z Run`;
        }
        return name;
    }

    function formatStepLabel(plotName) {
        const clean = plotName.replace("plot_", "").toUpperCase();
        if (clean.includes("12HR_")) {
            return `Hours ${clean.replace("12HR_", "").replace("-", "–")}`;
        } else if (clean.includes("24HR_")) {
            return `Hours ${clean.replace("24HR_", "").replace("-", "–")}`;
        }
        return clean;
    }

    function formatPlotTitle(plotName) {
        const clean = plotName.replace("plot_", "").replace(".png", "").toUpperCase();
        if (clean.startsWith("12HR_")) {
            return `12-Hour QPF Accumulation (Forecast Hours ${clean.replace("12HR_", "").replace("-", " to ")})`;
        } else if (clean.startsWith("24HR_")) {
            return `24-Hour QPF Accumulation (Forecast Hours ${clean.replace("24HR_", "").replace("-", " to ")})`;
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
