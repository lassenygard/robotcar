// Exercise the real inline controller with a small DOM/transport test double.
// No browser, network requests or motor hardware are used by these tests.
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');

const source = readFileSync(join(__dirname, '../robotcar/static/index.html'), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
function controller() {
  const elements = new Map(), sent = [], requests = [];
  const canvas = new Proxy({}, {get: () => () => {}});
  const element = id => {
    if (!elements.has(id)) elements.set(id, {
      value: id === 'zoom' ? '12' : '300', dataset: {}, style: {},
      getContext: () => canvas, replaceChildren() {}, removeAttribute() {},
      getBoundingClientRect: () => ({left:0, top:0, width:700, height:700}),
    });
    return elements.get(id);
  };
  const context = vm.createContext({
    document: {getElementById:element, querySelectorAll:() => [], activeElement:{tagName:'BODY'}},
    window: {}, location: {protocol:'https:', host:'robot.test'}, performance, AbortSignal,
    Image: class {complete = true; naturalWidth = 600;},
    Option: class {},
    WebSocket: class {readyState = 1; send(data) {sent.push(JSON.parse(data));}},
    setInterval() {}, setTimeout() {}, clearTimeout() {},
    async fetch(url, options) {
      requests.push(JSON.parse(options.body));
      return {status:200, json:async () => ({ok:true})};
    },
  });
  const run = code => vm.runInContext(code, context);
  run(source);
  const show = (id, saved={}) => run(`state={map:{map_id:${JSON.stringify(id)},pose:[0,0,0],localized:true,confidence:1,revision:1},navigation:{mode:'idle',patrol:${JSON.stringify(saved)}}};render()`);
  const choose = () => {
    run('mapRequest.onload()');
    element('map').onclick({clientX:400, clientY:350});
    element('addPatrol').onclick();
  };
  const snapshot = () => JSON.parse(run('JSON.stringify({chosen,patrol,displayedMapId,mapImgId})'));
  return {run, show, choose, snapshot, element, context, requests};
}

test('same frame preserves draft; a different frame clears old target and route', () => {
  const ui = controller();
  ui.show('A'); ui.choose();
  const original = ui.snapshot();
  assert.ok(original.chosen);
  assert.equal(original.patrol.length, 1);
  ui.run("state.map.name='saved-as';state.map.revision++;render()");
  assert.deepEqual(ui.snapshot(), original);
  ui.show('B', {map_id:'A', waypoints:[[1,2]], interval_s:60});
  assert.deepEqual(ui.snapshot(), {chosen:null, patrol:[], displayedMapId:'B', mapImgId:null});
  assert.equal(ui.element('go').disabled, true);
  assert.equal(ui.element('startPatrol').disabled, true);
  assert.equal(ui.element('targetText').textContent, 'Ingen destinasjon valgt');
});

test('saved route appears only in its own frame and legacy routes stay unselected', () => {
  const ui = controller();
  ui.show('A', {waypoints:[[1,2]], interval_s:60});
  assert.deepEqual(ui.snapshot().patrol, []);
  ui.show('B', {map_id:'B', waypoints:[[2,3]], interval_s:45});
  assert.deepEqual(ui.snapshot().patrol, [[2,3]]);
  assert.equal(ui.element('patrolInterval').value, 45);
});

test('delayed image from previous map cannot replace current image or create a target', () => {
  const ui = controller();
  ui.show('A'); ui.run('const previousImage=mapRequest');
  assert.match(ui.run('mapRequest.src'), /map_id=A/);
  ui.show('B'); ui.run('previousImage.onload()');
  ui.element('map').onclick({clientX:400, clientY:350});
  assert.equal(ui.snapshot().chosen, null);
  assert.equal(ui.snapshot().mapImgId, null);
  ui.run('mapRequest.onload()');
  assert.equal(ui.snapshot().mapImgId, 'B');
});

test('go-to retains the selected frame while the stop request is in flight', async () => {
  const ui = controller();
  ui.show('A'); ui.choose();
  ui.context.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    ui.requests.push(body);
    if (body.action === 'stop') ui.show('B');
    return {status:200, json:async () => ({ok:true})};
  };
  await ui.element('go').onclick();
  const message = ui.requests.find(r => r.action === 'goto');
  assert.equal(message.map_id, 'A');
  assert.ok(message.goal);
});

test('patrol start cannot retag an old route when map changes during save', async () => {
  const ui = controller();
  ui.show('A'); ui.choose();
  ui.context.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    ui.requests.push(body);
    if (body.action === 'patrol_settings') ui.show('B');
    return {status:200, json:async () => ({ok:true})};
  };
  await ui.element('startPatrol').onclick();
  assert.equal(ui.requests.find(r => r.action === 'patrol_settings').map_id, 'A');
  assert.equal(ui.requests.find(r => r.action === 'patrol').map_id, 'A');
  assert.deepEqual(ui.snapshot().patrol, []);
});
