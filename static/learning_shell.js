'use strict';
(() => {
  const toggle = document.querySelector('#menu-toggle');
  const sidebar = document.querySelector('#learning-sidebar');
  const backdrop = document.querySelector('#menu-backdrop');
  const main = document.querySelector('.learning-main');
  const dock = document.querySelector('.learning-dock');
  const mobile = matchMedia('(max-width: 760px)');
  if (document.body.classList.contains('revision-workspace')) {
    sidebar.querySelectorAll('[aria-current]').forEach(link => link.removeAttribute('aria-current'));
    sidebar.querySelector('[data-course-session]').setAttribute('aria-current', 'page');
  }
  document.addEventListener('learning-course', ({detail}) => {
    const path = `/course/${encodeURIComponent(detail.courseId)}`;
    document.querySelector('[data-course-title]').textContent = detail.title;
    document.querySelectorAll('.sidebar-course, [data-course-navigation], [data-course-notions], [data-course-session]').forEach(el => el.hidden = !detail.courseId);
    sidebar.querySelectorAll('[data-course-nav]').forEach(link => link.href = `${path}#${link.dataset.courseNav}`);
    document.querySelector('[data-course-notions]').href = `${path}#notions`;
    sidebar.querySelector('[data-course-session]').href = `/revision?course_id=${encodeURIComponent(detail.courseId)}`;
  });
  let open = !mobile.matches;
  function update() {
    sidebar.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Masquer le menu' : 'Afficher le menu');
    document.body.classList.toggle('sidebar-collapsed', !open);
    document.body.classList.toggle('mobile-menu-open', open && mobile.matches);
    backdrop.hidden = !(open && mobile.matches);
    main.inert = open && mobile.matches;
    if (dock) dock.inert = open && mobile.matches;
  }
  function close() {open = false; update(); toggle.focus();}
  toggle.onclick = () => {open = !open; update(); if(open && mobile.matches) sidebar.querySelector('a').focus();};
  backdrop.onclick = close;
  sidebar.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {if(mobile.matches) close();}));
  document.addEventListener('keydown', event => {
    if (!open || !mobile.matches) return;
    if (event.key === 'Escape') {event.preventDefault(); close();}
    if (event.key === 'Tab') {
      const targets = [toggle, ...[...sidebar.querySelectorAll('a')].filter(link => link.getClientRects().length)];
      const index = targets.indexOf(document.activeElement);
      if (event.shiftKey && index <= 0) {event.preventDefault(); targets.at(-1).focus();}
      else if (!event.shiftKey && (index === targets.length - 1 || index === -1)) {event.preventDefault(); toggle.focus();}
    }
  });
  mobile.addEventListener('change', () => {open = !mobile.matches; update();});
  update();
})();
