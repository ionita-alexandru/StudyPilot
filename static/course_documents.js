/* Les PDF restent locaux ; l’analyse réutilise la file d’import commune. */
'use strict';
(() => {
  const section=document.getElementById('complement-section');if(!section)return;
  const form=document.getElementById('complement-form'),list=document.getElementById('complement-list'),status=document.getElementById('complement-status');
  const endpoint=`/api/course/${encodeURIComponent(section.dataset.course)}/documents`;
  const roles={td:'TD',exam:'Annale',correction:'Corrigé',article:'Article',course:'Complément de cours'};
  const scopes={required:'À apprendre',practice:'Entraînement',optional:'Approfondissement'};
  const labels={queued:'En attente',processing:'Préparation en cours',ready:'Prêt',partial:'À compléter',interrupted:'À reprendre',error:'À reprendre'};
  let timer=null,revision=null;
  function select(values,value){const el=document.createElement('select');for(const [key,label] of Object.entries(values))el.append(new Option(label,key));el.value=value;return el;}
  async function mutate(item,method,payload){
    status.textContent='Mise à jour…';
    try{const response=await fetch(`/api/course/${encodeURIComponent(section.dataset.course)}/document/${item.id}`,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload||{})});const data=await response.json();if(!response.ok)throw Error(data.error);status.textContent='Document mis à jour. Prépare à nouveau ta révision pour intégrer ce changement.';await refresh();}catch(e){status.textContent=e.message;}
  }
  function render(items){
    list.replaceChildren();
    for(const item of items){
      const article=document.createElement('article');article.className='document-row';
      const title=document.createElement('h4');title.textContent=item.title;
      const detail=document.createElement('p');detail.className='muted';detail.textContent=`${item.role_label} · ${item.page_count} pages · ${labels[item.status]||item.status} · ${item.completed_batches||0}/${item.total_batches||'?'} lots`;
      const actions=document.createElement('div');actions.className='study-actions';
      const pdf=document.createElement('a');pdf.href=item.pdf_url;pdf.target='_blank';pdf.rel='noopener';pdf.textContent='PDF ↗';actions.append(pdf);
      const view=document.createElement('a');view.href=`/course/${encodeURIComponent(section.dataset.course)}/document/${item.id}`;view.textContent='Voir les contenus';actions.append(view);
      if(['partial','interrupted','error'].includes(item.status)){const retry=document.createElement('button');retry.type='button';retry.textContent='Reprendre la préparation';retry.onclick=()=>{retry.disabled=true;mutate(item,'POST');};actions.append(retry);}
      const settings=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Rôle et place dans la révision';settings.append(summary);
      const r=select(roles,item.role),s=select(scopes,item.scope);r.setAttribute('aria-label','Rôle de '+item.title);s.setAttribute('aria-label','Place de '+item.title);
      const save=document.createElement('button');save.type='button';save.textContent='Appliquer';save.disabled=['queued','processing'].includes(item.status);save.onclick=()=>mutate(item,'PATCH',{role:r.value,scope:s.value});settings.append(r,s,save);
      article.append(title,detail,actions,settings);if(item.error){const p=document.createElement('p');p.className='notice';p.textContent=item.error;article.append(p);}list.append(article);
    }
    if(!items.length){const p=document.createElement('p');p.className='muted';p.textContent='Tes compléments apparaîtront ici, à côté du cours principal.';list.append(p);}
  }
  async function refresh(){
    clearTimeout(timer);
    try{const response=await fetch(endpoint);const data=await response.json();if(!response.ok)throw Error(data.error);
      if(revision&&revision!==data.revision)status.textContent='Les documents ont évolué. Recharge le parcours ou prépare une nouvelle session pour intégrer les nouveautés.';
      revision=data.revision;render(data.documents);if(data.documents.some(d=>['queued','processing'].includes(d.status)))timer=setTimeout(refresh,4000);
    }catch(e){status.textContent=e.message;}
  }
  form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('[type="submit"]');button.disabled=true;status.textContent='Enregistrement du PDF…';
    try{const response=await fetch(endpoint,{method:'POST',body:new FormData(form)});const data=await response.json();if(!response.ok)throw Error(data.error);form.reset();status.textContent='PDF ajouté. Sa préparation est dans la file ; tu peux continuer à travailler.';await refresh();}catch(e){status.textContent=e.message;}finally{button.disabled=false;}};
  refresh();window.addEventListener('pagehide',()=>clearTimeout(timer));
})();
