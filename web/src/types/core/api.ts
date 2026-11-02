export type RequestResult<T> = { ok: true; data: T } | { ok: false; status: number | null; error: string };
