document.addEventListener("DOMContentLoaded", () => {
  const tabs = [
    ...document.querySelectorAll("[data-panel]")
  ];

  const views = [
    ...document.querySelectorAll("[data-view]")
  ];

  const input =
    document.querySelector("#sp-chat-question");


  function activatePanel(name) {
    for (const tab of tabs) {
      const active =
        tab.dataset.panel === name;

      tab.classList.toggle(
        "active",
        active
      );

      tab.setAttribute(
        "aria-selected",
        active ? "true" : "false"
      );
    }


    for (const view of views) {
      const active =
        view.dataset.view === name;

      view.classList.toggle(
        "active",
        active
      );

      view.hidden = !active;
    }


    if (
      name === "cards"
      &&
      window.MathJax?.typesetPromise
    ) {
      const cardView =
        document.querySelector(
          '[data-view="cards"]'
        );

      if (cardView) {
        window.MathJax
          .typesetPromise([cardView])
          .catch(() => {});
      }
    }
  }


  for (const tab of tabs) {
    tab.addEventListener(
      "click",
      () => {
        activatePanel(
          tab.dataset.panel
        );
      }
    );
  }


  for (
    const shortcut
    of document.querySelectorAll(
      "[data-prompt]"
    )
  ) {
    shortcut.addEventListener(
      "click",
      () => {
        if (!input) {
          return;
        }

        input.value =
          shortcut.dataset.prompt || "";

        input.focus();
      }
    );
  }

  for (
  const button
  of document.querySelectorAll(
    "[data-concepts-toggle]"
  )
) {

  button.addEventListener(
    "click",
    () => {

      const card =
        button.closest(
          ".sp-context-card"
        );


      const extras = [
        ...card.querySelectorAll(
          ".sp-concept-extra"
        )
      ];


      const opening =
        extras.some(
          item => item.hidden
        );


      for (const item of extras) {
        item.hidden = !opening;
      }


      button.textContent =
        opening
          ? "Réduire ↑"
          : `Voir ${button.dataset.total} notions ↓`;

    }
  );

}
});
