/** Move saved preferences to the new name without replacing a current value. */
export function readSavedValue(key: string, legacyKey: string): string | null {
  const current = localStorage.getItem(key)
  if (current !== null) return current
  const legacy = localStorage.getItem(legacyKey)
  if (legacy !== null) {
    try {
      localStorage.setItem(key, legacy)
      localStorage.removeItem(legacyKey)
    } catch {
      // Keep reading the old value if storage is full or read-only.
    }
  }
  return legacy
}
