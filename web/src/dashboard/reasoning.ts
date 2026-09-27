import { markdown } from '../agent.ts'

export interface ThinkingRound { round: number; text: string }

const MAX_THINKING = 6000

/** Keep streamed chunks intact within a round and retain the newest 6,000 characters. */
export function appendThinking(rounds: ThinkingRound[], text: string, round?: number): ThinkingRound[] {
  if (!text) return rounds
  const number = Number.isSafeInteger(round) && round! > 0 ? round! : (rounds.at(-1)?.round ?? 1)
  const last = rounds.at(-1)
  const next = last?.round === number
    ? [...rounds.slice(0, -1), { round: number, text: last.text + text }]
    : [...rounds, { round: number, text }]
  let excess = next.reduce((total, item) => total + item.text.length, 0) - MAX_THINKING
  while (excess > 0 && next.length) {
    if (next[0].text.length <= excess) {
      excess -= next[0].text.length
      next.shift()
    } else {
      next[0] = { ...next[0], text: next[0].text.slice(excess) }
      excess = 0
    }
  }
  return next
}

/** The shared Markdown parser escapes source text before adding formatting tags. Strip links for this data-only view. */
export function dashboardMarkdown(source: string): string {
  const withoutLinks = source
    .replace(/\[([^\]\n]+)\]\((?:https?:\/\/|www\.)[^\s)]+\)/gi, '$1')
    .replace(/(?:https?:\/\/|www\.)[^\s<)]+/gi, '')
  return markdown(withoutLinks).replace(/<a\b[^>]*>([\s\S]*?)<\/a>/gi, '$1')
}
