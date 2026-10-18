document.addEventListener('DOMContentLoaded', () => {
  const panel = document.querySelector('#chat');
  if (!panel || !window.StudyChat) return;
  panel.querySelector('#sp-chat-messages').setAttribute('data-chat-messages', '');
  panel.querySelector('#sp-chat-error').setAttribute('data-chat-error', '');
  const subject = document.createElement('p'); subject.dataset.chatSubject = '';
  subject.className = 'tutor-subject'; subject.textContent = 'Le cours';
  panel.querySelector('#sp-chat-messages').before(subject);
  const params = new URLSearchParams(location.search);
  const controller = StudyChat.mount(panel, {courseId: panel.dataset.courseId,
    partNumber: panel.dataset.partNumber, pdfUrl: panel.dataset.pdfUrl, cardId: params.get('card')});
  document.querySelectorAll('[data-study-action]').forEach(button => button.onclick = () => {
    controller.select(button.dataset.cardId, button.dataset.cardTitle, button.dataset.studyAction);
    panel.querySelector('textarea, input').focus();
  });
  if (params.get('q')) controller.ask('question', params.get('q'));
  else if (params.get('action')) controller.select(params.get('card'), '', params.get('action'));
});
