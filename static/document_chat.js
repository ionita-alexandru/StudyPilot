document.addEventListener('DOMContentLoaded',()=>{
  const host=document.getElementById('document-tutor');host.innerHTML=StudyChat.markup();
  const tutor=StudyChat.mount(host,{docked:true,courseId:host.dataset.course,partNumber:host.dataset.part,pdfUrl:host.dataset.pdf});
  host.querySelector('[data-chat-subject]').textContent=host.dataset.title;
  document.querySelectorAll('[data-document-entry]').forEach(b=>b.onclick=()=>{tutor.select(b.dataset.documentEntry,b.dataset.title);tutor.reveal();});
});
