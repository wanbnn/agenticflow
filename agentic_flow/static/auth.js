(() => {
  const form = document.querySelector("#auth-form");
  const errorBox = document.querySelector("#auth-error");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    errorBox.classList.add("hidden");
    const payload = Object.fromEntries(new FormData(form).entries());
    try {
      const response = await fetch(`/api/auth/${form.dataset.mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Não foi possível continuar.");
      window.location.assign("/dashboard");
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("hidden");
    } finally {
      button.disabled = false;
    }
  });
})();
