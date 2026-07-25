(() => {
  "use strict";

  const menu = document.querySelector("#workspace-menu");
  if (!menu) return;

  menu.querySelectorAll("[data-workspace-id]").forEach((option) => {
    option.addEventListener("click", async () => {
      if (option.classList.contains("active")) {
        menu.open = false;
        return;
      }
      option.classList.add("loading");
      const response = await fetch(`/api/auth/workspace/${option.dataset.workspaceId}`, {
        method: "POST",
      });
      if (response.ok) {
        window.location.reload();
        return;
      }
      option.classList.remove("loading");
    });
  });

  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
})();
