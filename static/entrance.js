// Animation d'entrée discrète, une fois par onglet ; aucun écran bloquant.
(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  try {
    if (sessionStorage.getItem('studypilot.arrival.v156')) return;
    sessionStorage.setItem('studypilot.arrival.v156', '1');
  } catch (_) {}
  const style = document.createElement('style');
  style.textContent = '@keyframes sp-arrival156{from{opacity:.35;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}.sp-enter156 .sp-home-main,.sp-enter156 .sp-chat,.sp-enter156 .sp-context,.sp-enter156 .sp-revision-setup,.sp-enter156 main{animation:sp-arrival156 .5s ease-out both}';
  document.head.append(style);
  document.documentElement.classList.add('sp-enter156');
  window.addEventListener('DOMContentLoaded',()=>setTimeout(()=>document.documentElement.classList.remove('sp-enter156'),650),{once:true});
})();
