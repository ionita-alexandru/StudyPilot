'use strict';
// Le serveur rend le Markdown après échappement ; aucune sortie IA brute en HTML.
window.StudyChat = {
  mount(root, context) {
    root = root.querySelector('.tutor') || root;
    const toolbar = document.createElement('div'); toolbar.className = 'tutor-toolbar';
    const expand = document.createElement('button'); expand.type = 'button';
    expand.textContent = 'Agrandir le chat'; expand.setAttribute('aria-expanded', 'false');
    toolbar.append(expand); root.prepend(toolbar);
    let expanded = null;
    expand.onclick = () => {
      if (expanded) {expanded.close(); return;}
      const slot = document.createComment('emplacement du chat');
      const scroll = messages.scrollTop;
      root.before(slot);
      const dialog = document.createElement('dialog'); dialog.className = 'tutor-dialog';
      dialog.setAttribute('aria-label', 'Assistant pédagogique agrandi');
      document.body.append(dialog); dialog.append(root); root.classList.add('tutor-expanded-root');
      expanded = dialog; expand.textContent = 'Réduire le chat'; expand.setAttribute('aria-expanded', 'true');
      dialog.addEventListener('close', () => {
        const position = messages.scrollTop;
        slot.replaceWith(root); root.classList.remove('tutor-expanded-root');
        dialog.remove(); expanded = null;
        expand.textContent = 'Agrandir le chat'; expand.setAttribute('aria-expanded', 'false');
        messages.scrollTop = position; expand.focus({preventScroll:true});
      }, {once:true});
      dialog.showModal(); messages.scrollTop = scroll; input.focus({preventScroll:true});
    };
    let conversationId = null;
    let cardId = context.cardId || null;
    let busy = false;
    let exercise = null, generation = 0;
    let anchor = cardId || 'course';
    const key = () => `studypilot.conversation.v1:${context.courseId}:${anchor}`;
    const messages = root.querySelector('[data-chat-messages]');
    const form = root.querySelector('form');
    const input = form.querySelector('textarea, input');
    const send = form.querySelector('[type="submit"]');
    const error = root.querySelector('[data-chat-error]');
    const subject = root.querySelector('[data-chat-subject]');
    root.querySelector('.tutor-followups')?.remove();
    const controls = document.createElement('div'); controls.className = 'tutor-exercise'; controls.hidden = true;
    controls.innerHTML = '<details><summary>Exercice en cours</summary><div data-exercise-statement></div></details><div class="tutor-followups"><button type="button" data-chat-action="hint">Un indice</button><button type="button" data-chat-action="solution">La solution</button></div><label>Ton message <select aria-label="Type de message"><option value="assess">Répondre à l’exercice</option><option value="question">Poser une question</option></select></label>';
    form.before(controls);
    const mode = controls.querySelector('select');
    const reset = document.createElement('button'); reset.type='button'; reset.className='tutor-reset'; reset.textContent='Nouvelle discussion'; form.after(reset);
    const prompts = {example: 'Montre un exemple simple d’utilisation de cette notion.',
      explain: 'Explique cette notion plus en détail, progressivement.',
      discover: 'Je découvre cette notion. Explique ses prérequis puis son idée, sans supposer que j’ai lu le cours.',
      exercise: 'Propose un exercice simple sur cette notion, sans donner la solution.',
      hint: 'Donne-moi un indice pour cet exercice.', solution: 'Explique la solution de cet exercice.'};
    function bubble(author, text, html, pages) {
      const box = document.createElement('article'); box.className = 'tutor-message';
      const label = document.createElement('strong'); label.textContent = author;
      const body = document.createElement('div'); body.className = 'tutor-body';
      if (html) body.innerHTML = html; else body.textContent = text;
      box.append(label, body);
      if (pages?.length) {
        const refs = document.createElement('small'); refs.textContent = 'Passages consultés : ';
        for (const page of pages) {
          const link = document.createElement('a'); link.textContent = `p. ${page} `;
          link.href = `${context.pdfUrl}#page=${Number(page)}`; link.target = '_blank'; link.rel = 'noopener'; refs.append(link);
        }
        box.append(refs);
      }
      messages.append(box);
      // Lire le début de la nouvelle réponse, pas seulement sa conclusion.
      const reveal = () => {messages.scrollTop += box.getBoundingClientRect().top - messages.getBoundingClientRect().top;};
      if (window.MathJax?.typesetPromise) window.MathJax.startup.promise.then(() => window.MathJax.typesetPromise([box])).then(reveal).catch(() => {});
      reveal();
    }
    function showExercise(value) {
      exercise=value; controls.hidden=!value;
      const statement=controls.querySelector('[data-exercise-statement]');
      if(value?.statement_html) statement.innerHTML=value.statement_html; else statement.textContent=value?.statement || '';
      if(value&&window.MathJax?.typesetPromise)window.MathJax.startup.promise.then(()=>window.MathJax.typesetPromise([statement])).catch(()=>{});
    }
    async function restore() {
      const token=++generation; let id;
      try{id=localStorage.getItem(key());}catch{}
      if(!id)return;
      try {
        const response=await fetch(`/api/conversation/${encodeURIComponent(context.courseId)}/${encodeURIComponent(id)}`);
        if(!response.ok)throw Error('La discussion précédente ne peut pas être chargée. Rouvre cette fiche pour réessayer.');
        const result=await response.json(); if(token!==generation)return;
        conversationId=result.conversation_id; cardId=result.active_card_id || cardId;
        for(const m of result.history)bubble(m.role==='user'?'Toi':'StudyPilot · discussion reprise',m.content,m.html);
        showExercise(result.exercise); if(subject&&result.active_title)subject.textContent=result.active_title;
      }catch(e){if(token===generation)error.textContent=e.message;}
    }
    let ready=restore();
    async function ask(intent='question', text=null) {
      if (busy) return;
      busy = true; await ready;
      const question = text || input.value.trim(); if (!question) {busy=false;return;}
      send.disabled = true; reset.disabled=true; send.textContent = 'Réponse en cours…'; error.textContent = '';
      root.querySelectorAll('[data-chat-action]').forEach(b => b.disabled = true);
      bubble('Toi', question); input.value = '';
      try {
        const response = await fetch('/api/part-chat', {method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({course_id:context.courseId, part_number:String(context.partNumber),
            card_id:cardId, conversation_id:conversationId, contextual:true, intent, question})});
        const result = await response.json(); if (!response.ok) throw Error(result.error || 'Réponse indisponible.');
        conversationId = result.conversation_id;
        cardId = result.active_card_id || cardId;
        try{localStorage.setItem(key(),conversationId);}catch{}
        showExercise(result.exercise); if(intent==='exercise')mode.value='assess';
        const label=result.source==='saved_resource'?'Exemple du cours':result.assessment?.basis==='local_calculation'?'StudyPilot · calcul vérifié localement':result.assessment?.basis==='input_format'?'StudyPilot · résultat à préciser':result.assessment?'StudyPilot · évaluation IA':result.source==='exercise_hint'||result.source==='exercise_solution'?'StudyPilot · exercice conservé':'StudyPilot · réponse générée';
        bubble(label, result.answer, result.answer_html, result.pages);
        if(result.assessment&&cardId)window.StudyProgress?.assess(context.courseId,cardId,result.assessment,result.exercise?.id);
        if (subject && result.active_title) subject.textContent = result.active_title;
      } catch (e) { error.textContent = e.message; input.value = question; }
      finally {
        busy = false; send.disabled = false; reset.disabled=false; send.textContent = 'Envoyer';
        root.querySelectorAll('[data-chat-action]').forEach(b => b.disabled = false);
        input.focus();
      }
    }
    form.addEventListener('submit', event => {event.preventDefault(); ask(exercise?mode.value:'question');});
    root.querySelectorAll('[data-chat-action]').forEach(b => b.addEventListener('click', () => ask(b.dataset.chatAction, prompts[b.dataset.chatAction])));
    reset.onclick=()=>{if(busy)return;generation++;conversationId=null;messages.replaceChildren();showExercise(null);try{localStorage.removeItem(key());}catch{}error.textContent='';};
    return {ask, isBusy:()=>busy, async select(id, title, intent, nextContext) {
      if (busy) {error.textContent='Attends la fin de la réponse avant de changer de notion.';return false;}
      if(nextContext)Object.assign(context,nextContext);
      if ((id || 'course') !== anchor) {generation++;cardId = id || null;anchor=cardId || 'course'; conversationId = null; messages.replaceChildren();showExercise(null);ready=restore();}
      if (subject) subject.textContent = title || 'Le cours';
      await ready; if (intent) await ask(intent, prompts[intent]); return true;
    }};
  },
  markup() { return `<section class="tutor" aria-label="Assistant pédagogique"><h3>Comprendre avec StudyPilot</h3><p data-chat-subject class="tutor-subject"></p><div data-chat-messages class="tutor-messages" role="log" aria-live="polite"></div><div class="tutor-followups"><button type="button" data-chat-action="hint">Un indice</button><button type="button" data-chat-action="solution">La solution</button></div><form><label>Ta question ou ta réponse<textarea maxlength="1000" rows="2" placeholder="Explique ton idée, ton résultat ou ce qui te bloque…" required></textarea></label><button type="submit">Envoyer</button></form><p data-chat-error role="alert"></p></section>`; }
};
