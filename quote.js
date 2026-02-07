/* ===============================
   QUOTE WIZARD LOGIC
   =============================== */

let currentStep = 1;

// scoring state
let baseScore = 0;
let featureScore = 0;
let timelineMultiplier = 1;

// cached elements
const steps = document.querySelectorAll(".step");
const progressBar = document.getElementById("progressBar");
const priceEl = document.getElementById("price");

/* ===============================
   CORE HELPERS
   =============================== */

function showStep(step) {
  steps.forEach(stepEl => stepEl.classList.remove("active"));
  const target = document.querySelector(`.step[data-step="${step}"]`);
  if (target) target.classList.add("active");
  updateProgress(step);
}

function updateProgress(step) {
  if (!progressBar) return;
  const percent = (step / steps.length) * 100;
  progressBar.style.width = percent + "%";
}

/* ===============================
   FEATURE CALCULATION
   =============================== */

function calculateFeatures() {
  featureScore = 0;
  const checked = document.querySelectorAll(
    '.step[data-step="3"] input[type="checkbox"]:checked'
  );
  checked.forEach(() => {
    featureScore += 0.5;
  });
}

/* ===============================
   FINAL PRICE CALCULATION
   =============================== */

function calculatePrice() {
  calculateFeatures();

  const totalScore = (baseScore + featureScore) * timelineMultiplier;
  let range = "";

  if (totalScore <= 1.5) {
    range = "$500 – $700";
  } else if (totalScore <= 2.5) {
    range = "$700 – $1,100";
  } else if (totalScore <= 3.5) {
    range = "$1,100 – $1,600";
  } else {
    range = "Custom project — reviewed after discussion";
  }

  if (priceEl) {
    priceEl.textContent = range;
  }

  // save for contact page
  localStorage.setItem("quoteRange", range);
}

/* ===============================
   CLICK HANDLING
   =============================== */

document.addEventListener("click", e => {
  // NEXT buttons
  if (e.target.classList.contains("next-btn")) {
    currentStep++;
    showStep(currentStep);
  }

  // STEP 2 — site type
  if (e.target.dataset.type) {
    switch (e.target.dataset.type) {
      case "one":
        baseScore = 1;
        break;
      case "multi":
      case "redesign":
        baseScore = 2;
        break;
      case "unsure":
        baseScore = 1.5;
        break;
    }
    currentStep++;
    showStep(currentStep);
  }

  // STEP 4 — timeline
  if (e.target.dataset.time) {
    switch (e.target.dataset.time) {
      case "asap":
        timelineMultiplier = 1.3;
        break;
      case "month":
        timelineMultiplier = 1.1;
        break;
      case "flexible":
        timelineMultiplier = 1.0;
        break;
    }
    currentStep++;
    showStep(currentStep);
  }

  // STEP 5 — ongoing support
  if (e.target.dataset.support) {
    calculatePrice();
    currentStep++;
    showStep(currentStep);
  }
});

/* ===============================
   INIT
   =============================== */

showStep(currentStep);