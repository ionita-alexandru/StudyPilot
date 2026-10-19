/* Planification locale : budget contrôlé, prérequis avant application, sans appel IA. */
(function(root) {
  'use strict';
  function build(cards, options = {}, progress = {}) {
    const seconds = Math.max(0, Math.floor(Number(options.seconds) || 0));
    const mode = options.mode || 'guided', level = options.level || 'some';
    const goal = options.goal || 'understand';
    const all = cards.filter(c => c && c.card_id);
    const known = id => ['passed', 'understood'].includes(progress[id]?.status);
    const byId = new Map(all.map(c => [c.card_id, c]));
    const prerequisiteUse = new Map();
    all.forEach(c => (c.prerequisite_ids || []).forEach(id => prerequisiteUse.set(id, (prerequisiteUse.get(id) || 0) + 1)));
    const rank = c => (progress[c.card_id]?.status === 'review' ? 30 : 0)
      + (known(c.card_id) ? -15 : 8) + (prerequisiteUse.get(c.card_id) || 0) * 3
      + (options.notes && String(options.notes).length > 2 && c.title.toLocaleLowerCase().includes(String(options.notes).toLocaleLowerCase()) ? 10 : 0);
    // Un débutant suit les bases dans l'ordre du cours, même après une réussite isolée.
    const candidates = mode === 'free' || level === 'new' ? all
      : mode === 'guided' ? [...all.filter(c=>progress[c.card_id]?.status==='review'),...all.filter(c=>progress[c.card_id]?.status!=='review')]
      : all.map((c,i) => ({c,i})).sort((a,b) => rank(b.c)-rank(a.c)||a.i-b.i).map(x=>x.c);
    const reserve = Math.min(seconds, seconds >= 600 ? 120 : 30);
    const focus = Number(options.pomodoro) * 60 || 0;
    const breakLength = focus === 3000 ? 600 : focus ? 300 : 0;
    let budget = Math.max(0, seconds - reserve);
    // Chaque pause annoncée compte dans le temps disponible.
    let breakSeconds=0;
    if (focus) {
      const cycles=Math.floor(budget/(focus+breakLength)), tail=budget%(focus+breakLength);
      breakSeconds=cycles*breakLength+Math.max(0,tail-focus);
      budget-=breakSeconds;
    }
    const ordered = [], visited = new Set(), visiting = new Set(), warnings = new Set();
    if(all.some(c=>(c.prerequisite_ids||[]).some(id=>!byId.has(id)&&!known(id))))warnings.add('Certains prérequis sont hors du périmètre choisi ; consulte-les avant de poursuivre si nécessaire.');
    function visit(c) {
      if (visited.has(c.card_id)) return;
      if (visiting.has(c.card_id)) {warnings.add('Certains prérequis forment un cycle : vérifie les notions signalées.'); return;}
      visiting.add(c.card_id);
      for (const id of c.prerequisite_ids || []) if (byId.has(id) && (!known(id) || level === 'new')) visit(byId.get(id));
      visiting.delete(c.card_id); visited.add(c.card_id); ordered.push(c);
    }
    candidates.forEach(visit);
    const selected = [], omitted = [];
    let spent = 0;
    for (const card of ordered) {
      const status = progress[card.card_id]?.status;
      let cost = mode === 'free' ? 240 : level === 'new' ? 600 : level === 'solid' ? 300 : 420;
      if (known(card.card_id) && level !== 'new') cost = Math.max(180, cost - 120);
      if (status === 'review') cost += 120;
      if (goal === 'practice') cost += 120;
      const missing = (card.prerequisite_ids || []).some(id => byId.has(id) && !known(id) && !selected.some(x => x.card_id === id));
      if (spent + cost > budget || missing) {omitted.push({...card, reason:missing?'Prérequis à travailler d’abord':'Temps disponible insuffisant'}); continue;}
      selected.push({...card, seconds:cost, reason:level==='new'?'Construire les bases':status === 'review'?'Difficulté repérée':prerequisiteUse.get(card.card_id)?'Base utile pour la suite':known(card.card_id)?'Consolider par le rappel':'À découvrir',
        stages:goal === 'practice'?['Rappeler', 'Appliquer', 'Vérifier']:goal==='consolidate'?['Rappeler sans regarder','Comparer au cours','Se tester']:['Comprendre', 'Rappeler sans regarder', 'Appliquer']});
      spent += cost;
    }
    return {items:selected, omitted, seconds, activitySeconds:spent, breakSeconds,
      reviewSeconds:reserve, spareSeconds:Math.max(0, budget-spent), warnings:[...warnings], mode, level, goal};
  }
  function remaining(clock, now) {
    if (clock.deadline) return Math.max(0, (clock.deadline-now)/1000);
    return Math.max(0, clock.remaining-(clock.paused?0:Math.max(0,now-clock.last)/1000));
  }
  function advance(phase,left,elapsed,focus,rest) {
    let worked=0;
    while(elapsed>0) {
      const take=Math.min(left,elapsed);if(phase==='focus')worked+=take;left-=take;elapsed-=take;
      if(left<=0){phase=phase==='focus'?'break':'focus';left=phase==='focus'?focus:rest;}
      if(left<=0)break;
    }
    return {phase,left,worked};
  }
  const api = {build, remaining,advance};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.StudyPlan = api;
})(typeof window === 'undefined' ? {} : window);
