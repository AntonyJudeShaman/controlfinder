export function displayControlId(controlId: string): string {
  const match = /^([a-z]{2})-(\d+)(?:\.(\d+))?$/.exec(controlId);
  if (!match) return controlId.toUpperCase();
  const [, family = "", base = "", enhancement] = match;
  return `${family.toUpperCase()}-${base}${enhancement ? `(${enhancement})` : ""}`;
}
