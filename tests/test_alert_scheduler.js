// SPDX-License-Identifier: GPL-3.0-only
const fs = require('node:fs');
const assert = require('node:assert/strict');
const source = fs.readFileSync(new URL('../DaysModel.qml', `file://${__filename}`), 'utf8');
function method(name) {
    const start = source.indexOf(`    function ${name}(`);
    const open = source.indexOf('{', start);
    let depth = 1, end = open + 1;
    for (; depth; end++) { if (source[end] === '{') depth++; if (source[end] === '}') depth--; }
    return new Function('root', 'alertProcess', 'weatherProcess', 'alertTimer', 'weatherTimer', 'command', 'argument',
        `const ${name} = function ${source.slice(start + '    function '.length, end)}; return ${name}(argument);`);
}
const signals = [];
const process = {running: false, command: [], signal: n => signals.push(n)};
const weather = {running: false, signal: n => signals.push(n)};
const timer = {restart() {}};
const root = {sessionAvailable: false, alertCity: {latitude: 39, longitude: 117}, alertKey: 'city-a', alertForcePending: false,
    alertPending: false, refreshWeather: force => assert.equal(force, true)};
const call = (name, arg) => method(name)(root, process, weather, timer, timer, args => args, arg);
root.refreshAlerts = force => call('refreshAlerts', force);
call('refreshAlerts', false);
assert.equal(process.running, false);
call('applySessionState', {available: true});
assert.equal(process.running, true);
assert.ok(process.command.includes('--force'));
weather.running = true;
call('applySessionState', {available: false});
assert.deepEqual(signals, [15, 15]);
process.running = false; weather.running = false;
call('refreshAlerts', false);
assert.equal(process.running, false);
call('applySessionState', {available: true, wake: true});
assert.ok(process.command.includes('--force'));
process.running = false;
call('refreshAlerts', false);
assert.ok(!process.command.includes('--force'));
root.alertCity = null; process.running = false;
call('refreshAlerts', true);
assert.equal(process.running, false);
assert.equal(root.alertForcePending, true);
console.log('PASS: blocked sessions stop requests, resume forces refresh, unresolved locations defer requests.');
