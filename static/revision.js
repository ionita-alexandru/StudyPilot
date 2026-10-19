document.addEventListener(
  "DOMContentLoaded",
  () => {

    const setup =
      document.querySelector("#revision-setup");

    const session =
      document.querySelector("#revision-session");

    const summary =
      document.querySelector("#revision-summary");

    const courseSelect =
      document.querySelector("#revision-course");

    const partSelect =
      document.querySelector("#revision-part");

    const startButton =
      document.querySelector("#revision-start");

    const errorBox =
      document.querySelector("#revision-setup-error");

    const cardInfo =
      document.querySelector("#revision-card-info");

    const customDuration =
      document.querySelector("#revision-custom-duration");

    let courseData = null;
    let courseRequest = 0;
    const chatDock = document.querySelector('.sp-revision-chat-panel');

    let cards = [];

    let currentCardIndex = 0;

    let selectedDuration = 45;

    let pomodoroMode = "off";

    let totalWorkSeconds = 0;

    let workRemaining = 0;

    let phaseRemaining = 0;

    let focusSeconds = 0;

    let breakSeconds = 0;

    let phase = "focus";

    let paused = false;

    let timer = null;

    let cardsSeen = 0;

    let masteredCount = 0;

    let reviewCount = 0;

    let almostCount = 0;

    function formatTime(seconds) {

      const safe =
        Math.max(
          0,
          Math.floor(seconds)
        );

      const minutes =
        Math.floor(safe / 60);

      const secs =
        safe % 60;

      return (
        String(minutes)
        +
        ":"
        +
        String(secs).padStart(
          2,
          "0"
        )
      );

    }

    async function loadCourse() {
      const request = ++courseRequest;
      courseData = null; cards = []; startButton.disabled = true;
      partSelect.replaceChildren(new Option('Tout le cours', ''));
      document.dispatchEvent(new CustomEvent('learning-course', {detail:{
        courseId:courseSelect.value, title:courseSelect.selectedOptions[0]?.textContent.trim() || ''
      }}));

      const courseId =
        courseSelect.value;

      if (!courseId) {
        return;
      }

      errorBox.textContent = "";

      cardInfo.textContent =
        "Chargement des fiches…";

      try {

        const response =
          await fetch(
            `/api/revision?course_id=${encodeURIComponent(
              courseId
            )}`
          );

        const data =
          await response.json();

        if (!response.ok) {

          throw new Error(
            data.error
            ||
            "Impossible de charger ce cours."
          );

        }

        if (request !== courseRequest) return;
        courseData = data;

        partSelect.innerHTML =
          '<option value="">Tout le cours</option>';

        for (const part of data.parts) {

          const option =
            document.createElement("option");

          option.value =
            part.number;

          option.textContent =
            `Partie ${part.number} · ${part.title}`;

          partSelect.append(option);

        }

        updateAvailableCards();

      }

      catch (error) {
        if (request !== courseRequest) return;

        courseData = null;

        cards = [];

        errorBox.textContent =
          error.message;

        cardInfo.textContent = "";

      }

    }

    function updateAvailableCards() {

      if (!courseData) {
        return;
      }

      const selectedPart =
        partSelect.value;

      cards =
        selectedPart
          ? courseData.cards.filter(
              card =>
                String(
                  card.part_number
                )
                === selectedPart
            )
          : [...courseData.cards];

      startButton.disabled = !cards.length;
      cardInfo.textContent =
        `${cards.length} fiche${
          cards.length > 1 ? "s" : ""
        } disponible${
          cards.length > 1 ? "s" : ""
        }.`;

    }

    courseSelect.addEventListener(
      "change",
      loadCourse
    );

    partSelect.addEventListener(
      "change",
      updateAvailableCards
    );

    for (
      const button
      of document.querySelectorAll(
        "[data-duration]"
      )
    ) {

      button.addEventListener(
        "click",
        () => {

          document
            .querySelectorAll(
              "[data-duration]"
            )
            .forEach(
              item =>
                item.classList.remove(
                  "active"
                )
            );

          button.classList.add(
            "active"
          );

          selectedDuration =
            Number(
              button.dataset.duration
            );

          customDuration.value = "";

        }
      );

    }

    customDuration.addEventListener(
      "input",
      () => {

        const value =
          Number(customDuration.value);

        if (
          Number.isFinite(value)
          &&
          value >= 5
        ) {

          selectedDuration =
            Math.min(
              value,
              240
            );

          document
            .querySelectorAll(
              "[data-duration]"
            )
            .forEach(
              item =>
                item.classList.remove(
                  "active"
                )
            );

        }

      }
    );

    for (
      const button
      of document.querySelectorAll(
        "[data-pomodoro]"
      )
    ) {

      button.addEventListener(
        "click",
        () => {

          document
            .querySelectorAll(
              "[data-pomodoro]"
            )
            .forEach(
              item =>
                item.classList.remove(
                  "active"
                )
            );

          button.classList.add(
            "active"
          );

          pomodoroMode =
            button.dataset.pomodoro;

        }
      );

    }

    startButton.addEventListener(
      "click",
      startSession
    );

    function startSession() {
      if (sharedTutor?.isBusy()) {
        errorBox.textContent = 'Attends la fin de la réponse avant de démarrer une nouvelle session.';
        return;
      }

      if (!courseData) {

        errorBox.textContent =
          "Le cours n'est pas chargé.";

        return;
      }

      if (!cards.length) {

        errorBox.textContent =
          "Aucune fiche disponible.";

        return;
      }

      if (
        !Number.isFinite(
          selectedDuration
        )
        ||
        selectedDuration < 5
      ) {

        errorBox.textContent =
          "Choisis une durée valide.";

        return;
      }

      totalWorkSeconds =
        Math.round(
          selectedDuration * 60
        );

      workRemaining =
        totalWorkSeconds;

      configurePomodoro();

      cardsSeen = 0;

      masteredCount = 0;

      reviewCount = 0;

      almostCount = 0;

      currentCardIndex = 0;

      paused = false;

      setup.hidden = true;

      summary.hidden = true;

      session.hidden = false;
      chatDock.hidden = false;
      document.querySelector('#session-pause').textContent = 'Pause';

      document.querySelector(
        "#session-course-name"
      ).textContent =
        courseData.course.title;

      const selectedOption =
        partSelect.options[
          partSelect.selectedIndex
        ];

      document.querySelector(
        "#session-part-name"
      ).textContent =
        selectedOption.textContent;

      showCard();

      renderTimer();

      startTimer();

    }

    function configurePomodoro() {

      phase = "focus";

      if (
        pomodoroMode === "25"
      ) {

        focusSeconds =
          25 * 60;

        breakSeconds =
          5 * 60;

      }

      else if (
        pomodoroMode === "50"
      ) {

        focusSeconds =
          50 * 60;

        breakSeconds =
          10 * 60;

      }

      else {

        focusSeconds =
          totalWorkSeconds;

        breakSeconds = 0;

      }

      phaseRemaining =
        Math.min(
          focusSeconds,
          workRemaining
        );

    }

    function startTimer() {

      clearInterval(timer);

      timer =
        setInterval(
          tick,
          1000
        );

    }

    function tick() {

      if (paused) {
        return;
      }

      if (phase === "focus") {

        workRemaining =
          Math.max(
            0,
            workRemaining - 1
          );

        phaseRemaining =
          Math.max(
            0,
            phaseRemaining - 1
          );

        if (
          workRemaining <= 0
        ) {

          finishSession();

          return;
        }

        if (
          phaseRemaining <= 0
        ) {

          if (
            pomodoroMode === "off"
          ) {

            finishSession();

            return;
          }

          phase = "break";

          phaseRemaining =
            breakSeconds;

        }

      }

      else {

        phaseRemaining =
          Math.max(
            0,
            phaseRemaining - 1
          );

        if (
          phaseRemaining <= 0
        ) {

          phase = "focus";

          phaseRemaining =
            Math.min(
              focusSeconds,
              workRemaining
            );

        }

      }

      renderTimer();

    }

    function renderTimer() {

      const phaseLabel =
        document.querySelector(
          "#session-phase-label"
        );

      phaseLabel.textContent =
        phase === "focus"
          ? "Focus"
          : "Pause";

      phaseLabel.classList.toggle(
        "focus",
        phase === "focus"
      );

      phaseLabel.classList.toggle(
        "break",
        phase === "break"
      );

      document.querySelector(
        "#session-phase-time"
      ).textContent =
        formatTime(
          phaseRemaining
        );

      document.querySelector(
        "#session-work-time"
      ).textContent =
        formatTime(
          workRemaining
        );

      const done =
        totalWorkSeconds
        -
        workRemaining;

      const progress =
        totalWorkSeconds > 0
          ? (
              done
              /
              totalWorkSeconds
            ) * 100
          : 0;

      document.querySelector(
        "#session-progress-bar"
      ).style.width =
        `${Math.min(
          100,
          progress
        )}%`;

    }

  function getCurrentCard() {

  if (!cards.length) {
    return null;
  }

  return cards[
    currentCardIndex
    %
    cards.length
  ];

}

    function showCard() {

      const card =
  getCurrentCard();

      const labels = {rule:"Règle",definition:"Définition", concept:"Concept", property:"Propriété", theorem:"Théorème", formula:"Formule", method:"Méthode", protocol:"Protocole", syntax:"Syntaxe", command:"Commande", example:"Exemple", remark:"Remarque"};
      document.querySelector("#revision-card-type").textContent = labels[card.concept_type] || "Notion";

      document.querySelector(
        "#revision-card-title"
      ).innerHTML = card.title_html || escapeHtml(card.title);

      document.querySelector(
        "#revision-card-part"
      ).textContent =
        `Partie ${card.part_number} · ${card.part_title}`;

      document.querySelector(
        "#revision-card-counter"
      ).textContent =
        `${(
          currentCardIndex
          %
          cards.length
        ) + 1} / ${cards.length}`;

      resetRevisionChat();

      document.querySelector(
        "#revision-card-hidden"
      ).hidden = false;

      document.querySelector(
        "#revision-card-content"
      ).hidden = true;

      document.querySelector(
        "#revision-rating"
      ).hidden = true;

      document.querySelector(
        "#revision-card-content"
      ).replaceChildren();

    }

    document.querySelector(
      "#revision-reveal"
    ).addEventListener(
      "click",
      revealCard
    );

    function revealCard() {

      const card =
        cards[
          currentCardIndex
          %
          cards.length
        ];

      const container =
        document.querySelector(
          "#revision-card-content"
        );

      container.replaceChildren();

      // HTML produit par le renderer serveur, qui échappe tout contenu source.
      container.innerHTML = card.content_html || "";
      for (const [index, illustration] of (card.illustrations || []).entries()) {
        const figure = document.createElement("figure");
        const img = document.createElement("img");
        img.src = `/course/${encodeURIComponent(courseSelect.value)}/card/${encodeURIComponent(card.card_id)}/illustration/${index}`;
        img.alt = `Illustration du cours : ${card.title}`;
        img.style.maxWidth = "100%";
        const caption = document.createElement("figcaption");
        caption.textContent = `Extrait original — page ${illustration.page}`;
        const link = document.createElement("a");
        link.href = `${courseData.course.pdf_url}#page=${illustration.page}`;
        link.target = "_blank"; link.rel = "noopener noreferrer";
        link.append(img); figure.className = "sp-source-figure";
        figure.append(link, caption);
        container.append(figure);
      }

      if (
        Array.isArray(
          card.source_pages
        )
        &&
        card.source_pages.length
      ) {

        const source =
          document.createElement(
            "small"
          );

        source.className =
          "sp-revision-source";

        source.append(document.createTextNode("Source : "));
        card.source_pages.forEach((page, index) => {
          if (index) source.append(document.createTextNode(", "));
          const link = document.createElement("a");
          link.href = `${courseData.course.pdf_url}#page=${page}`;
          link.textContent = `p.${page}`;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          source.append(link);
        });

        container.append(
          source
        );

      }

      document.querySelector(
        "#revision-card-hidden"
      ).hidden = true;

      container.hidden = false;

      document.querySelector(
        "#revision-rating"
      ).hidden = false;

      window.MathJax
        ?.typesetPromise?.(
          [container, document.querySelector("#revision-card-title")]
        )
        .catch(
          () => {}
        );

    }

    for (
      const button
      of document.querySelectorAll(
        "[data-rating]"
      )
    ) {

      button.addEventListener(
        "click",
        () => {

          rateCurrentCard(
            button.dataset.rating
          );

        }
      );

    }

    let sharedTutor = null;
    function escapeHtml(value) {const span=document.createElement('span');span.textContent=value;return span.innerHTML;}
    function resetRevisionChat() {
      const card=getCurrentCard(); if(!card)return;
      const ctx={docked:true,courseId:courseData.course.course_id,partNumber:card.part_number,pdfUrl:courseData.course.pdf_url,cardId:card.card_id};
      if(!sharedTutor){
        const panel=document.querySelector('.sp-revision-chat-panel');
        panel.innerHTML=StudyChat.markup();
        sharedTutor=StudyChat.mount(panel,ctx);
        document.querySelectorAll('[data-revision-action]').forEach(b=>b.onclick=()=>{const c=getCurrentCard();sharedTutor.select(c.card_id,c.title,b.dataset.revisionAction,{partNumber:c.part_number});sharedTutor.reveal();});
      }
      sharedTutor.select(card.card_id,card.title,null,ctx);
    }

    function rateCurrentCard(
      rating
    ) {
      if(sharedTutor?.isBusy())return;
      const card=getCurrentCard();
      cardsSeen += 1;

      if (
        rating === "mastered"
      ) {

        masteredCount += 1;

      }

      else if (
        rating === "review"
      ) {

        reviewCount += 1;

      }

      else {

        almostCount += 1;

      }

      saveProgress(
        card,
        rating
      );

      currentCardIndex += 1;

      showCard();

    }

    function saveProgress(card,rating) {StudyProgress.mark(courseData.course.course_id,card.card_id,rating);}

    document.querySelector(
      "#session-pause"
    ).addEventListener(
      "click",
      event => {

        paused =
          !paused;

        event.currentTarget
          .textContent =
            paused
              ? "Reprendre"
              : "Pause";

      }
    );

    document.querySelector(
      "#session-end"
    ).addEventListener(
      "click",
      finishSession
    );

    function finishSession() {

      clearInterval(timer);

      timer = null;

      const worked =
        totalWorkSeconds
        -
        workRemaining;

      saveSessionLog(
        worked
      );

      session.hidden = true;
      chatDock.hidden = true;

      summary.hidden = false;

      document.querySelector(
        "#summary-time"
      ).textContent =
        `${Math.round(
          worked / 60
        )} min`;

      document.querySelector(
        "#summary-seen"
      ).textContent =
        cardsSeen;

      document.querySelector(
        "#summary-mastered"
      ).textContent =
        masteredCount;

      document.querySelector(
        "#summary-review"
      ).textContent =
        reviewCount;

    }

    function saveSessionLog(
      workedSeconds
    ) {

      const key =
        "studypilot.revision.sessions.v1";

      let sessions = [];

      try {

        sessions =
          JSON.parse(
            localStorage.getItem(
              key
            )
            ||
            "[]"
          );

      }

      catch {

        sessions = [];

      }

      sessions.push({

        course_id:
          courseData.course.course_id,

        course_title:
          courseData.course.title,

        part_number:
          partSelect.value || null,

        pomodoro:
          pomodoroMode,

        planned_work_minutes:
          selectedDuration,

        worked_seconds:
          workedSeconds,

        cards_seen:
          cardsSeen,

        mastered:
          masteredCount,

        almost:
          almostCount,

        review:
          reviewCount,

        ended_at:
          new Date()
            .toISOString(),

      });

      localStorage.setItem(
        key,
        JSON.stringify(
          sessions.slice(-100)
        )
      );

    }

    document.querySelector(
      "#summary-restart"
    ).addEventListener(
      "click",
      () => {

        summary.hidden = true;

        setup.hidden = false;

      }
    );

    const initialCourse =
      new URLSearchParams(
        window.location.search
      ).get("course_id");

    if (
      initialCourse
      &&
      [
        ...courseSelect.options
      ].some(
        option =>
          option.value
          === initialCourse
      )
    ) {

      courseSelect.value =
        initialCourse;

    }

    loadCourse();

  }
);
