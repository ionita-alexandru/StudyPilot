(() => {
    "use strict";
    const form = document.getElementById("upload-form");
    const input = document.getElementById("pdf-file");
    const submit = document.getElementById("upload-submit");
    const selected = document.getElementById("selected-filename");
    const progress = document.getElementById("upload-progress");
    const statusTitle = document.getElementById("upload-status-title");
    const statusDetail = document.getElementById("upload-status-detail");
    const errorBox = document.getElementById("upload-error");
    const resume = document.getElementById("upload-resume");
    const open = document.getElementById("upload-open");
    let resumeUrl = null;
    const storageKey = 'studypilot.lastImport';
    function remember(jobId) {
        try { if (jobId) localStorage.setItem(storageKey, jobId); else localStorage.removeItem(storageKey); } catch (_) {}
    }

    input.addEventListener("change", () => {
        selected.textContent = input.files.length ? input.files[0].name : "Aucun fichier sélectionné";
    });

    function setStatus(title, detail) {
        progress.hidden = false;
        statusTitle.textContent = title;
        statusDetail.textContent = detail;
    }

    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
        progress.hidden = true;
        submit.disabled = false;
        input.disabled = false;
    }

    async function readJson(response) {
        try { return await response.json(); } catch (_) { return {}; }
    }

    async function followImport(statusUrl) {
        resume.hidden = true;
        open.hidden = true;
        while (true) {
            await new Promise(resolve => setTimeout(resolve, 2500));
            const response = await fetch(statusUrl, { cache: "no-store" });
            const result = await readJson(response);
            if (!response.ok) {
                showError(result.error || "Suivi interrompu : vérifie que le serveur est toujours ouvert.");
                return;
            }
            if (result.status === "queued") {
                setStatus("Cours dans la file d’attente", "Une autre analyse est en cours. StudyPilot traitera ton PDF ensuite.");
            } else if (result.status === "processing") {
                const stage = result.current_state || '';
                const label = stage.startsWith('inventaire') ? 'Notions' : stage.startsWith('fiches') ? 'Fiches' : 'Plan et aperçus';
                const detail = result.total
                    ? `${label} : ${result.done || 0}/${result.total} éléments traités. ${result.current_part && !stage.startsWith('fiches') ? `Partie ${result.current_part} en cours.` : ''}`
                    : "Extraction du PDF et préparation du plan pédagogique. Cela peut prendre plusieurs minutes.";
                setStatus("StudyPilot structure ton cours…", detail);
            } else if (result.status === "ready") {
                remember(null);
                setStatus("Cours prêt !", "Le plan, les vues d’ensemble et les fiches sont prêts. Ouverture du cours…");
                window.location.assign(result.course_url);
                return;
            } else if (["partial", "interrupted", "error"].includes(result.status)) {
                setStatus("Analyse à reprendre", result.error || "Des éléments restent à traiter ou à vérifier. Les résultats déjà enregistrés sont conservés.");
                resumeUrl = result.resume_url;
                resume.hidden = !resumeUrl;
                resume.disabled = false;
                if (result.course_url) { open.href = result.course_url; open.hidden = false; }
                submit.disabled = false;
                input.disabled = false;
                return;
            } else {
                showError("État d'analyse inattendu.");
                return;
            }
        }
    }

    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (!input.files.length) { showError("Sélectionne un PDF."); return; }
        const file = input.files[0];
        if (!file.name.toLowerCase().endsWith(".pdf")) {
            showError("Sélectionne un fichier .pdf.");
            return;
        }
        if (file.size > 20 * 1024 * 1024) {
            showError("Le PDF dépasse la limite de 20 Mo.");
            return;
        }
        submit.disabled = true;
        input.disabled = true;
        errorBox.hidden = true;
        setStatus("Envoi du PDF…", "Vérification du fichier avant traitement.");
        try {
            const body = new FormData();
            body.append("pdf", file);
            const response = await fetch("/api/upload", { method: "POST", body });
            const result = await readJson(response);
            if (!response.ok || !result.status_url) {
                showError(result.error || "Impossible d'importer ce PDF.");
                return;
            }
            setStatus("PDF reçu !", "Ton cours a été ajouté à la file de traitement.");
            remember(result.job_id);
            history.replaceState(null, '', '/upload?job_id=' + encodeURIComponent(result.job_id));
            await followImport(result.status_url);
        } catch (_) {
            showError("Connexion au serveur interrompue. Vérifie que StudyPilot est ouvert.");
        }
    });

    resume.addEventListener('click', async () => {
        resume.disabled = true;
        errorBox.hidden = true;
        try {
            const response = await fetch(resumeUrl, {method: 'POST'});
            const result = await readJson(response);
            if (!response.ok) throw new Error(result.error || 'Reprise impossible.');
            submit.disabled = true;
            input.disabled = true;
            await followImport(result.status_url);
        } catch (error) { showError(error.message); resume.disabled = false; }
    });
    let lastJob = new URLSearchParams(location.search).get('job_id');
    try { lastJob ||= localStorage.getItem(storageKey); } catch (_) {}
    if (/^[a-f0-9]{32}$/.test(lastJob || '')) {
        submit.disabled = true;
        input.disabled = true;
        setStatus('Récupération de ton import…', 'Lecture du dernier état enregistré.');
        followImport('/api/upload/status/' + lastJob).catch(() => showError('Suivi interrompu. Recharge cette page pour le retrouver.'));
    }
})();
