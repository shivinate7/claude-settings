import assert from 'node:assert/strict';
import { test } from 'node:test';
import { homeTitle } from './home';

test('the home title counts no notes at first', () => {
  assert.equal(homeTitle(), 'Notes: 0');
});
