# ControlFinder web

A Next.js front end over the FastAPI service in `src/controlfinder/api`. It has five pages: controls,
configs (with live retrieval knobs), results, ask and trace. Run `make api` in one terminal and `make web` in
another, then open http://localhost:3000.

## Rules that matter here

- **No typed numbers.** Every metric, interval, count and latency on screen comes from the API, which reads
  `results/*.json` and the database. If a number is not in an API response, it does not appear.
- **Backend-driven options.** Retrievers, chunking strategies, the k range, answering systems, families and
  metric names all come from the API (`/configs`, `/families`, the results files). The only static lists are
  the navigation links and the home page blurbs.
- **Zero model calls during development.** Search runs local retrieval only. On the ask page, the dev
  questions replay from the LLM cache. A new question calls the model, so the page says so.

## How the code is laid out

This follows the React conventions in `~/.cursor/skills/react-ui-conventions`, with these Next.js adaptations:

- Page views live in `src/screens/` because Next reserves `src/pages/`. Their mirrors are `hooks/screens/`,
  `types/screens/` and `lib/screens/`.
- `app/**/page.tsx`, `app/layout.tsx` and `next.config.ts` use default exports because Next requires them.
  Each page only wraps its screen in `<Suspense>`, which `useSearchParams` needs.
- Every request goes through `sendRequest` in `src/core/api/client.ts`. It validates the response with zod
  and returns a `RequestResult` union instead of throwing, so stores and hooks never need `try`/`catch`. A
  validation error names the path of the first failing field.
- `next.config.ts` rewrites `/api/*` to the FastAPI server (`CONTROLFINDER_API_URL`, default
  `http://127.0.0.1:8000`), so the browser never talks to port 8000 directly.
- Shared server data (configs, results) lives in Zustand stores. Each screen's own state lives in a
  `useReducer` in its controller hook. Anything worth bookmarking (filters, knobs, selected IDs) lives in
  the URL.
- Responses are keyed by the request that produced them (`Keyed<T>`), so a slow, stale response never
  overwrites a newer one, and the hooks never set state synchronously inside an effect.
- Screens and components are pure views. Formatting (numbers, intervals, IDs) happens in `lib/*-helpers.ts`,
  which the hooks call.

## Style

- The brutalist theme lives in the CSS variables in `src/app/globals.css`: zero radius, black borders, a paper
  background with a grid, one yellow accent and hard offset shadows (`shadow-brutal`, `shadow-brutal-sm`).
- The look of the shadcn components is set in their variants in `src/components/ui/`, so the screens use
  `className` for layout only.
- Do not put Greek letters under `uppercase`. CSS turns τ into Τ, which reads as a T.

## Dependencies and checks

- Versions are exact and at least 14 days old: `minimumReleaseAge: 20160` (minutes) in
  `pnpm-workspace.yaml`. pnpm itself is pinned through `packageManager`.
- Before committing, run `pnpm typecheck` and `pnpm build`.
