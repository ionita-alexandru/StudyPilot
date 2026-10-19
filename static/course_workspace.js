'use strict';
(() => {
  const workspace = document.querySelector('#course-workspace');
  if (!workspace) return;
  const courseId = workspace.dataset.course;
  const notions = [...workspace.querySelectorAll('[data-notion]')];
  const links = notions.map(item => item.querySelector('a'));
  const tutorHost = document.querySelector('#course-tutor');
  tutorHost.innerHTML = StudyChat.markup();
  const tutor = StudyChat.mount(tutorHost, {docked:true, courseId, partNumber:tutorHost.dataset.part, pdfUrl:tutorHost.dataset.pdf});
  tutorHost.querySelector('[data-chat-subject]').textContent = tutorHost.dataset.title;
  document.querySelector('#open-course-chat').onclick = () => tutor.reveal();

  function refreshProgress() {
    workspace.querySelectorAll('[data-progress-id]').forEach(el => el.textContent = StudyProgress.label(el.dataset.progressId));
    const records = notions.map(item => ({item, record:StudyProgress.get(item.dataset.notion)}));
    document.querySelector('#progress-seen').textContent = records.filter(x => x.record.status).length;
    document.querySelector('#progress-practice').textContent = records.filter(x => x.record.assessment?.status === 'correct').length;
    document.querySelector('#progress-review').textContent = records.filter(x => x.record.status === 'review').length;
    const list = document.querySelector('#progress-list'); list.replaceChildren();
    for (const {item, record} of records.filter(x => x.record.status)) {
      const row = document.createElement('li');
      const link = item.querySelector('a').cloneNode(true);
      const status = document.createElement('small'); status.textContent = StudyProgress.label(item.dataset.notion);
      row.append(link, status); list.append(row);
    }
    if (!list.children.length) {
      const empty = document.createElement('li'); empty.textContent = 'Commence par une notion ou un exercice : tes premiers repères apparaîtront ici.'; list.append(empty);
    }
    const last = StudyProgress.last();
    let resume;
    if (last?.courseId === courseId && typeof last.url === 'string') {
      try {
        const url = new URL(last.url, location.origin);
        resume = url.origin === location.origin && links.find(link => link.href === url.href);
      } catch { /* Une ancienne URL invalide ne doit pas bloquer le parcours. */ }
    }
    const button = document.querySelector('#continue-learning');
    if (button && resume) {
      button.href = resume.href; button.textContent = 'Reprendre : ' + resume.textContent;
      document.querySelector('#next-description').textContent = 'Retrouve ta dernière notion et poursuis avec une explication ou un exercice.';
    }
  }
  refreshProgress();
  window.addEventListener('study-progress', refreshProgress);
  window.addEventListener('storage', refreshProgress);

  function showPanel() {
    const key = location.hash.slice(1);
    const selected = ['documents','progression'].includes(key) ? key : 'apprendre';
    workspace.querySelectorAll('[data-course-panel]').forEach(panel => panel.hidden = panel.id !== selected);
    document.querySelectorAll('[data-course-nav]').forEach(link => {
      if (link.dataset.courseNav === selected) link.setAttribute('aria-current','page');
      else link.removeAttribute('aria-current');
    });
    if (key === 'notions') document.querySelector('#notions').open = true;
  }
  showPanel(); window.addEventListener('hashchange', showPanel);
  const normalize = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const chapters = [...workspace.querySelectorAll('[data-chapter]')];
  let previousOpen = null;
  document.querySelector('#notion-search').addEventListener('input', event => {
    const query = normalize(event.target.value.trim());
    if (query && !previousOpen) previousOpen = chapters.map(chapter => chapter.open);
    let count = 0;
    for (const item of notions) {
      item.hidden = !normalize(item.dataset.search).includes(query);
      if (!item.hidden) count++;
    }
    chapters.forEach((chapter, index) => {
      chapter.hidden = !!query && ![...chapter.querySelectorAll('[data-notion]')].some(item => !item.hidden);
      if (query) chapter.open = !chapter.hidden;
      else if (previousOpen) chapter.open = previousOpen[index];
    });
    if (!query) previousOpen = null;
    document.querySelector('#search-count').textContent = query ? `${count} notion${count === 1 ? '' : 's'} trouvée${count === 1 ? '' : 's'}` : '';
  });
})();
