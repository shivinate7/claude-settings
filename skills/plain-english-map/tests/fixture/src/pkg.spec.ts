import assert from 'node:assert/strict';
import { test } from 'node:test';
import { homeTitle } from './pkg';

test('the package gives the home title', () => {
  assert.equal(homeTitle(), 'Notes: 0');
});
