document.addEventListener('DOMContentLoaded', () => {
  const panel = document.querySelector('#chat');
  if (!panel || !window.StudyChat) return;
  panel.innerHTML = StudyChat.markup();
  const params = new URLSearchParams(location.search);
  const controller = StudyChat.mount(panel, {docked:true, courseId:panel.dataset.courseId,
    partNumber:panel.dataset.partNumber, pdfUrl:panel.dataset.pdfUrl, cardId:params.get('card')});
  panel.querySelector('[data-chat-subject]').textContent = panel.dataset.title;
  panel.querySelector('textarea').id = 'sp-chat-question';
  document.querySelectorAll('[data-study-action]').forEach(button => button.onclick = () => {
    controller.select(button.dataset.cardId, button.dataset.cardTitle, button.dataset.studyAction);
    controller.reveal();
  });
  if (params.get('q')) controller.ask('question', params.get('q'));
  else if (params.get('action')) controller.select(params.get('card'), panel.dataset.title, params.get('action'));
  controller.reveal(false);
});
