// Tests de logique avec un DOM simulé ; ne constituent pas un test visuel.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const arrival = fs.readFileSync(path.join(__dirname, '../static/entrance.js'), 'utf8');
function run({ reduced = false, storage = new Map(), blocked = false } = {}) {
  const classes = new Set(), events = {}, timers = [];
  const context = { document: { createElement: () => ({textContent:''}), head: {append(){}}, documentElement: { classList: { add: s => classes.add(s), remove: s => classes.delete(s) } } },
    sessionStorage: { getItem: k => { if (blocked) throw Error('refus'); return storage.get(k); }, setItem: (k,v) => storage.set(k,v) },
    setTimeout: (f,ms) => timers.push({f,ms}),
    window: { matchMedia: () => ({matches:reduced}), addEventListener: (k,v) => events[k] = v } };
  vm.runInNewContext(arrival, context);
  return { classes, events, timers };
}
test('arrival appears once and releases its class without layout timer blocking', () => {
  const storage = new Map(), first = run({storage});
  assert.equal(first.classes.has('sp-enter156'), true);
  first.events.DOMContentLoaded();
  assert.ok(first.timers[0].ms > 0 && first.timers[0].ms <= 1000);
  first.timers[0].f();
  assert.equal(first.classes.size, 0);
  assert.equal(run({storage}).classes.size, 0);
});
test('reduced motion does not add an animation or timer', () => {
  const state = run({reduced:true});
  assert.equal(state.classes.size, 0);
  assert.equal(state.timers.length, 0);
});
test('unavailable storage never blocks the page', () => {
  const state = run({blocked:true});
  state.events.DOMContentLoaded();
  state.timers[0].f();
  assert.equal(state.classes.size, 0);
});
test('code copy uses the original content, preserves whitespace, and enhances once', async () => {
  const code = '    def calcul(x):\n        return x ** 2';
  let button, copied, writes = 0;
  const pre = { querySelector: s => s === 'button' ? button : {textContent:code}, append: b => {button=b; writes++;} };
  const document = {querySelectorAll: () => [pre], querySelector: () => null,
    createElement: () => ({setAttribute(){}, addEventListener(_event, fn){this.click=fn;}})};
  const context = {document, navigator:{clipboard:{writeText: async v => {copied=v;}}}, window:{setTimeout(){}}};
  const script = fs.readFileSync(path.join(__dirname, '../static/cards.js'), 'utf8');
  vm.runInNewContext(script, context);
  vm.runInNewContext(script, context);
  assert.equal(writes, 1);
  await button.click();
  assert.equal(copied, code);
  assert.equal(button.textContent, 'Copié');
});

test('an interrupted import survives reload and resumes before opening the finished course', async () => {
  const script = fs.readFileSync(path.join(__dirname, '../static/upload.js'), 'utf8');
  for (const initial of ['interrupted', 'partial', 'error']) {
    const elements = new Map(), storage = new Map(), requests = [], navigations = [];
    const job = 'a'.repeat(32), statusUrl = '/api/upload/status/' + job;
    const resumeUrl = '/api/upload/resume/' + job;
    for (const id of ['upload-form','pdf-file','upload-submit','selected-filename','upload-progress',
      'upload-status-title','upload-status-detail','upload-error','upload-resume','upload-open']) {
      elements.set(id, {hidden:true, disabled:false, files:[], handlers:{},
        addEventListener(event, action) {this.handlers[event] = action;}});
    }
    const replies = [
      {status:initial, resume_url:resumeUrl, course_url:'/course/example'},
      {status_url:statusUrl},
      {status:'processing', current_state:'fiches: en cours', done:0, total:1},
      {status:'ready', course_url:'/course/example'},
    ];
    vm.runInNewContext(script, {
      document:{getElementById:id => elements.get(id)},
      location:{search:'?job_id='+job}, history:{replaceState(){}}, URLSearchParams,
      localStorage:{getItem:k=>storage.get(k), setItem:(k,v)=>storage.set(k,v), removeItem:k=>storage.delete(k)},
      window:{location:{assign:url=>navigations.push(url)}},
      setTimeout:fn=>fn(),
      fetch:async (url, options) => {requests.push([url,options?.method || 'GET']); return {ok:true,json:async()=>replies.shift()};},
    });
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(navigations, [], initial);
    assert.equal(elements.get('upload-resume').hidden, false, initial);
    assert.equal(elements.get('upload-open').hidden, false, initial);
    await elements.get('upload-resume').handlers.click();
    assert.deepEqual(requests, [[statusUrl,'GET'],[resumeUrl,'POST'],[statusUrl,'GET'],[statusUrl,'GET']]);
    assert.deepEqual(navigations, ['/course/example']);
  }
});


test('shared progress migrates both screens and distinguishes assistance from self-assessment',()=>{
  const storage=new Map([
    ['studypilot-main-v155',JSON.stringify({a:'known'})],
    ['studypilot.revision.progress.v1',JSON.stringify({course:{b:{rating:'review',seen:3}}})]
  ]);
  const context={window:{dispatchEvent(){}},Event:class{},localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/study_progress.js'),'utf8'),context);
  const progress=context.window.StudyProgress;
  assert.equal(progress.get('a').status,'understood');assert.equal(progress.get('b').seen,3);
  progress.assess('course','a',{status:'correct',basis:'local_calculation',assisted:true},'ex1');
  assert.equal(progress.get('a').status,'assisted');assert.match(progress.label('a'),/avec aide/);
  progress.mark('course','a','understood');assert.match(progress.label('a'),/autoévaluation/);
  assert.equal(progress.get('a').assessment.exerciseId,'ex1');
  progress.clear(['a']);assert.equal(progress.get('b').status,'review');
});
