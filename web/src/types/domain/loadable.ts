export type Loadable<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: T };

export interface Keyed<T> {
  key: string;
  result: Loadable<T>;
}
