import assert from 'node:assert/strict'
import test from 'node:test'
import { verdictBucket } from '../src/lib/verdict.ts'

test('incorrect is never counted as correct despite its shared suffix', () => {
  assert.equal(verdictBucket('incorrect'), 'incorrect')
  assert.equal(verdictBucket('INCORRECT'), 'incorrect')
})
test('partial correctness remains separate from correct and incorrect', () => {
  for (const value of ['partially_correct', 'partially correct', 'partially-correct', 'partial']) assert.equal(verdictBucket(value), 'partially_correct')
})
test('only explicit correct verdicts count as correct', () => {
  assert.equal(verdictBucket(' correct '), 'correct')
  assert.equal(verdictBucket('not correct'), 'ungraded')
})
test('explicit missed recall remains incorrect', () => {
  assert.equal(verdictBucket('dont_know'), 'incorrect')
  assert.equal(verdictBucket("don't_know"), 'incorrect')
})
test('provider failures and unknown grades do not fabricate incorrect outcomes', () => {
  for (const value of ['grading_error', 'error', 'unknown', '', null, undefined]) assert.equal(verdictBucket(value), 'ungraded')
})
