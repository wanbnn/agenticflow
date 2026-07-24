(() => {
  const modal = document.querySelector("#workflow-modal");
  const form = document.querySelector("#workflow-form");
  const openModal = () => {
    modal.classList.remove("hidden");
    setTimeout(() => document.querySelector("#new-workflow-name").focus(), 50);
  };
  const closeModal = () => modal.classList.add("hidden");

  document.querySelector("#new-workflow-button")?.addEventListener("click", openModal);
  document.querySelector("#new-workflow-card")?.addEventListener("click", openModal);
  document.querySelector("#modal-close")?.addEventListener("click", closeModal);
  modal?.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = document.querySelector("#workflow-error");
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    errorBox.classList.add("hidden");
    try {
      const response = await fetch("/api/workflows", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: document.querySelector("#new-workflow-name").value,
          description: document.querySelector("#new-workflow-description").value,
          nodes: [],
          edges: [],
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Não foi possível criar o workflow.");
      window.location.assign(`/workflows/${data.id}`);
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("hidden");
    } finally {
      button.disabled = false;
    }
  });

  document.querySelector("#logout-button")?.addEventListener("click", async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  });
})();
