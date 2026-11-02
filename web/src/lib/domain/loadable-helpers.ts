import type { RequestResult } from "@/types/core/api";
import type { Loadable } from "@/types/domain/loadable";

export function loading<T>(): Loadable<T> {
  return { status: "loading" };
}

export function mapLoadable<T, U>(value: Loadable<T>, map: (data: T) => U): Loadable<U> {
  return value.status === "success" ? { status: "success", data: map(value.data) } : value;
}

export function toLoadable<T>(result: RequestResult<T>): Loadable<T> {
  return result.ok ? { status: "success", data: result.data } : { status: "error", message: result.error };
}
