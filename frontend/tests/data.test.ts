import { test } from 'node:test';
import assert from 'node:assert/strict';
import { liveSensor, type EdgeDevice } from '../src/data.ts';

const current = (): EdgeDevice => ({ device_id: 'uno', data_status: 'current', quality: 'good', expires_at: Date.now() / 1000 + 30, valid: { rain_percent: 0, rain_raw: 1023, rain_state: 'DRY', soil_percent: 63, soil_state: 'OK' } });
test('零读数是有效数据，土壤 OK 状态保留', () => {
  assert.equal(liveSensor(current(), 'rain', true).value, 0);
  assert.equal(liveSensor(current(), 'soil', true).state, 'OK');
});
test('离线、过期和缺失数据不显示缓存读数', () => {
  for (const device of [undefined, {...current(), expires_at: 1}, {...current(), data_status: 'stale'}]) {
    assert.equal(liveSensor(device, 'rain', true).value, null);
    assert.equal(liveSensor(device, 'rain', true).state, 'UNKNOWN');
  }
  assert.equal(liveSensor(current(), 'rain', false).value, null);
});
