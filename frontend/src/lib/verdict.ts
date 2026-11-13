export type VerdictBucket = 'correct' | 'partially_correct' | 'incorrect' | 'ungraded'

export function verdictBucket(value: string | null | undefined): VerdictBucket {
  const normalized = (value ?? '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  if (normalized === 'incorrect' || normalized === 'dont_know' || normalized === "don't_know") return 'incorrect'
  if (normalized === 'partially_correct' || normalized === 'partial') return 'partially_correct'
  if (normalized === 'correct') return 'correct'
  return 'ungraded'
}
