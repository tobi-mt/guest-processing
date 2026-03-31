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
const successTitle = document.getElementById("success-title");
const draftBanner = document.getElementById("draft-banner");
const websiteField = form.querySelector('input[name="website"]');
const conditionalGroups = Array.from(document.querySelectorAll("[data-conditional-source]"));
const socialPlatformFields = Array.from(document.querySelectorAll("[data-social-platform]"));
const socialOtherField = form.elements.namedItem("social_other");
const socialHandlesField = form.elements.namedItem("social_handles");

const stepNames = ["Contact", "Journey", "Perspective", "Conversation"];
const DRAFT_STORAGE_KEY = "mirror-talk-intake-draft-v1";
const DEFAULT_DRAFT_BANNER_TEXT = "Your progress is saved automatically in this browser, so you can come back later and continue where you left off.";

let currentStep = 0;
let isComplete = false;
let draftBannerResetTimer = null;

function buildConditionalAnswer(choiceName, detailName) {
  const choiceField = form.elements.namedItem(choiceName);
  const detailField = form.elements.namedItem(detailName);
  const choice = typeof choiceField?.value === "string" ? choiceField.value.trim() : "";
  const detail = typeof detailField?.value === "string" ? detailField.value.trim() : "";

  if (!choice) {
    return "";
  }

  if (choice === "Yes") {
    return detail ? `Yes — ${detail}` : "Yes";
  }

  return choice;
}

function buildSocialHandlesValue() {
  const entries = [];

  socialPlatformFields.forEach((field) => {
    const value = typeof field.value === "string" ? field.value.trim() : "";
    if (!value) {
      return;
    }
    entries.push(`${field.dataset.socialPlatform}: ${value}`);
  });

  const otherValue = typeof socialOtherField?.value === "string" ? socialOtherField.value.trim() : "";
  if (otherValue) {
    entries.push(otherValue);
  }

  return entries.join("\n");
}

function syncSocialHandlesField() {
  if (!socialHandlesField) {
    return;
  }

  socialHandlesField.value = buildSocialHandlesValue();
}

function hasStructuredSocialValue() {
  if (socialPlatformFields.some((field) => String(field.value || "").trim())) {
    return true;
  }
  return Boolean(String(socialOtherField?.value || "").trim());
}

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
    showDraftSavedState();
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

  if (!hasStructuredSocialValue() && socialHandlesField?.value) {
    socialOtherField.value = socialHandlesField.value;
  }

  normalizeWebsiteValue(websiteField);
  syncSocialHandlesField();
  updateConditionalGroups();
}

function setDraftBannerText(text, saved = false) {
  if (!draftBanner) {
    return;
  }

  draftBanner.textContent = text;
  draftBanner.classList.toggle("saved", saved);
}

function showDraftSavedState() {
  if (!draftBanner) {
    return;
  }

  setDraftBannerText("Draft saved in this browser.", true);
  if (draftBannerResetTimer) {
    window.clearTimeout(draftBannerResetTimer);
  }
  draftBannerResetTimer = window.setTimeout(() => {
    setDraftBannerText(DEFAULT_DRAFT_BANNER_TEXT, false);
  }, 1600);
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

function updateConditionalGroups() {
  conditionalGroups.forEach((group) => {
    const sourceName = group.dataset.conditionalSource;
    const expectedValue = group.dataset.conditionalValue || "Yes";
    const sourceField = form.elements.namedItem(sourceName);
    const shouldShow = Boolean(sourceField) && sourceField.value === expectedValue;
    group.classList.toggle("hidden", !shouldShow);
  });

  window.requestAnimationFrame(notifyParentHeight);
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
    indicator.classList.toggle("active", !isComplete && index === currentStep);
    indicator.classList.toggle("completed", isComplete || index < currentStep);
  });

  backButton.disabled = currentStep === 0;
  nextButton.classList.toggle("hidden", currentStep === steps.length - 1);
  submitButton.classList.toggle("hidden", currentStep !== steps.length - 1);
  if (isComplete) {
    stepCounter.textContent = "Finished";
    progressFill.style.width = "100%";
    progressCaption.textContent = "Application complete";
  } else {
    stepCounter.textContent = `Step ${currentStep + 1} of ${steps.length}`;
    progressFill.style.width = `${((currentStep + 1) / steps.length) * 100}%`;
    progressCaption.textContent = `Currently on ${stepNames[currentStep]}`;
  }
  window.requestAnimationFrame(notifyParentHeight);
}

function validateFields(fields) {
  for (const field of fields) {
    if (field.type === "hidden") {
      continue;
    }
    if (field.closest(".hidden")) {
      continue;
    }

    const trimmedValue = typeof field.value === "string" ? field.value.trim() : field.value;
    const conditionalRule = field.dataset.conditionalRequired;
    let isConditionallyRequired = false;

    if (conditionalRule) {
      const [sourceName, expectedValue] = conditionalRule.split(":");
      const sourceField = form.elements.namedItem(sourceName);
      isConditionallyRequired = Boolean(sourceField) && sourceField.value === expectedValue;
    }

    if ((field.hasAttribute("required") || isConditionallyRequired) && !trimmedValue) {
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
  syncSocialHandlesField();
  const fields = activeStep.querySelectorAll("input, select, textarea");
  if (!validateFields(fields)) {
    return false;
  }

  if (activeStep.contains(socialHandlesField)) {
    const hasWebsite = Boolean(String(websiteField?.value || "").trim());
    const hasSocial = Boolean(String(socialHandlesField.value || "").trim());

    if (!hasWebsite && !hasSocial) {
      setMessage("Please share at least a website or one social/public profile so we can verify and understand your public voice.", "error");
      const focusTarget = websiteField || socialPlatformFields[0] || socialOtherField;
      focusTarget?.classList.add("field-error");
      focusTarget?.focus({ preventScroll: true });
      focusTarget?.scrollIntoView({ behavior: "smooth", block: "center" });
      return false;
    }

    if (!hasWebsite || !hasSocial) {
      setMessage("You can submit with either a website or social presence. Sharing both simply helps us review your application more quickly.", "pending");
    }
  }

  return true;
}

function validateEntireForm() {
  for (let index = 0; index < steps.length; index += 1) {
    syncSocialHandlesField();
    const fields = steps[index].querySelectorAll("input, select, textarea");
    if (!validateFields(fields)) {
      currentStep = index;
      syncStepUI();
      return false;
    }

    if (steps[index].contains(socialHandlesField)) {
      const hasWebsite = Boolean(String(websiteField?.value || "").trim());
      const hasSocial = Boolean(String(socialHandlesField.value || "").trim());

      if (!hasWebsite && !hasSocial) {
        currentStep = index;
        syncStepUI();
        setMessage("Please share at least a website or one social/public profile so we can verify and understand your public voice.", "error");
        const focusTarget = websiteField || socialPlatformFields[0] || socialOtherField;
        focusTarget?.classList.add("field-error");
        focusTarget?.focus({ preventScroll: true });
        focusTarget?.scrollIntoView({ behavior: "smooth", block: "center" });
        return false;
      }

      if (!hasWebsite || !hasSocial) {
        setMessage("You can submit with either a website or social presence. Sharing both simply helps us review your application more quickly.", "pending");
      }
    }
  }

  return true;
}

function clearFieldHighlights() {
  form.querySelectorAll(".field-error").forEach((field) => {
    field.classList.remove("field-error");
  });
}

function focusFieldByName(fieldName) {
  const field = form.elements.namedItem(fieldName);
  if (!field || typeof field.focus !== "function") {
    return false;
  }

  const step = field.closest(".form-step");
  if (step) {
    const stepIndex = steps.indexOf(step);
    if (stepIndex >= 0) {
      currentStep = stepIndex;
      syncStepUI();
    }
  }

  field.classList.add("field-error");
  field.focus({ preventScroll: true });
  field.scrollIntoView({ behavior: "smooth", block: "center" });
  return true;
}

function revealServerValidationTarget(errorMessage) {
  const match = errorMessage.match(/Please provide a more complete answer for:\s*(.+)$/i);
  if (!match) {
    return false;
  }

  const normalizedFieldName = match[1].trim().toLowerCase().replace(/\s+/g, "_");
  return focusFieldByName(normalizedFieldName);
}

function setMessage(text, tone = "") {
  message.textContent = text;
  message.className = `intake-message ${tone}`.trim();
}

function showSuccessState() {
  form.classList.add("hidden");
  successPanel.classList.remove("hidden");
  isComplete = true;
  syncStepUI();
}

function hideSuccessState() {
  form.classList.remove("hidden");
  successPanel.classList.add("hidden");
  isComplete = false;
}

nextButton.addEventListener("click", () => {
  clearFieldHighlights();
  isComplete = false;
  normalizeWebsiteValue(websiteField);
  syncSocialHandlesField();
  updateConditionalGroups();
  if (!validateCurrentStep()) {
    return;
  }

  currentStep += 1;
  saveDraft();
  syncStepUI();
});

backButton.addEventListener("click", () => {
  clearFieldHighlights();
  isComplete = false;
  currentStep = Math.max(0, currentStep - 1);
  saveDraft();
  syncStepUI();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearFieldHighlights();
  normalizeWebsiteValue(websiteField);
  syncSocialHandlesField();
  updateConditionalGroups();
  if (!validateEntireForm()) {
    setMessage("Please complete the highlighted field before submitting.", "error");
    return;
  }

  const payload = Object.fromEntries(new FormData(form).entries());
  payload.faith = buildConditionalAnswer("faith_choice", "faith_detail");
  payload.alignment = buildConditionalAnswer("alignment_choice", "alignment_detail");
  payload.favorite_quote = buildConditionalAnswer("favorite_quote_choice", "favorite_quote_detail");
  payload.experience = buildConditionalAnswer("experience_choice", "experience_detail");
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

    const fullName = (payload.full_name || "").trim();
    form.reset();
    clearDraft();
    currentStep = steps.length - 1;
    setDraftBannerText(DEFAULT_DRAFT_BANNER_TEXT, false);
    if (successTitle) {
      successTitle.textContent = fullName
        ? `Thank you, ${fullName}, for sharing your story.`
        : "Thank you for sharing your story.";
    }
    showSuccessState();
    setMessage(data.message || "Your application was submitted successfully.", "success");
    window.requestAnimationFrame(notifyParentHeight);
  } catch (error) {
    hideSuccessState();
    revealServerValidationTarget(error.message);
    setMessage(error.message, "error");
    window.requestAnimationFrame(notifyParentHeight);
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Submit Application";
  }
});

form.addEventListener("input", () => {
  clearFieldHighlights();
  syncSocialHandlesField();
  updateConditionalGroups();
  saveDraft();
});

form.addEventListener("change", () => {
  clearFieldHighlights();
  syncSocialHandlesField();
  updateConditionalGroups();
  saveDraft();
});

window.addEventListener("load", notifyParentHeight);
window.addEventListener("resize", notifyParentHeight);
websiteField?.addEventListener("blur", () => normalizeWebsiteValue(websiteField));

restoreDraft();
updateConditionalGroups();
syncStepUI();
