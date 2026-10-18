// Le contenu copié est le texte original, jamais le balisage de présentation.
(() => {
  function enhance(root) {
    root.querySelectorAll('.sp-card-section pre, .sp-takeaway pre').forEach(pre => {
      if (pre.querySelector('button')) return;
      const button = document.createElement('button');
      button.className = 'sp-copy-code'; button.type = 'button'; button.textContent = 'Copier';
      button.setAttribute('aria-label', 'Copier cet exemple');
      button.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(pre.querySelector('code').textContent);
          button.textContent = 'Copié';
        } catch (_) { button.textContent = 'Copie indisponible'; }
        window.setTimeout(() => { button.textContent = 'Copier'; }, 1800);
      });
      pre.append(button);
    });
  }
  enhance(document);
  const revision = document.querySelector('#revision-card-content');
  if (revision) new MutationObserver(() => enhance(revision)).observe(revision, { childList: true });
})();
