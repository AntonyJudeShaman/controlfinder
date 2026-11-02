import type { z } from "zod";
import type { RequestResult } from "@/types/core/api";

export async function sendRequest<T extends z.ZodType>(
  path: string,
  schema: T,
  init?: RequestInit,
): Promise<RequestResult<z.infer<T>>> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { cache: "no-store", ...init });
  } catch {
    return { ok: false, status: null, error: `${path}: the API did not answer. Is \`make api\` running?` };
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    return { ok: false, status: response.status, error: `${path}: HTTP ${response.status}` };
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    const where = issue ? issue.path.join(".") || "(root)" : "(root)";
    return { ok: false, status: response.status, error: `${path}: unexpected response at ${where}: ${issue?.message ?? "invalid"}` };
  }
  return { ok: true, data: parsed.data };
}

export function postJson(body: Record<string, string | number | boolean | null>): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}
