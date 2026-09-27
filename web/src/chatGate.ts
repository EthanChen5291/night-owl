/** Guards chat state across delayed thread loads, streams, tool calls, and reset. */
export class ChatGate {
  generation = 0
  navigating = true // initial thread restore
  migrating = true // initial legacy import check
  sending = false

  current(token: number): boolean {
    return token === this.generation
  }

  /** Check when React applies an update, which may be later than when an event queued it. */
  guard<T>(token: number, update: (previous: T) => T): (previous: T) => T {
    return (previous) => this.current(token) ? update(previous) : previous
  }

  navigate(): number | null {
    if (this.sending || this.migrating) return null
    this.navigating = true
    return ++this.generation
  }

  navigationDone(token: number): boolean {
    if (!this.current(token)) return false
    this.navigating = false
    return true
  }

  send(): number | null {
    if (this.sending || this.navigating || this.migrating) return null
    this.sending = true
    return ++this.generation
  }

  sendDone(token: number): boolean {
    if (!this.current(token)) return false
    this.sending = false
    return true
  }

  reset(): void {
    ++this.generation
    this.navigating = false
    this.sending = false
  }
}

/** Identity issued by the server for one answer; browser tools must continue this exact answer. */
export class ChatRequestIdentity {
  threadId: string | null
  answerId: number | null = null

  constructor(threadId: string | null) {
    this.threadId = threadId
  }

  acceptThread(id: string, answerId: number): boolean {
    if (!id || !Number.isInteger(answerId) || answerId <= 0 || (this.threadId !== null && this.threadId !== id)) return false
    if (this.answerId !== null && this.answerId !== answerId) return false
    this.threadId = id
    this.answerId = answerId
    return true
  }

  continuation(): { thread_id: string; answer_id: number } {
    if (!this.threadId || this.answerId === null) throw new Error('missing thread or answer identity for browser tools')
    return { thread_id: this.threadId, answer_id: this.answerId }
  }
}
