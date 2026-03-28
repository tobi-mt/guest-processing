document.addEventListener("DOMContentLoaded", () => {
  const forms = document.querySelectorAll("[data-mirror-talk-intake-form]");

  forms.forEach((form) => {
    const endpoint = form.dataset.endpoint;
    const steps = Array.from(form.querySelectorAll(".mirror-talk-intake-step"));
    const indicators = Array.from(form.querySelectorAll("[data-step-indicator]"));
    const backButton = form.querySelector("[data-action='back']");
    const nextButton = form.querySelector("[data-action='next']");
    const submitButton = form.querySelector("[data-action='submit']");
    const counter = form.querySelector("[data-step-counter]");
    const message = form.querySelector("[data-intake-message]");

    let currentStep = 0;

    const setMessage = (text, tone = "") => {
      if (!message) {
        return;
      }

      message.textContent = text;
      message.className = `mirror-talk-intake-message ${tone}`.trim();
    };

    const syncStepUI = () => {
      steps.forEach((step, index) => {
        step.classList.toggle("is-active", index === currentStep);
      });

      indicators.forEach((indicator, index) => {
        indicator.classList.toggle("is-active", index === currentStep);
      });

      if (counter) {
        counter.textContent = `Step ${currentStep + 1} of ${steps.length}`;
      }

      if (backButton) {
        backButton.disabled = currentStep === 0;
      }

      if (nextButton) {
        nextButton.hidden = currentStep === steps.length - 1;
      }

      if (submitButton) {
        submitButton.hidden = currentStep !== steps.length - 1;
      }
    };

    const validateCurrentStep = () => {
      const activeStep = steps[currentStep];
      const requiredFields = activeStep.querySelectorAll("[required]");

      for (const field of requiredFields) {
        if (!field.value.trim()) {
          field.reportValidity();
          return false;
        }
      }

      return true;
    };

    nextButton?.addEventListener("click", () => {
      if (!validateCurrentStep()) {
        return;
      }

      currentStep += 1;
      syncStepUI();
    });

    backButton?.addEventListener("click", () => {
      currentStep = Math.max(0, currentStep - 1);
      syncStepUI();
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      setMessage("");

      if (!validateCurrentStep()) {
        return;
      }

      if (!endpoint) {
        setMessage("The intake API endpoint has not been configured yet.", "is-error");
        return;
      }

      const payload = Object.fromEntries(new FormData(form).entries());

      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.error || "Unable to submit your application.");
        }

        form.reset();
        currentStep = 0;
        syncStepUI();
        setMessage(data.message || "Thank you. Your application has been submitted.", "is-success");
      } catch (error) {
        setMessage(error.message, "is-error");
      }
    });

    syncStepUI();
  });
});
