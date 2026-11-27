export function buildUserStorageKey(
  baseKey: string,
  userId?: number | null,
  userEmail?: string | null
): string {
  if (userId !== null && userId !== undefined && Number.isFinite(userId)) {
    return `${baseKey}_u${userId}`
  }
  if (userEmail && userEmail.trim()) {
    return `${baseKey}_e_${userEmail.trim().toLowerCase()}`
  }
  return baseKey
}
