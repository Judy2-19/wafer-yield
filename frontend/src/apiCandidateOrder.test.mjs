import assert from 'node:assert/strict'
import test from 'node:test'

import { buildApiCandidates } from './apiCandidates.ts'

test('remote browsers try the current server before loopback addresses', () => {
  assert.deepEqual(buildApiCandidates(undefined), [
    '/api',
    'http://127.0.0.1:8000/api',
    'http://localhost:8000/api',
  ])
})

test('an explicit deployment API address stays first', () => {
  assert.equal(buildApiCandidates('https://wafer.example/api')[0], 'https://wafer.example/api')
})
