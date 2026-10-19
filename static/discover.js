'use strict';
const settings=document.currentScript.dataset;
const host=document.querySelector('#discover-tutor');host.innerHTML=StudyChat.markup();
const tutor=StudyChat.mount(host,{docked:true,courseId:settings.course,cardId:settings.card,partNumber:settings.part,pdfUrl:settings.pdf});
tutor.select(settings.card,settings.title);
StudyProgress.location(settings.course,location.pathname+location.search);
if(!StudyProgress.get(settings.card).status)StudyProgress.mark(settings.course,settings.card,'read');
const refresh=()=>document.querySelector('#notion-progress').textContent=StudyProgress.label(settings.card);
refresh();window.addEventListener('study-progress',refresh);window.addEventListener('storage',refresh);
document.querySelector('#understood').onclick=()=>StudyProgress.mark(settings.course,settings.card,'understood');
document.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>{tutor.select(settings.card,settings.title,b.dataset.action);tutor.reveal();});
document.querySelectorAll('[data-prerequisite]').forEach(b=>b.onclick=()=>{tutor.ask('prerequisite',`Explique ce prérequis et son lien avec la notion : ${b.dataset.prerequisite}`);tutor.reveal();});
document.querySelector('#feedback-form').onsubmit=async event=>{
  event.preventDefault();const form=event.currentTarget,button=form.querySelector('button'),status=document.querySelector('#feedback-status');button.disabled=true;
  try{const response=await fetch('/api/study-feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({course_id:settings.course,card_id:settings.card,comment:form.elements.comment.value})});const result=await response.json();if(!response.ok)throw Error(result.error);status.textContent=result.message;form.reset();}
  catch(e){status.textContent=e.message;}finally{button.disabled=false;}
};
