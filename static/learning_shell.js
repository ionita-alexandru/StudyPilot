'use strict';
(() => {
  const toggle = document.querySelector('#menu-toggle');
  const closeButton = document.querySelector('#menu-close');
  const sidebar = document.querySelector('#learning-sidebar');
  const backdrop = document.querySelector('#menu-backdrop');
  const topbar = document.querySelector('.learning-topbar');
  const skip = document.querySelector('.skip-link');
  const main = document.querySelector('.learning-main');
  const dock = document.querySelector('.learning-dock');
  const mobile = matchMedia('(max-width: 760px)');

  document.addEventListener('learning-course', ({detail}) => {
    const path = `/course/${encodeURIComponent(detail.courseId)}`;
    const courseContext = document.querySelector('[data-course-context]');
    courseContext.textContent = courseContext.title = detail.title;
    courseContext.href = path;
    document.querySelector('[data-course-title]').textContent = detail.title;
    document.querySelectorAll('.sidebar-course, [data-course-navigation], [data-course-context], [data-course-notions], [data-course-session]').forEach(el => el.hidden = !detail.courseId);
    sidebar.querySelectorAll('[data-course-nav]').forEach(link => link.href = `${path}#${link.dataset.courseNav}`);
    document.querySelector('[data-course-notions]').href = `${path}#notions`;
    sidebar.querySelector('[data-course-session]').href = `/revision?course_id=${encodeURIComponent(detail.courseId)}`;
  });

  let open = !mobile.matches;
  function updateMenu() {
    const drawerOpen = open && mobile.matches;
    sidebar.hidden = !open;
    if (drawerOpen) {
      sidebar.setAttribute('role', 'dialog');
      sidebar.setAttribute('aria-modal', 'true');
    } else {
      sidebar.removeAttribute('role');
      sidebar.removeAttribute('aria-modal');
    }
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Masquer le menu' : 'Afficher le menu');
    document.body.classList.toggle('sidebar-collapsed', !open);
    document.body.classList.toggle('mobile-menu-open', drawerOpen);
    backdrop.hidden = !drawerOpen;
    for (const region of [skip, topbar, main, dock]) {
      if (region) region.inert = drawerOpen;
    }
  }

  function closeMenu() {
    open = false;
    updateMenu();
    toggle.focus({preventScroll:true});
  }

  toggle.addEventListener('click', () => {
    open = !open;
    updateMenu();
    if (open && mobile.matches) closeButton.focus({preventScroll:true});
  });
  closeButton.addEventListener('click', closeMenu);
  backdrop.addEventListener('click', closeMenu);

  sidebar.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || !mobile.matches || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    closeMenu();
    const url = new URL(link.href);
    if (url.origin !== location.origin || url.pathname !== location.pathname || !link.dataset.courseNav) return;
    function focusPanel() {
      const panel = document.getElementById(link.dataset.courseNav);
      const heading = panel && !panel.hidden && document.getElementById(panel.getAttribute('aria-labelledby'));
      if (!heading) return;
      heading.setAttribute('tabindex', '-1');
      heading.focus({preventScroll:true});
    }
    if (url.hash === location.hash) requestAnimationFrame(focusPanel);
    else window.addEventListener('hashchange', focusPanel, {once:true});
  });

  document.addEventListener('keydown', event => {
    if (open && mobile.matches) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeMenu();
      }
      if (event.key === 'Tab') {
        const targets = [...sidebar.querySelectorAll('a[href], button:not([disabled])')].filter(el => el.getClientRects().length);
        const index = targets.indexOf(document.activeElement);
        if (event.shiftKey && index <= 0) {
          event.preventDefault();
          targets.at(-1)?.focus();
        } else if (!event.shiftKey && (index === targets.length - 1 || index === -1)) {
          event.preventDefault();
          targets[0]?.focus();
        }
      }
      return;
    }
    if (event.key === 'Escape' && dock?.contains(event.target)) {
      const discussion = dock.querySelector('.tutor-discussion-toggle[aria-expanded="true"]');
      if (discussion) {
        event.preventDefault();
        discussion.click();
        discussion.focus({preventScroll:true});
      }
    }
  });

  mobile.addEventListener('change', () => {
    const focusInSidebar = sidebar.contains(document.activeElement);
    const closeButtonFocused = document.activeElement === closeButton;
    open = !mobile.matches;
    updateMenu();
    if ((mobile.matches && focusInSidebar) || closeButtonFocused) toggle.focus({preventScroll:true});
    updateKeyboardInset();
  });
  updateMenu();

  // Some mobile browsers resize only the visual viewport for the on-screen keyboard.
  const viewport = window.visualViewport;
  function updateKeyboardInset() {
    const editing = mobile.matches && viewport?.scale === 1 && document.activeElement?.matches('.tutor textarea');
    const inset = editing ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop) : 0;
    const style = document.documentElement.style;
    style.setProperty('--learning-keyboard-inset', `${inset}px`);
    if (editing) style.setProperty('--learning-visible-height', `${viewport.height}px`);
    else style.removeProperty('--learning-visible-height');
  }
  viewport?.addEventListener('resize', updateKeyboardInset);
  viewport?.addEventListener('scroll', updateKeyboardInset);
  document.addEventListener('focusin', updateKeyboardInset);
  document.addEventListener('focusout', () => requestAnimationFrame(updateKeyboardInset));
})();
