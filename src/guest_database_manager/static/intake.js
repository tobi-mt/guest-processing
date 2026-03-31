const steps = Array.from(document.querySelectorAll(".form-step"));
const indicators = Array.from(document.querySelectorAll("[data-step-indicator]"));
const form = document.getElementById("intake-form");
const nextButton = document.getElementById("next-button");
const backButton = document.getElementById("back-button");
const submitButton = document.getElementById("submit-button");
const stepCounter = document.getElementById("step-counter");
const message = document.getElementById("intake-message");
const progressFill = document.getElementById("progress-fill");
const progressCaption = document.getElementById("progress-caption");
const successPanel = document.getElementById("success-panel");

const stepNames = ["Contact", "Journey", "Perspective", "Conversation"];

let currentStep = 0;

function notifyParentHeight() {
  if (window.parent === window) {
    return;
  }

  const height = Math.ceil(document.documentElement.scrollHeight);
  window.parent.postMessage(
    {
      type: "mirror-talk-intake-height",
      height,
    },
    "*",
  );
}

function syncStepUI() {
  steps.forEach((step, index) => {
    step.classList.toggle("active", index === currentStep);
  });

  indicators.forEach((indicator, index) => {
    indicator.classList.toggle("active", index === currentStep);
  });

  backButton.disabled = currentStep === 0;
  nextButton.classList.toggle("hidden", currentStep === steps.length - 1);
  submitButton.classList.toggle("hidden", currentStep !== steps.length - 1);
  stepCounter.textContent = `Step ${currentStep + 1} of ${steps.length}`;
  progressFill.style.width = `${((currentStep + 1) / steps.length) * 100}%`;
  progressCaption.textContent = `Currently on ${stepNames[currentStep]}`;
  window.requestAnimationFrame(notifyParentHeight);
}

function validateCurrentStep() {
  const activeStep = steps[currentStep];
  const requiredFields = activeStep.querySelectorAll("[required]");

  for (const field of requiredFields) {
    if (!field.value.trim()) {
      field.reportValidity();
      return false;
    }
  }

  return true;
}

function setMessage(text, tone = "") {
  message.textContent = text;
  message.className = `intake-message ${tone}`.trim();
}

function showSuccessState() {
  form.classList.add("hidden");
  successPanel.classList.remove("hidden");
}

function hideSuccessState() {
  form.classList.remove("hidden");
  successPanel.classList.add("hidden");
}

nextButton.addEventListener("click", () => {
  if (!validateCurrentStep()) {
    return;
  }

  currentStep += 1;
  syncStepUI();
});

backButton.addEventListener("click", () => {
  currentStep = Math.max(0, currentStep - 1);
  syncStepUI();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!validateCurrentStep()) {
    return;
  }

  const payload = Object.fromEntries(new FormData(form).entries());
  submitButton.disabled = true;
  submitButton.textContent = "Submitting...";
  setMessage("Submitting your application...", "pending");

  try {
    const response = await fetch("/api/intake", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Unable to submit your application.");
    }

    form.reset();
    currentStep = 0;
    syncStepUI();
    showSuccessState();
    setMessage(data.message || "Your application was submitted successfully.", "success");
    window.requestAnimationFrame(notifyParentHeight);
  } catch (error) {
    hideSuccessState();
    setMessage(error.message, "error");
    window.requestAnimationFrame(notifyParentHeight);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Submit Application";
  }
});

window.addEventListener("load", notifyParentHeight);
window.addEventListener("resize", notifyParentHeight);

syncStepUI();
