document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("#sp-home-chat-form");
  const question = document.querySelector("#sp-home-question");
  const course = document.querySelector("#sp-home-course");
  const coursePath = document.querySelector("#home-course-path");
  const shortcuts = document.querySelectorAll("[data-home-mode]");
  const error = document.querySelector("#sp-home-error");
  const newChat = document.querySelector("#sp-new-chat");
  const pdfInput = document.querySelector("#sp-pdf-input");
  const uploadStatus = document.querySelector("#sp-upload-status");
  const uploadStatusText = document.querySelector("#sp-upload-status-text");

  if (form) {
    function updateCourseLinks() {
      const courseUrl = course.selectedOptions[0]?.dataset.courseUrl;
      if (!courseUrl) {
        return;
      }

      form.action = courseUrl;
      coursePath.href = courseUrl;
      for (const shortcut of shortcuts) {
        shortcut.href = courseUrl + "#" + shortcut.dataset.homeMode;
      }
    }

    course.disabled = false;
    course.addEventListener("change", updateCourseLinks);
    window.addEventListener("pageshow", updateCourseLinks);
    updateCourseLinks();

    form.addEventListener("submit", event => {
      if (!question.value.trim()) {
        event.preventDefault();
        error.textContent = "Écris une question pour commencer.";
        question.focus();
        return;
      }

      question.value = question.value.trim();
    });

    question.addEventListener("input", () => {
      error.textContent = "";
    });

    newChat.hidden = false;
    newChat.addEventListener("click", () => {
      question.value = "";
      error.textContent = "";
      question.focus();
    });
  }

  let isUploading = false;
  for (const link of document.querySelectorAll("[data-home-upload]")) {
    link.addEventListener("click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
        return;
      }

      event.preventDefault();
      if (!isUploading) {
        pdfInput.click();
      }
    });
  }

  pdfInput.addEventListener("change", async () => {
    const file = pdfInput.files?.[0];
    pdfInput.value = "";
    if (!file || isUploading) {
      return;
    }

    uploadStatus.hidden = false;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      uploadStatusText.textContent = "Sélectionne un fichier PDF.";
      return;
    }

    const body = new FormData();
    body.append("pdf", file);
    isUploading = true;
    uploadStatusText.textContent = "Envoi du PDF…";

    try {
      const response = await fetch("/api/upload", { method: "POST", body });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "Impossible d’importer ce PDF.");
      }

      uploadStatusText.textContent = "Analyse et création du cours…";
      window.location.assign("/upload?job_id=" + encodeURIComponent(result.job_id));
    } catch (uploadError) {
      uploadStatusText.textContent = uploadError.message || "Erreur pendant l’import.";
    } finally {
      isUploading = false;
    }
  });
});
