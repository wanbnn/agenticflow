from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.sessions import SessionMiddleware

from .catalog import NODE_CATALOG
from .engine import WorkflowEngine, validate_workflow
from .models import Edge, Node, Position, RunRequest, Workflow, WorkflowCreate
from .store import Store
from .ui import render_auth_page, render_dashboard, render_page


PACKAGE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("AGENTIC_FLOW_DATA_DIR", PACKAGE_DIR.parent / "data"))


class SetupPayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    workspace_name: str = Field(min_length=2, max_length=120)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        clean = value.strip().lower()
        if "@" not in clean or "." not in clean.rsplit("@", 1)[-1]:
            raise ValueError("Informe um e-mail válido.")
        return clean


class LoginPayload(BaseModel):
    email: str
    password: str


def sample_workflow() -> WorkflowCreate:
    return WorkflowCreate(
        name="Equipe de pesquisa",
        description="Dois agentes colaboram para produzir uma resposta revisada.",
        nodes=[
            Node(id="input-1", type="input", name="Nova solicitação", position=Position(x=80, y=230), config={"field": "message"}),
            Node(
                id="prompt-1",
                type="prompt",
                name="Preparar contexto",
                position=Position(x=360, y=230),
                config={"template": "Analise e responda com clareza:\n\n{{message}}"},
            ),
            Node(
                id="agent-researcher",
                type="agent",
                name="Agente pesquisador",
                position=Position(x=640, y=230),
                config={
                    "role": "Pesquisador",
                    "provider": "mock",
                    "model": "gpt-4.1-mini",
                    "system_prompt": "Você é um pesquisador objetivo.",
                    "input_field": "prompt",
                    "output_field": "research",
                    "api_key_env": "OPENAI_API_KEY",
                    "temperature": 0.2,
                },
            ),
            Node(
                id="agent-reviewer",
                type="agent",
                name="Agente revisor",
                position=Position(x=920, y=230),
                config={
                    "role": "Revisor executivo",
                    "provider": "mock",
                    "model": "gpt-4.1-mini",
                    "system_prompt": "Revise o material e produza a resposta final.",
                    "input_field": "research",
                    "output_field": "response",
                    "api_key_env": "OPENAI_API_KEY",
                    "temperature": 0.1,
                },
            ),
            Node(id="output-1", type="output", name="Resposta final", position=Position(x=1200, y=230), config={"field": "response"}),
        ],
        edges=[
            Edge(id="e1", source="input-1", target="prompt-1"),
            Edge(id="e2", source="prompt-1", target="agent-researcher"),
            Edge(id="e3", source="agent-researcher", target="agent-reviewer"),
            Edge(id="e4", source="agent-reviewer", target="output-1"),
        ],
    )


def database_from_environment() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    if os.getenv("DB_HOST"):
        user = quote_plus(os.getenv("DB_USER", "agentic"))
        password = quote_plus(os.getenv("DB_PASSWORD", ""))
        host = os.getenv("DB_HOST", "mysql")
        port = os.getenv("DB_PORT", "3306")
        name = os.getenv("DB_NAME", "agentic_flow")
        return f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"
    return str(DATA_DIR / "agentic-flow-v2.db")


def create_app(database: str | Path | None = None) -> FastAPI:
    app = FastAPI(
        title="Agentic Flow API",
        description="Construtor visual multiagente com PyReact e LangGraph.",
        version="0.2.0",
    )
    database_target = database or database_from_environment()
    store = Store(database_target)
    engine = WorkflowEngine()
    app.state.store = store
    app.state.engine = engine
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv("SESSION_SECRET", "dev-only-change-this-session-secret"),
        session_cookie="agentic_session",
        max_age=60 * 60 * 24 * 14,
        same_site="lax",
        https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    )
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    def auth_context(request: Request) -> tuple[dict[str, Any], dict[str, str]]:
        user_id = request.session.get("user_id")
        user = store.get_user(user_id) if user_id else None
        workspace = store.get_user_workspace(user_id) if user else None
        if not user or not workspace:
            request.session.clear()
            raise HTTPException(401, "Autenticação necessária.")
        return user, workspace

    def provision_webhooks(
        payload: WorkflowCreate,
        current: Workflow | None = None,
    ) -> WorkflowCreate:
        prepared = payload.model_copy(deep=True)
        existing = {
            node.id: node.config.get("webhook_id")
            for node in (current.nodes if current else [])
            if node.type == "webhook" and node.config.get("webhook_id")
        }
        for node in prepared.nodes:
            if node.type != "webhook":
                continue
            if existing.get(node.id):
                node.config["webhook_id"] = existing[node.id]
                continue
            while True:
                generated = "wh_" + secrets.token_urlsafe(24)
                if not store.find_webhook(generated):
                    node.config["webhook_id"] = generated
                    break
        return prepared

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "engine": "langgraph", "ui": "pyreact"}

    @app.get("/", include_in_schema=False)
    def index(request: Request):
        if not store.has_users():
            return RedirectResponse("/setup", status_code=303)
        if not request.session.get("user_id"):
            return RedirectResponse("/login", status_code=303)
        return RedirectResponse("/dashboard", status_code=303)

    @app.get("/setup", response_class=HTMLResponse, include_in_schema=False)
    def setup_page(request: Request):
        if store.has_users():
            destination = "/dashboard" if request.session.get("user_id") else "/login"
            return RedirectResponse(destination, status_code=303)
        return render_auth_page("setup")

    @app.get("/login", response_class=HTMLResponse, include_in_schema=False)
    def login_page(request: Request):
        if not store.has_users():
            return RedirectResponse("/setup", status_code=303)
        if request.session.get("user_id") and store.get_user(request.session["user_id"]):
            return RedirectResponse("/dashboard", status_code=303)
        return render_auth_page("login")

    @app.post("/api/auth/setup", status_code=201)
    def setup_admin(payload: SetupPayload, request: Request):
        try:
            user, workspace = store.create_admin(
                name=payload.name,
                email=payload.email,
                password=payload.password,
                workspace_name=payload.workspace_name,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        store.create_workflow(sample_workflow(), workspace["id"], user["id"])
        request.session.clear()
        request.session["user_id"] = user["id"]
        return {"user": user, "workspace": workspace}

    @app.post("/api/auth/login")
    def login(payload: LoginPayload, request: Request):
        if not store.has_users():
            raise HTTPException(409, "Conclua a configuração inicial.")
        user = store.authenticate(payload.email, payload.password)
        if not user:
            raise HTTPException(401, "E-mail ou senha inválidos.")
        request.session.clear()
        request.session["user_id"] = user["id"]
        return {"user": user}

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request):
        request.session.clear()
        return Response(status_code=204)

    @app.get("/api/auth/me")
    def current_user(request: Request):
        user, workspace = auth_context(request)
        return {"user": user, "workspace": workspace}

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    def dashboard(request: Request):
        try:
            user, workspace = auth_context(request)
        except HTTPException:
            destination = "/setup" if not store.has_users() else "/login"
            return RedirectResponse(destination, status_code=303)
        return render_dashboard(
            store.list_workflows(workspace["id"]),
            user,
            workspace,
        )

    @app.get("/workflows/{workflow_id}", response_class=HTMLResponse, include_in_schema=False)
    def editor(workflow_id: str, request: Request):
        try:
            _, workspace = auth_context(request)
        except HTTPException:
            return RedirectResponse("/login", status_code=303)
        if not store.get_workflow(workflow_id, workspace["id"]):
            raise HTTPException(404, "Workflow não encontrado.")
        return render_page(workflow_id)

    @app.get("/api/catalog")
    def catalog(request: Request):
        auth_context(request)
        return NODE_CATALOG

    @app.get("/api/users")
    def users(request: Request):
        user, workspace = auth_context(request)
        if user["role"] != "admin":
            raise HTTPException(403, "Apenas administradores podem listar usuários.")
        return store.list_users(workspace["id"])

    @app.get("/api/workflows")
    def workflows(request: Request):
        _, workspace = auth_context(request)
        return store.list_workflows(workspace["id"])

    @app.post("/api/workflows", status_code=201)
    def create_workflow(payload: WorkflowCreate, request: Request):
        user, workspace = auth_context(request)
        prepared = provision_webhooks(payload)
        return store.create_workflow(prepared, workspace["id"], user["id"])

    @app.get("/api/workflows/{workflow_id}")
    def get_workflow(workflow_id: str, request: Request):
        _, workspace = auth_context(request)
        workflow = store.get_workflow(workflow_id, workspace["id"])
        if not workflow:
            raise HTTPException(404, "Workflow não encontrado.")
        return workflow

    @app.put("/api/workflows/{workflow_id}")
    def update_workflow(workflow_id: str, payload: WorkflowCreate, request: Request):
        _, workspace = auth_context(request)
        current = store.get_workflow(workflow_id, workspace["id"])
        if not current:
            raise HTTPException(404, "Workflow não encontrado.")
        prepared = provision_webhooks(payload, current)
        candidate = Workflow.model_validate(
            {**current.model_dump(), **prepared.model_dump()}
        )
        if candidate.nodes:
            try:
                validate_workflow(candidate)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        return store.update_workflow(workflow_id, prepared, workspace["id"])

    @app.delete("/api/workflows/{workflow_id}", status_code=204)
    def delete_workflow(workflow_id: str, request: Request):
        _, workspace = auth_context(request)
        if not store.delete_workflow(workflow_id, workspace["id"]):
            raise HTTPException(404, "Workflow não encontrado.")
        return Response(status_code=204)

    @app.post("/api/workflows/{workflow_id}/run")
    def run_workflow(workflow_id: str, payload: RunRequest, request: Request):
        _, workspace = auth_context(request)
        workflow = store.get_workflow(workflow_id, workspace["id"])
        if not workflow:
            raise HTTPException(404, "Workflow não encontrado.")
        result = engine.run(workflow, payload)
        store.save_run(result, workspace["id"])
        return result

    @app.get("/api/workflows/{workflow_id}/runs")
    def workflow_runs(workflow_id: str, request: Request, limit: int = 20):
        _, workspace = auth_context(request)
        if not store.get_workflow(workflow_id, workspace["id"]):
            raise HTTPException(404, "Workflow não encontrado.")
        return store.list_runs(workflow_id, workspace["id"], min(max(limit, 1), 100))

    @app.post("/webhooks/{webhook_id}")
    async def receive_webhook(webhook_id: str, request: Request):
        match = store.find_webhook(webhook_id)
        if not match:
            raise HTTPException(404, "Webhook não encontrado ou desativado.")
        workflow, trigger_node, workspace_id = match
        try:
            body = await request.json()
        except Exception:
            raw = await request.body()
            body = {"message": raw.decode("utf-8", errors="replace")}
        webhook_input = dict(body) if isinstance(body, dict) else {"payload": body}
        webhook_input["_webhook"] = {
            "method": request.method,
            "query": dict(request.query_params),
            "trigger_node_id": trigger_node.id,
        }
        result = engine.run(
            workflow,
            RunRequest(input=webhook_input, session_id=f"webhook:{webhook_id}"),
            entry_node_id=trigger_node.id,
        )
        store.save_run(result, workspace_id)
        if trigger_node.config.get("response_mode") == "accepted":
            return JSONResponse(
                {"accepted": True, "run_id": result.id, "status": result.status},
                status_code=202,
            )
        return JSONResponse(
            result.model_dump(),
            status_code=200 if result.status == "success" else 500,
        )

    return app


app = create_app()


def run() -> None:
    uvicorn.run("agentic_flow.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    run()
