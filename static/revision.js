/* Une seule session : libre, guidée ou express. Aucun appel IA pour recalculer le temps. */
'use strict';
document.addEventListener('DOMContentLoaded', () => {
  const $ = id => document.getElementById(id);
  const setup=$('revision-setup'), session=$('revision-session'), summary=$('revision-summary');
  const courseSelect=$('revision-course'), partSelect=$('revision-part'), error=$('revision-setup-error');
  const dock=document.querySelector('.sp-revision-chat-panel');
  let data=null, request=0, cards=[], plan=null, queue=[], current=null, tutor=null, clock=null, timer=null;
  let duration=45, pomodoro='off', running=false, revealed=false, phase='focus', phaseLeft=0, focusTime=0;
  let completed=[], skipped=[], attempts={}, sessionStart=0, initialSeconds=0, materialVersion=null;
  const checkpointKey='studypilot.active-session.v1';let checkpoint=null,lastSave=0;
  function saveCheckpoint() {
    if(!running)return;
    try{localStorage.setItem(checkpointKey,JSON.stringify({courseId:data.course.course_id,revision:materialVersion,
      part:partSelect.value,mode:$('revision-mode').value,level:$('revision-level').value,goal:$('revision-goal').value,
      notes:$('revision-notes').value,plan,queue:queue.map(c=>c.card_id),current:current?.card_id,clock:{...clock,paused:true,last:Date.now()},
      recall:$('revision-recall').value,completed,skipped,attempts,focusTime,phase,phaseLeft,pomodoro,initialSeconds}));}catch{}
  }
  function offerCheckpoint() {
    try{checkpoint=JSON.parse(localStorage.getItem(checkpointKey)||'null');}catch{checkpoint=null;}
    const available=checkpoint?.clock&&checkpoint?.plan?.items&&Array.isArray(checkpoint.queue)&&checkpoint.courseId===data?.course.course_id;
    $('session-resume').hidden=!available;
    if(available)text('session-resume-text',checkpoint.revision!==data.revision?'Les documents ont évolué : reprends pour adapter le parcours au temps restant.':`Une session est en pause · ${checkpoint.clock.deadline?'heure limite conservée':format(checkpoint.clock.remaining)+' restantes'}.`);
  }
  const text=(id,value)=>$(id).textContent=value;
  const format=s=>`${Math.floor(Math.max(0,s)/60)}:${String(Math.floor(Math.max(0,s))%60).padStart(2,'0')}`;
  const progress=()=>Object.fromEntries(cards.map(c=>[c.card_id,StudyProgress.get(c.card_id)]));
  function options(seconds) {return {seconds,mode:$('revision-mode').value,level:$('revision-level').value,
    goal:$('revision-goal').value,pomodoro,notes:$('revision-notes').value};}
  function invalidate() {$('revision-plan').hidden=true;plan=null;}
  async function loadCourse() {
    const token=++request; data=null;cards=[];$('revision-start').disabled=true;invalidate();
    partSelect.replaceChildren(new Option('Tout le cours',''));
    document.dispatchEvent(new CustomEvent('learning-course',{detail:{courseId:courseSelect.value,title:courseSelect.selectedOptions[0]?.textContent.trim()||''}}));
    if(!courseSelect.value)return;
    error.textContent='';text('revision-card-info','Chargement des notions…');
    try {
      const response=await fetch(`/api/revision?course_id=${encodeURIComponent(courseSelect.value)}`);
      const value=await response.json();if(token!==request)return;
      if(!response.ok)throw Error(value.error||'Le cours ne peut pas être chargé.');
      data=value;for(const part of value.parts)partSelect.append(new Option(`${part.number} · ${part.title}`,part.number));
      updateCards();offerCheckpoint();
    }catch(e){if(token===request){error.textContent=e.message;text('revision-card-info','');}}
  }
  function updateCards() {
    cards=(data?.cards||[]).filter(c=>!partSelect.value||String(c.part_number)===partSelect.value);
    $('revision-start').disabled=!cards.length;text('revision-card-info',`${cards.length} notions disponibles`);invalidate();
    const box=$('revision-diagnostic');box.replaceChildren();
    cards.slice(0,3).forEach(card=>{const label=document.createElement('label');label.textContent=card.title;
      const select=document.createElement('select');select.dataset.diagnostic=card.card_id;
      select.append(new Option('Je ne sais pas encore',''),new Option('À découvrir ou revoir','review'),new Option('Je pense savoir l’expliquer','understood'));
      label.append(select);box.append(label);});
  }
  function budget() {
    if($('revision-clock').value==='deadline') {
      const date=new Date($('revision-deadline').value).getTime();
      const seconds=Math.floor((date-Date.now())/1000);
      if(!Number.isFinite(date)||seconds<300||seconds>28800)throw Error('Choisis une heure limite entre 5 minutes et 8 heures à partir de maintenant.');
      return {seconds,deadline:date};
    }
    const custom=$('revision-custom-duration').value;
    const minutes=custom?Number(custom):duration;
    if(!Number.isFinite(minutes)||minutes<5||minutes>480)throw Error('Choisis entre 5 et 480 minutes.');
    return {seconds:Math.floor(minutes*60),deadline:null};
  }
  function preparationProgress() {
    const records=progress();
    document.querySelectorAll('[data-diagnostic]').forEach(select=>{if(select.value)records[select.dataset.diagnostic]={...records[select.dataset.diagnostic],status:select.value};});
    return records;
  }
  function list(container,items,detail) {
    container.replaceChildren();
    for(const item of items){const li=document.createElement('li');const title=document.createElement('strong');title.textContent=item.title;
      const note=document.createElement('small');note.textContent=detail(item);li.append(title,note);container.append(li);}
    if(!items.length){const li=document.createElement('li');li.textContent='Aucune notion dans cette liste.';container.append(li);}
  }
  function prepare() {
    if(!data||!cards.length)return;
    error.textContent='';
    try {
      const b=budget();plan=StudyPlan.build(cards,options(b.seconds),preparationProgress());plan.deadline=b.deadline;
      if(!plan.items.length)throw Error('Ce temps ne permet pas une activité complète avec ce niveau. Ajoute quelques minutes ou choisis une notion précise.');
      text('plan-description',`${plan.items.length} notions proposées sur ${cards.length} · ${Math.ceil(plan.activitySeconds/60)} min d’activités, ${Math.ceil(plan.breakSeconds/60)} min de pauses et ${Math.ceil(plan.reviewSeconds/60)} min de bilan. La marge reste disponible pour les difficultés.`);
      list($('plan-items'),plan.items.slice(0,3),c=>`${Math.ceil(c.seconds/60)} min · ${c.reason} · ${c.stages.join(' → ')}`);
      $('plan-more').hidden=plan.items.length<=3;list($('plan-rest'),plan.items.slice(3),c=>`${Math.ceil(c.seconds/60)} min · ${c.reason}`);
      list($('plan-omitted'),plan.omitted,c=>c.reason);
      text('plan-warning',[...plan.warnings,plan.omitted.length?'Le programme priorise une partie du cours ; il ne garantit pas de tout maîtriser dans ce temps.':'Une réussite isolée ne prouve pas une maîtrise complète.'].join(' '));
      $('revision-plan').hidden=false;$('revision-plan').scrollIntoView({behavior:'smooth',block:'start'});
    }catch(e){error.textContent=e.message;}
  }
  function mountTutor() {
    const ctx={docked:true,courseId:data.course.course_id,partNumber:current.part_number,pdfUrl:data.course.pdf_url,cardId:current.card_id,
      learner:{level:$('revision-level').value,goal:$('revision-goal').value,notes:$('revision-notes').value}};
    if(!tutor){dock.innerHTML=StudyChat.markup();tutor=StudyChat.mount(dock,ctx);}
    tutor.select(current.card_id,current.title,null,ctx);
  }
  function launch() {
    if(!plan||tutor?.isBusy())return;
    let seconds=plan.deadline?Math.floor((plan.deadline-Date.now())/1000):plan.seconds;
    if(seconds<300){error.textContent='L’heure limite est trop proche. Prépare à nouveau le parcours.';return;}
    if(plan.deadline)plan=Object.assign(StudyPlan.build(cards,options(seconds),preparationProgress()),{deadline:plan.deadline});
    if(!plan.items.length)return;
    queue=[...plan.items];completed=[];skipped=[];attempts={};focusTime=0;phase='focus';
    initialSeconds=seconds;sessionStart=Date.now();materialVersion=data.revision;
    clock={remaining:seconds,deadline:plan.deadline,paused:false,last:Date.now()};phaseLeft=Number(pomodoro)*60||seconds;
    running=true;setup.hidden=summary.hidden=true;session.hidden=false;dock.hidden=false;
    text('session-pause','Pause');text('session-course-name',data.course.title);
    text('session-part-name',partSelect.selectedOptions[0].textContent);
    nextCard();renderClock();clearInterval(timer);timer=setInterval(tick,1000);
    saveCheckpoint();
    $('session-pause').focus({preventScroll:true});window.scrollTo({top:0});
  }
  function nextCard() {
    if(!queue.length){finish('Le programme prévu est terminé.');return;}
    current=queue.shift();revealed=false;
    text('revision-card-title',current.title);text('revision-card-part',`${current.part_number} · ${current.part_title}`);
    text('revision-card-type',current.concept_type||'Notion');
    text('revision-card-counter',`${completed.length+skipped.length+1} / ${completed.length+skipped.length+queue.length+1}`);
    text('session-guidance',`${current.reason||'Poursuivre'} · environ ${Math.ceil(current.seconds/60)} min`);
    text('session-step',current.stages.join(' → '));
    $('revision-card-hidden').hidden=false;$('revision-card-content').hidden=true;$('revision-rating').hidden=true;
    $('recall-field').hidden=true;$('revision-recall').value='';$('revision-card-content').replaceChildren();
    mountTutor();
    saveCheckpoint();
  }
  function reveal() {
    if(!current)return;revealed=true;const container=$('revision-card-content');
    container.innerHTML=current.content_html||''; // HTML échappé et rendu par le serveur.
    for(const [index,illustration] of (current.illustrations||[]).entries()) {
      const figure=document.createElement('figure'),img=document.createElement('img');
      img.src=`/course/${encodeURIComponent(data.course.course_id)}/card/${encodeURIComponent(current.card_id)}/illustration/${index}`;
      img.alt=`Illustration du cours : ${current.title}`;figure.append(img);container.append(figure);
    }
    const source=document.createElement('p');source.className='sp-revision-source';source.textContent='Sources : ';
    for(const page of current.source_pages||[]){const a=document.createElement('a');a.href=`${current.pdf_url||data.course.pdf_url}#page=${page}`;a.textContent=`p. ${page} `;a.target='_blank';a.rel='noopener';source.append(a);}container.append(source);
    $('revision-card-hidden').hidden=true;container.hidden=false;$('revision-rating').hidden=false;
    window.MathJax?.startup?.promise.then(()=>window.MathJax.typesetPromise([container])).catch(()=>{});
  }
  function rate(rating) {
    if(!revealed||tutor?.isBusy())return;
    StudyProgress.mark(data.course.course_id,current.card_id,rating);completed.push({...current,rating});
    attempts[current.card_id]=(attempts[current.card_id]||0)+1;
    if($('revision-mode').value!=='free'&&rating!=='mastered'&&attempts[current.card_id]<2&&clock.remaining>current.seconds+180) {
      queue.splice(Math.min(1,queue.length),0,{...current,reason:'Revenir sur la difficulté après une autre notion'});
      // Retirer une activité tardive si le retour sur une difficulté ne rentre plus.
      while(queue.length>1&&queue.reduce((n,c)=>n+c.seconds,0)>clock.remaining-plan.reviewSeconds)plan.omitted.push({...queue.pop(),reason:'Reportée pour retravailler une difficulté'});
    }
    nextCard();
  }
  function tick() {
    if(!running)return;const now=Date.now();const delta=Math.min(Math.max(0,clock.remaining-plan.reviewSeconds),Math.max(0,(now-clock.last)/1000));
    clock.remaining=StudyPlan.remaining(clock,now);clock.last=now;
    if(!clock.paused){
      if(pomodoro==='off'){focusTime+=delta;phaseLeft=Math.max(0,phaseLeft-delta);}
      else{const next=StudyPlan.advance(phase,phaseLeft,delta,Number(pomodoro)*60,Number(pomodoro)===50?600:300);phase=next.phase;phaseLeft=next.left;focusTime+=next.worked;}
    }
    if(clock.remaining<=plan.reviewSeconds){finish('Le temps d’activités est écoulé : place au bilan.');return;}
    renderClock();
    if(now-lastSave>5000){lastSave=now;saveCheckpoint();}
  }
  function renderClock() {text('session-phase-label',clock.paused?'En pause':phase==='focus'?'Focus':'Pause prévue');text('session-phase-time',format(Math.min(phaseLeft,clock.remaining)));text('session-work-time',format(clock.remaining));$('session-progress-bar').style.width=`${Math.min(100,(initialSeconds-clock.remaining)/initialSeconds*100)}%`;}
  function finish(message='Session arrêtée à ta demande.') {
    if(!running)return;running=false;clearInterval(timer);session.hidden=dock.hidden=true;summary.hidden=false;
    try{localStorage.removeItem(checkpointKey);}catch{}
    const ids=new Set(completed.map(c=>c.card_id));const left=[...plan.omitted,...skipped,...(current&&!ids.has(current.card_id)?[current]:[]),...queue];
    const unique=[...new Map(left.filter(c=>!ids.has(c.card_id)).map(c=>[c.card_id,c])).values()];
    text('summary-description',message+' Les résultats concernent les activités réalisées, pas tout le cours.');
    text('summary-time',`${Math.round(focusTime/60)} min`);text('summary-seen',ids.size);
    text('summary-mastered',completed.filter(c=>c.rating==='mastered').length);text('summary-review',completed.filter(c=>c.rating==='review').length);
    list($('summary-omitted'),unique,c=>c.reason||'À reprendre');
    text('summary-next',unique.length?`Prochain pas : ${unique[0].title}.`:'Tu peux maintenant essayer un exercice sur une notion abordée.');
    try{const key='studypilot.revision.sessions.v1';let logs=JSON.parse(localStorage.getItem(key)||'[]');if(!Array.isArray(logs))logs=[];
      logs.push({course_id:data.course.course_id,course_title:data.course.title,mode:$('revision-mode').value,planned_work_minutes:initialSeconds/60,worked_seconds:Math.floor(focusTime),cards_seen:ids.size,mastered:completed.filter(c=>c.rating==='mastered').length,review:completed.filter(c=>c.rating==='review').length,ended_at:new Date().toISOString()});localStorage.setItem(key,JSON.stringify(logs.slice(-100)));}catch{}
    summary.scrollIntoView({behavior:'smooth',block:'start'});
  }
  courseSelect.addEventListener('change',loadCourse);partSelect.addEventListener('change',updateCards);
  document.querySelectorAll('[data-duration]').forEach(b=>b.onclick=()=>{duration=Number(b.dataset.duration);$('revision-custom-duration').value='';document.querySelectorAll('[data-duration]').forEach(x=>x.classList.toggle('active',x===b));invalidate();});
  document.querySelectorAll('[data-pomodoro]').forEach(b=>b.onclick=()=>{pomodoro=b.dataset.pomodoro;document.querySelectorAll('[data-pomodoro]').forEach(x=>x.classList.toggle('active',x===b));invalidate();});
  setup.addEventListener('input',event=>{if(!event.target.closest('#revision-plan'))invalidate();});
  $('revision-clock').onchange=()=>{$('deadline-field').hidden=$('revision-clock').value!=='deadline';};
  $('revision-start').onclick=prepare;$('revision-launch').onclick=launch;$('revision-reveal').onclick=reveal;
  document.querySelectorAll('[data-rating]').forEach(b=>b.onclick=()=>rate(b.dataset.rating));
  document.querySelectorAll('[data-revision-action]').forEach(b=>b.onclick=()=>{tutor.select(current.card_id,current.title,b.dataset.revisionAction,{partNumber:current.part_number});tutor.reveal();});
  $('session-recall').onclick=()=>{$('recall-field').hidden=false;$('revision-card-content').hidden=true;$('revision-rating').hidden=true;$('revision-recall').focus();};
  $('revision-check-recall').onclick=()=>{const value=$('revision-recall').value.trim();if(value)tutor.ask('question',`Vérifie mon rappel de cette notion, sans supposer qu’il est faux : ${value}`.slice(0,1000));};
  $('session-skip').onclick=()=>{if(tutor?.isBusy())return;skipped.push(current);nextCard();};
  $('session-replan').onclick=()=>{$('session-adjust').hidden=!$('session-adjust').hidden;};
  $('session-apply-time').onclick=async()=>{
    if(tutor?.isBusy())return;const minutes=Number($('session-new-minutes').value);if(!Number.isFinite(minutes)||minutes<5||minutes>480)return;
    const button=$('session-apply-time');button.disabled=true;
    try{
    const response=await fetch(`/api/revision?course_id=${encodeURIComponent(data.course.course_id)}`);const updated=await response.json();
    if(!response.ok)throw Error(updated.error||'Actualisation indisponible.');if(!running)return;
    data=updated;materialVersion=data.revision;cards=data.cards.filter(c=>!partSelect.value||String(c.part_number)===partSelect.value);
    const used=new Set(completed.map(c=>c.card_id));const pool=cards.filter(c=>!used.has(c.card_id)||StudyProgress.get(c.card_id).status==='review');
    plan=StudyPlan.build(pool,options(minutes*60),progress());queue=[...plan.items];clock.remaining=minutes*60;if(clock.deadline)clock.deadline=Date.now()+minutes*60000;clock.last=Date.now();initialSeconds=minutes*60;$('session-adjust').hidden=true;nextCard();renderClock();
    }catch(e){text('session-guidance',e.message);}finally{button.disabled=false;}
  };
  $('session-pause').onclick=()=>{tick();if(!running)return;clock.paused=!clock.paused;clock.last=Date.now();text('session-pause',clock.paused?'Reprendre':'Pause');renderClock();};
  $('session-end').onclick=()=>finish();$('summary-restart').onclick=()=>{summary.hidden=true;setup.hidden=false;invalidate();loadCourse();};
  // Une modification documentaire pendant la session demande un rechargement explicite.
  window.addEventListener('focus',async()=>{if(!running)return;try{const response=await fetch(`/api/revision?course_id=${encodeURIComponent(data.course.course_id)}`);const value=await response.json();if(response.ok&&value.revision!==materialVersion)text('session-guidance','Les documents ont changé. Termine cette étape puis prépare à nouveau le parcours pour intégrer les nouveautés.');}catch{}});
  window.addEventListener('pagehide',saveCheckpoint);
  $('session-discard-button').onclick=()=>{try{localStorage.removeItem(checkpointKey);}catch{}checkpoint=null;$('session-resume').hidden=true;};
  $('session-resume-button').onclick=()=>{
    if(!checkpoint||tutor?.isBusy())return;
    const saved=checkpoint;const byId=new Map(data.cards.map(c=>[c.card_id,c]));
    pomodoro=saved.pomodoro;
    const changed=saved.revision!==data.revision;
    if(!changed&&!byId.has(saved.current)){text('revision-setup-error','La notion enregistrée a changé. Prépare un nouveau parcours.');return;}
    $('revision-mode').value=saved.mode;$('revision-level').value=saved.level;$('revision-goal').value=saved.goal;$('revision-notes').value=saved.notes||'';partSelect.value=saved.part;updateCards();
    plan=saved.plan;queue=[saved.current,...saved.queue].filter(id=>byId.has(id)).map(id=>({...byId.get(id),...saved.plan.items.find(c=>c.card_id===id)}));
    if(changed){
      const used=new Set(saved.completed.map(c=>c.card_id));const seconds=saved.clock.deadline?Math.max(0,(saved.clock.deadline-Date.now())/1000):saved.clock.remaining;
      plan=StudyPlan.build(cards.filter(c=>!used.has(c.card_id)||StudyProgress.get(c.card_id).status==='review'),options(seconds),progress());queue=[...plan.items];
    }
    completed=saved.completed;skipped=saved.skipped;attempts=saved.attempts;focusTime=saved.focusTime;phase=saved.phase;phaseLeft=saved.phaseLeft;pomodoro=saved.pomodoro;initialSeconds=saved.initialSeconds;
    materialVersion=data.revision;clock={...saved.clock,paused:true,last:Date.now()};running=true;setup.hidden=summary.hidden=true;session.hidden=dock.hidden=false;
    text('session-course-name',data.course.title);text('session-part-name',partSelect.selectedOptions[0].textContent);text('session-pause','Reprendre');
    current=null;if(!queue.length){finish('Le budget restant ne permet pas une activité complète après cette mise à jour.');return;}
    nextCard();if(!changed&&saved.recall){$('recall-field').hidden=false;$('revision-recall').value=saved.recall;}tick();renderClock();clearInterval(timer);if(running)timer=setInterval(tick,1000);
  };
  const params=new URLSearchParams(location.search);if(params.get('mode')==='express')$('revision-mode').value='express';
  const initial=params.get('course_id');if([...courseSelect.options].some(o=>o.value===initial))courseSelect.value=initial;
  loadCourse();
});
