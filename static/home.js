document.addEventListener(
  "DOMContentLoaded",
  () => {

    const form =
      document.querySelector(
        "#sp-home-chat-form"
      );

    const question =
      document.querySelector(
        "#sp-home-question"
      );

    const course =
      document.querySelector(
        "#sp-home-course"
      );

    const error =
      document.querySelector(
        "#sp-home-error"
      );

    const pdfInput =
      document.querySelector(
        "#sp-pdf-input"
      );

    const uploadStatus =
      document.querySelector(
        "#sp-upload-status"
      );

    const uploadStatusText =
      document.querySelector(
        "#sp-upload-status-text"
      );


    /*
     * Chat d'accueil réel :
     *
     * on choisit le cours,
     * puis on entre directement
     * dans son workspace avec la question.
     */
    if (form) {

      form.addEventListener(
        "submit",
        event => {

          event.preventDefault();


          const text =
            question.value.trim();

          const courseId =
            course.value;


          if (!text) {
            return;
          }


          if (!courseId) {

            error.textContent =
              "Choisis d'abord un cours.";

            return;
          }


          const params =
            new URLSearchParams({
              q: text,
            });


          window.location.href =
            `/course/${encodeURIComponent(
              courseId
            )}?${params.toString()}`;

        }
      );

    }



    document.querySelectorAll('[data-home-mode]').forEach(button=>button.addEventListener('click',()=>{
      const id=course?.value;
      if(!id){error.textContent="Choisis d’abord un cours.";return;}
      window.location.href='/course/'+encodeURIComponent(id)+'#'+button.dataset.homeMode;
    }));

    /*
     * Nouvelle discussion.
     */
    document
      .querySelector("#sp-new-chat")
      ?.addEventListener(
        "click",
        () => {

          if (!question) {
            return;
          }


          question.value = "";

          question.focus();

        }
      );



    /*
     * Ouverture du sélecteur PDF.
     */
    const uploadButtons = [
      "#sp-upload-trigger",
      "#sp-upload-trigger-small",
      "#sp-home-upload-button",
      "#sp-empty-upload",
    ];


    for (const selector of uploadButtons) {

      document
        .querySelector(selector)
        ?.addEventListener(
          "click",
          () => {
            pdfInput?.click();
          }
        );

    }



    /*
     * Upload réel via l'API StudyPilot existante.
     */
    pdfInput?.addEventListener(
      "change",
      async () => {

        const file =
          pdfInput.files?.[0];


        if (!file) {
          return;
        }


        if (
          file.type !== "application/pdf"
          &&
          !file.name
            .toLowerCase()
            .endsWith(".pdf")
        ) {

          if (error) {
            error.textContent =
              "Sélectionne un fichier PDF.";
          }

          return;
        }


        const body =
          new FormData();

        body.append(
          "pdf",
          file
        );


        uploadStatus.hidden = false;

        uploadStatusText.textContent =
          "Envoi du PDF…";


        try {

          const response =
            await fetch(
              "/api/upload",
              {
                method: "POST",
                body,
              }
            );


          const result =
            await response.json();


          if (!response.ok) {

            throw new Error(
              result.error
              ||
              "Impossible d'importer ce PDF."
            );

          }


          uploadStatusText.textContent =
            "Analyse et création du cours…";


          window.location.assign('/upload?job_id=' + encodeURIComponent(result.job_id));

        }

        catch (uploadError) {

          uploadStatusText.textContent =
            uploadError.message
            ||
            "Erreur pendant l'import.";

        }

        finally {

          pdfInput.value = "";

        }

      }
    );



  }
);
