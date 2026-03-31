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
const draftBanner = document.getElementById("draft-banner");
const websiteField = form.querySelector('input[name="website"]');

const stepNames = ["Contact", "Journey", "Perspective", "Conversation"];
const DRAFT_STORAGE_KEY = "mirror-talk-intake-draft-v1";

let currentStep = 0;

function supportsLocalStorage() {
  try {
    return typeof window.localStorage !== "undefined";
  } catch (error) {
    return false;
  }
}

function getDraftPayload() {
  if (!supportsLocalStorage()) {
    return null;
  }

  try {
    const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    return JSON.parse(raw);
  } catch (error) {
    return null;
  }
}

function saveDraft() {
  if (!supportsLocalStorage()) {
    return;
  }

  const formValues = Object.fromEntries(new FormData(form).entries());
  const payload = {
    step: currentStep,
    values: formValues,
    savedAt: new Date().toISOString(),
  };

  try {
    window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(payload));
  } catch (error) {
    return;
  }
}

function clearDraft() {
  if (!supportsLocalStorage()) {
    return;
  }

  try {
    window.localStorage.removeItem(DRAFT_STORAGE_KEY);
  } catch (error) {
    return;
  }
}

function restoreDraft() {
  const draft = getDraftPayload();
  if (!draft || !draft.values) {
    return;
  }

  for (const [name, value] of Object.entries(draft.values)) {
    const field = form.elements.namedItem(name);
    if (!field || typeof field.value === "undefined") {
      continue;
    }
    field.value = value;
  }

  if (Number.isInteger(draft.step) && draft.step >= 0 && draft.step < steps.length) {
    currentStep = draft.step;
  }

  if (draftBanner && draft.savedAt) {
    draftBanner.textContent = "We restored your saved progress in this browser, so you can continue where you left off.";
  }

  normalizeWebsiteValue(websiteField);
}

function normalizeWebsiteValue(field) {
  if (!field) {
    return;
  }

  const value = field.value.trim();
  if (value && !/^[a-z]+:\/\//i.test(value)) {
    field.value = `https://${value}`;
  }
}

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

function validateFields(fields) {
  for (const field of fields) {
    const trimmedValue = typeof field.value === "string" ? field.value.trim() : field.value;

    if (field.hasAttribute("required") && !trimmedValue) {
      field.reportValidity();
      return false;
    }

    if (trimmedValue && !field.checkValidity()) {
      field.reportValidity();
      return false;
    }
  }

  return true;
}

function validateCurrentStep() {
  const activeStep = steps[currentStep];
  const fields = activeStep.querySelectorAll("input, select, textarea");
  return validateFields(fields);
}

function validateEntireForm() {
  for (let index = 0; index < steps.length; index += 1) {
    const fields = steps[index].querySelectorAll("input, select, textarea");
    if (!validateFields(fields)) {
      currentStep = index;
      syncStepUI();
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
  normalizeWebsiteValue(websiteField);
  if (!validateCurrentStep()) {
    return;
  }

  currentStep += 1;
  saveDraft();
  syncStepUI();
});

backButton.addEventListener("click", () => {
  currentStep = Math.max(0, currentStep - 1);
  saveDraft();
  syncStepUI();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  normalizeWebsiteValue(websiteField);
  if (!validateEntireForm()) {
    setMessage("Please complete the highlighted field before submitting.", "error");
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
    clearDraft();
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

form.addEventListener("input", () => {
  saveDraft();
});

form.addEventListener("change", () => {
  saveDraft();
});

window.addEventListener("load", notifyParentHeight);
window.addEventListener("resize", notifyParentHeight);
websiteField?.addEventListener("blur", () => normalizeWebsiteValue(websiteField));

restoreDraft();
syncStepUI();
