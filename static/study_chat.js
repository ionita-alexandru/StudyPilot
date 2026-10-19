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
    const sendLabel = send.textContent;
    const status = root.querySelector('[data-chat-status]');
    root.querySelector('.tutor-followups')?.remove();
    const controls = document.createElement('div'); controls.className = 'tutor-exercise'; controls.hidden = true;
    controls.innerHTML = '<details><summary>Exercice en cours</summary><div data-exercise-statement></div></details><div class="tutor-followups"><button type="button" data-chat-action="hint">Un indice</button><button type="button" data-chat-action="solution">La solution</button></div><label>Ton message <select aria-label="Type de message"><option value="assess">Répondre à l’exercice</option><option value="question">Poser une question</option></select></label>';
    form.before(controls);
    const mode = controls.querySelector('select');
    const reset = document.createElement('button'); reset.type='button'; reset.className='tutor-reset'; reset.textContent='Nouvelle discussion'; form.after(reset);
    // Le même formulaire reste monté pendant la lecture et les changements de rubrique.
    let discussionToggle = null, pendingMessage = null;
    function reveal(focus = true) {
      if (discussionToggle) {
        root.classList.add('tutor-discussion-open');
        discussionToggle.setAttribute('aria-expanded', 'true');
        discussionToggle.textContent = 'Replier la discussion';
        messages.hidden = controls.hidden = reset.hidden = false;
        controls.hidden = !exercise;
        if (pendingMessage) {
          messages.scrollTop += pendingMessage.getBoundingClientRect().top - messages.getBoundingClientRect().top;
          pendingMessage = null;
        }
      }
      if (focus) input.focus({preventScroll:true});
    }
    if (context.docked) {
      root.classList.add('tutor-docked');
      discussionToggle = document.createElement('button'); discussionToggle.type = 'button';
      discussionToggle.className = 'tutor-discussion-toggle';
      discussionToggle.textContent = 'Ouvrir la discussion'; discussionToggle.setAttribute('aria-expanded', 'false');
      messages.id = 'course-discussion'; discussionToggle.setAttribute('aria-controls', messages.id);
      toolbar.prepend(discussionToggle); messages.hidden = reset.hidden = true;
      discussionToggle.onclick = () => {
        if (!root.classList.contains('tutor-discussion-open')) {reveal(false); return;}
        root.classList.remove('tutor-discussion-open'); messages.hidden = reset.hidden = true;
        controls.hidden = !exercise;
        discussionToggle.textContent = messages.children.length ? `Discussion · ${messages.children.length} messages` : 'Ouvrir la discussion'; discussionToggle.setAttribute('aria-expanded', 'false');
      };
      // Réserver la hauteur réelle de la barre, y compris avec zoom ou message d'erreur.
      const dock = root.parentElement;
      new ResizeObserver(() => {
        if (expanded) return;
        document.documentElement.style.setProperty('--composer-height', `${Math.ceil(dock.getBoundingClientRect().height)}px`);
      }).observe(dock);
      expand.addEventListener('click', () => reveal(false));
    }
    const prompts = {example: 'Montre un exemple simple d’utilisation de cette notion.',
      explain: 'Explique cette notion plus en détail, progressivement.',
      discover: 'Je découvre cette notion. Explique ses prérequis puis son idée, sans supposer que j’ai lu le cours.',
      exercise: 'Propose un exercice simple sur cette notion, sans donner la solution.',
      hint: 'Donne-moi un indice pour cet exercice.', solution: 'Explique la solution de cet exercice.'};
    function bubble(author, text, html, pages, references) {
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
      if (references?.length) {
        const refs=document.createElement('small');refs.textContent='Compléments consultés : ';
        const seen=new Set();
        for(const ref of references){
          if(typeof ref.url!=='string'||!ref.url.startsWith('/course/')||seen.has(ref.url))continue;
          seen.add(ref.url);const link=document.createElement('a');link.href=ref.url;link.target='_blank';link.rel='noopener';link.textContent=`${ref.title} · p. ${ref.page} `;refs.append(link);
        }
        box.append(refs);
      }
      if (discussionToggle && messages.hidden) {
        discussionToggle.textContent = `Discussion · ${messages.children.length} messages`;
        pendingMessage = box;
      }
      // Lire le début de la nouvelle réponse, pas seulement sa conclusion.
      const scrollToMessage = () => {
        if (!messages.hidden && messages.contains(box)) messages.scrollTop += box.getBoundingClientRect().top - messages.getBoundingClientRect().top;
      };
      if (window.MathJax?.typesetPromise) window.MathJax.startup.promise.then(() => window.MathJax.typesetPromise([box])).then(scrollToMessage).catch(() => {});
      scrollToMessage();
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
        for(const m of result.history)bubble(m.role==='user'?'Toi':'StudyPilot · discussion reprise',m.content,m.html,null,m.references);
        showExercise(result.exercise); if(subject&&result.active_title)subject.textContent=result.active_title;
      }catch(e){if(token===generation)error.textContent=e.message;}
    }
    let ready=restore();
    async function ask(intent='question', text=null) {
      if (busy) return;
      busy = true; await ready;
      const question = text || input.value.trim(); if (!question) {busy=false;return;}
      reveal(false);
      send.disabled = true; reset.disabled=true;
      if(status) status.textContent='Réponse en cours…'; else send.textContent='Réponse en cours…';
      error.textContent = '';
      root.querySelectorAll('[data-chat-action]').forEach(b => b.disabled = true);
      bubble('Toi', question); input.value = '';
      try {
        const response = await fetch('/api/part-chat', {method:'POST', headers:{'Content-Type':'application/json'},
          body:JSON.stringify({course_id:context.courseId, part_number:String(context.partNumber),
            card_id:cardId, conversation_id:conversationId, contextual:true, intent, question,learner:context.learner})});
        const result = await response.json(); if (!response.ok) throw Error(result.error || 'Réponse indisponible.');
        conversationId = result.conversation_id;
        cardId = result.active_card_id || cardId;
        try{localStorage.setItem(key(),conversationId);}catch{}
        showExercise(result.exercise); if(intent==='exercise')mode.value='assess';
        const label=result.source==='saved_resource'?'Exemple du cours':result.assessment?.basis==='local_calculation'?'StudyPilot · calcul vérifié localement':result.assessment?.basis==='input_format'?'StudyPilot · résultat à préciser':result.assessment?'StudyPilot · évaluation IA':result.source==='exercise_hint'||result.source==='exercise_solution'?'StudyPilot · exercice conservé':'StudyPilot · réponse générée';
        bubble(label, result.answer, result.answer_html, result.pages,result.references);
        if(result.assessment&&cardId)window.StudyProgress?.assess(context.courseId,cardId,result.assessment,result.exercise?.id);
        if (subject && result.active_title) subject.textContent = result.active_title;
      } catch (e) { error.textContent = e.message; input.value = question; }
      finally {
        busy = false; send.disabled = false; reset.disabled=false; send.textContent = sendLabel;
        if(status) status.textContent='';
        root.querySelectorAll('[data-chat-action]').forEach(b => b.disabled = false);
        input.focus({preventScroll:true});
      }
    }
    form.addEventListener('submit', event => {event.preventDefault(); ask(exercise?mode.value:'question');});
    root.querySelectorAll('[data-chat-action]').forEach(b => b.addEventListener('click', () => ask(b.dataset.chatAction, prompts[b.dataset.chatAction])));
    reset.onclick=()=>{if(busy)return;generation++;conversationId=null;pendingMessage=null;messages.replaceChildren();showExercise(null);try{localStorage.removeItem(key());}catch{}error.textContent='';};
    return {ask, reveal, isBusy:()=>busy, async select(id, title, intent, nextContext) {
      if (busy) {error.textContent='Attends la fin de la réponse avant de changer de notion.';return false;}
      const changedCourse = nextContext?.courseId && nextContext.courseId !== context.courseId;
      if(nextContext)Object.assign(context,nextContext);
      if (changedCourse || (id || 'course') !== anchor) {generation++;cardId = id || null;anchor=cardId || 'course'; conversationId = null; pendingMessage = null; messages.replaceChildren();showExercise(null);ready=restore();}
      if (subject) subject.textContent = title || 'Le cours';
      await ready; if (intent) await ask(intent, prompts[intent]); return true;
    }};
  },
  markup() { return `<section class="tutor tutor-composer" aria-label="Assistant pédagogique"><h3>Comprendre avec StudyPilot</h3><div data-chat-messages class="tutor-messages" role="log" aria-live="polite"></div><form class="chat-composer"><label><span class="chat-input-label">Ta question ou ta réponse</span><textarea maxlength="1000" rows="2" placeholder="Demander à StudyPilot…" required></textarea></label><div class="composer-footer"><span class="composer-context"><span class="context-dot" aria-hidden="true"></span><span data-chat-subject class="tutor-subject"></span></span><span data-chat-status role="status"></span><button type="submit" aria-label="Envoyer" title="Envoyer">↑</button></div></form><p data-chat-error role="alert"></p></section>`; }
};
