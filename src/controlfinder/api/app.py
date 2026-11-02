"""The FastAPI app: thin HTTP routes over `Backend`, each input validated before it gets there.

`make api` serves it on port 8000; the web app (web/) reaches it through its own /api proxy.
`create_app` takes the function that builds the backend, so tests can hand it fake models.
"""

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from psycopg import Connection
from pydantic import BaseModel, Field

from controlfinder.api.backend import Backend
from controlfinder.index.db import connect
from controlfinder.retrieval.pipeline import CANDIDATES
from controlfinder.retrieval.production import K, STRATEGY

Retrieval = Literal["bm25", "dense", "hybrid"]
Strategy = Literal["A_control_only", "B_control_plus_enh", "C_separate"]
System = Literal["pipeline", "pipeline_base_text", "agent"]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    system: System | None = None


def found(value: dict | None) -> dict:
    if value is None:
        raise HTTPException(status_code=404, detail="not found")
    return value


def create_app(make_backend: Callable[[Connection], Backend] = Backend) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with connect(autocommit=True) as conn:
            app.state.backend = make_backend(conn)
            yield

    app = FastAPI(title="ControlFinder", lifespan=lifespan)

    def backend(request: Request) -> Backend:
        return request.app.state.backend

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/search")
    def search(request: Request, q: str = Query(min_length=1, max_length=2000), retrieval: Retrieval = "dense",
               strategy: Strategy = STRATEGY, k: int = Query(K, ge=1, le=CANDIDATES), rerank: bool = False) -> dict:
        return backend(request).search(q, retrieval, strategy, k, rerank)

    @app.post("/ask")
    def ask(request: Request, body: AskRequest) -> dict:
        return backend(request).ask(body.question, body.system)

    @app.get("/controls")
    def controls(request: Request, family: str | None = Query(None, pattern="^[A-Za-z]{2}$"),
                 q: str | None = Query(None, max_length=200), limit: int = Query(50, ge=1, le=500),
                 offset: int = Query(0, ge=0)) -> dict:
        return backend(request).list_controls(family, q, limit, offset)

    @app.get("/families")
    def families(request: Request) -> list[dict]:
        return backend(request).families()

    @app.get("/controls/{control_id}")
    def control(request: Request, control_id: str) -> dict:
        return found(backend(request).control(control_id))

    @app.get("/configs")
    def configs(request: Request) -> dict:
        return backend(request).configs()

    @app.get("/results")
    def results(request: Request) -> list[str]:
        return backend(request).results()

    @app.get("/results/{name}")
    def result(request: Request, name: str) -> dict:
        return found(backend(request).result(name))

    @app.get("/logs")
    def logs(request: Request, pipeline: str | None = Query(None, max_length=100),
             limit: int = Query(50, ge=1, le=500)) -> dict:
        return backend(request).logs(pipeline, limit)

    @app.get("/logs/{log_id}")
    def log(request: Request, log_id: int) -> dict:
        return found(backend(request).log(log_id))

    return app


app = create_app()
