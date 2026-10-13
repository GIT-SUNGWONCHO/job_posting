import { expect, it } from 'vitest'
import { bodyShard } from './load'

// tests/test_screen.py test_body_shard_matches_the_web_hash와 같은 값
it('bodyShard matches the Python hash', () => {
  expect(bodyShard('zighang:a')).toBe('04')
  expect(bodyShard('saramin:55277376')).toBe('08')
})
