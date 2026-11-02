export function withParams(pathname: string, current: string, changes: Record<string, string | null>): string {
  const next = new URLSearchParams(current);
  for (const [key, value] of Object.entries(changes)) {
    if (value === null || value === "") next.delete(key);
    else next.set(key, value);
  }
  const query = next.toString();
  return query ? `${pathname}?${query}` : pathname;
}

export function pickParam<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return allowed.find((option) => option === value) ?? fallback;
}
