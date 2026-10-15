// SPDX-License-Identifier: GPL-3.0-only
// Run with: node tests/test_widget_settings.js
const fs = require('node:fs');
const assert = require('node:assert/strict');
const source = fs.readFileSync(new URL('../BarWidget.qml', `file://${__filename}`), 'utf8');
const body = source.split('    function persist(values) {')[1].split('\n    ThemeUi.BarIconButton')[0].trim().replace(/\}$/, '');
const persist = new Function('root', 'panel', 'values', body);
const city = {name: '岳麓山', cityName: '长沙', kind: 'poi', latitude: 28.18001, longitude: 112.93002};
let settings = {id: 'andy.days', locationMode: 'auto', city: null};
let calls = 0;
let accept = true;
const panel = {settingsError: ''};
const root = {
    moduleName: 'andy.days',
    get settings() { return settings; },
    set settings(_) { throw Error('Must preserve the host binding'); },
    bar: {shell: {updateEntryInline(id, entry) {
        calls++;
        assert.equal(id, 'andy.days');
        if (accept) settings = entry; // Simulate the host updating its binding.
        return accept;
    }}}
};
persist(root, panel, {locationMode: 'manual', city});
assert.equal(settings.city.name, '岳麓山');
assert.equal(panel.settingsError, '');
assert.equal(calls, 1);
assert.equal(settings.city.cityName, '长沙');
assert.equal(settings.city.latitude, 28.18001);
assert.equal(settings.city.longitude, 112.93002);
panel.settingsError = 'previous error';
persist(root, panel, {locationMode: 'manual', city});
assert.equal(calls, 1); // Re-selecting the same city is successful without a write.
assert.equal(panel.settingsError, '');
accept = false;
persist(root, panel, {locationMode: 'auto', city: null});
assert.match(panel.settingsError, /保存失败/);
assert.equal(settings.city.name, '岳麓山');
accept = true;
persist(root, panel, {locationMode: 'auto', city: null});
assert.equal(settings.city, null);
assert.equal(panel.settingsError, '');
console.log('City selection, no-op, failure and automatic location checks passed.');
