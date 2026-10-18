'use strict';
// Une seule progression pour les fiches, la découverte et les révisions.
window.StudyProgress = (() => {
  const key='studypilot.progress.v2';
  const read=k=>{try{const x=JSON.parse(localStorage.getItem(k)||'{}');return x&&typeof x==='object'&&!Array.isArray(x)?x:{};}catch{return {};}};
  function load(){const data=read(key);data.cards ||= {};return data;}
  function save(data){try{localStorage.setItem(key,JSON.stringify(data));window.dispatchEvent(new Event('study-progress'));}catch{}}
  const normalize=s=>({known:'understood',mastered:'understood',almost:'learning',review:'review'}[s]||s);
  const data=load();
  if(!data.migrated){
    for(const [id,status] of Object.entries(read('studypilot-main-v155')))if(typeof status==='string')data.cards[id]={status:normalize(status),seen:1};
    for(const [courseId,cards] of Object.entries(read('studypilot.revision.progress.v1')))for(const [id,item] of Object.entries(cards||{})) {
      const old=data.cards[id]||{}; data.cards[id]={...old,courseId,status:normalize(item.rating),seen:Math.max(old.seen||0,item.seen||0),updatedAt:item.updated_at};
    }
    data.migrated=true;save(data);
  }
  return {
    get(id){return load().cards[id]||{};},
    mark(courseId,id,status){const d=load(),old=d.cards[id]||{};d.cards[id]={...old,courseId,status:normalize(status),seen:(old.seen||0)+1,updatedAt:new Date().toISOString()};save(d);},
    assess(courseId,id,assessment,exerciseId){const d=load(),old=d.cards[id]||{};
      d.cards[id]={...old,courseId,status:assessment.status==='uncertain'?(old.status||'learning'):assessment.status==='correct'?(assessment.assisted?'assisted':'passed'):'review',
        assessment:{...assessment,exerciseId},seen:(old.seen||0)+1,updatedAt:new Date().toISOString()};save(d);},
    legacy(){return Object.fromEntries(Object.entries(load().cards).map(([id,x])=>[id,['understood','passed'].includes(x.status)?'known':x.status==='review'?'review':'']));},
    clear(ids){const d=load();for(const id of ids)delete d.cards[id];save(d);},
    label(id){const x=this.get(id);return ({read:'Lue',understood:'Comprise · autoévaluation',learning:'En cours',review:'À revoir',assisted:'Exercice réussi avec aide',passed:x.assessment?.basis==='local_calculation'?'Résultat vérifié · sans aide':'Exercice réussi · évaluation IA'})[x.status]||'À découvrir';},
    location(courseId,url){const d=load();d.last={courseId,url};save(d);},
    last(){return load().last;}
  };
})();
