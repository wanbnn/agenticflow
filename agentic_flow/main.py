from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any, Literal
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
from .providers import PROVIDER_TYPES, PROVIDER_TYPE_MAP, ProviderRuntime
from .store import Store
from .templates import instantiate_template, template_catalog
from .ui import (
    render_access_page,
    render_auth_page,
    render_dashboard,
    render_page,
    render_providers_page,
)


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


class ProviderPayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    type: str
    base_url: str = Field(default="", max_length=500)
    default_model: str = Field(default="", max_length=160)
    api_key: str = Field(default="", max_length=1000)
    enabled: bool = True

    @field_validator("type")
    @classmethod
    def known_type(cls, value: str) -> str:
        if value not in PROVIDER_TYPE_MAP:
            raise ValueError("Tipo de provedor desconhecido.")
        return value


class UserCreatePayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "manager", "user"] = "user"


class UserUpdatePayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role: Literal["admin", "manager", "user"]
    active: bool = True


class WorkspacePayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class WorkspaceMembershipPayload(BaseModel):
    user_id: str
    enabled: bool = True


class TeamPolicyPayload(BaseModel):
    create_workflows: bool = False
    edit_workflows: bool = False
    run_workflows: bool = True
    manage_providers: bool = False
    allowed_node_types: list[str] | None = None


class TeamPayload(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    policy: TeamPolicyPayload = Field(default_factory=TeamPolicyPayload)


class TeamMembersPayload(BaseModel):
    user_ids: list[str] = Field(default_factory=list)


class TemplateInstantiatePayload(BaseModel):
    name: str | None = Field(default=None, max_length=120)


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
                    "provider_id": "mock",
                    "model": "",
                    "system_prompt": "Você é um pesquisador objetivo.",
                    "input_field": "prompt",
                    "output_field": "research",
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
                    "provider_id": "mock",
                    "model": "",
                    "system_prompt": "Revise o material e produza a resposta final.",
                    "input_field": "research",
                    "output_field": "response",
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
    encryption_secret = os.getenv(
        "CREDENTIALS_ENCRYPTION_KEY",
        os.getenv("SESSION_SECRET", "dev-only-change-this-session-secret"),
    )
    provider_runtime = ProviderRuntime(store, encryption_secret)
    engine = WorkflowEngine(provider_runtime, store)
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

    def auth_context(request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
        user_id = request.session.get("user_id")
        user = store.get_user(user_id) if user_id else None
        workspace = (
            store.get_accessible_workspace(
                user_id, request.session.get("workspace_id")
            )
            if user
            else None
        )
        if user and not workspace:
            workspace = store.get_accessible_workspace(user_id)
        if not user or not workspace:
            request.session.clear()
            raise HTTPException(401, "Autenticação necessária.")
        request.session["workspace_id"] = workspace["id"]
        return user, workspace

    def permissions_for(user: dict[str, Any], workspace: dict[str, Any]):
        return store.effective_permissions(user["id"], workspace["id"])

    def require_global_admin(
        request: Request,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        user, workspace = auth_context(request)
        if user["role"] != "admin":
            raise HTTPException(403, "Apenas administradores podem realizar esta ação.")
        return user, workspace

    def require_permission(
        request: Request, permission: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, object]]:
        user, workspace = auth_context(request)
        permissions = permissions_for(user, workspace)
        if not permissions.get(permission):
            raise HTTPException(403, "Seu papel ou time não permite esta ação.")
        return user, workspace, permissions

    def validate_node_access(
        payload: WorkflowCreate, permissions: dict[str, object]
    ) -> None:
        allowed = permissions.get("allowed_node_types")
        if allowed is None:
            return
        blocked = sorted({node.type for node in payload.nodes} - set(allowed))
        if blocked:
            raise HTTPException(
                403,
                "Seu time não permite os seguintes tipos de nó: "
                + ", ".join(blocked),
            )

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

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
        <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop stop-color="#957fff"/><stop offset="1" stop-color="#6041ed"/>
        </linearGradient></defs><rect width="64" height="64" rx="16" fill="url(#g)"/>
        <path d="M18 46 28 17h8l10 29h-8l-2-7H27l-2 7h-7Zm11-14h5l-2-8-3 8Z"
        fill="white"/></svg>"""
        return Response(content=svg, media_type="image/svg+xml")

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
        request.session["workspace_id"] = workspace["id"]
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
        workspace = store.get_accessible_workspace(user["id"])
        if not workspace:
            request.session.clear()
            raise HTTPException(
                403, "Seu usuário ainda não foi liberado em um workspace."
            )
        request.session["workspace_id"] = workspace["id"]
        return {"user": user}

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request):
        request.session.clear()
        return Response(status_code=204)

    @app.get("/api/auth/me")
    def current_user(request: Request):
        user, workspace = auth_context(request)
        return {
            "user": user,
            "workspace": workspace,
            "workspaces": store.list_workspaces(user["id"]),
            "permissions": permissions_for(user, workspace),
        }

    @app.post("/api/auth/workspace/{workspace_id}")
    def switch_workspace(workspace_id: str, request: Request):
        user_id = request.session.get("user_id")
        workspace = (
            store.get_accessible_workspace(user_id, workspace_id)
            if user_id
            else None
        )
        if not workspace:
            raise HTTPException(403, "Acesso ao workspace não autorizado.")
        request.session["workspace_id"] = workspace_id
        return {"workspace": workspace}

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
            store.list_workspaces(user["id"]),
            permissions_for(user, workspace),
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
        user, workspace = auth_context(request)
        allowed = permissions_for(user, workspace).get("allowed_node_types")
        if allowed is None:
            return NODE_CATALOG
        return [node for node in NODE_CATALOG if node["type"] in allowed]

    def require_admin(request: Request) -> tuple[dict[str, Any], dict[str, Any]]:
        user, workspace, _ = require_permission(request, "manage_providers")
        return user, workspace

    @app.get("/api/users")
    def users(request: Request):
        user, workspace, _ = require_permission(request, "manage_teams")
        return store.list_users(workspace["id"])

    @app.get("/settings/access", response_class=HTMLResponse, include_in_schema=False)
    def access_page(request: Request):
        try:
            user, workspace, _ = require_permission(request, "manage_teams")
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse("/login", status_code=303)
            raise
        return render_access_page(
            user, workspace, store.list_workspaces(user["id"])
        )

    @app.get("/api/access/overview")
    def access_overview(request: Request):
        user, workspace, permissions = require_permission(request, "manage_teams")
        return {
            "current_user": user,
            "workspace": workspace,
            "workspaces": store.list_workspaces(user["id"]),
            "users": (
                store.list_all_users()
                if user["role"] == "admin"
                else store.list_users(workspace["id"])
            ),
            "workspace_users": store.list_users(workspace["id"]),
            "teams": store.list_teams(workspace["id"]),
            "node_types": [
                {"type": item["type"], "name": item["name"]}
                for item in NODE_CATALOG
            ],
            "permissions": permissions,
        }

    @app.post("/api/admin/users", status_code=201)
    def create_user(payload: UserCreatePayload, request: Request):
        require_global_admin(request)
        try:
            return store.create_user(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.put("/api/admin/users/{user_id}")
    def update_user(user_id: str, payload: UserUpdatePayload, request: Request):
        current, _ = require_global_admin(request)
        if user_id == current["id"] and (
            payload.role != "admin" or not payload.active
        ):
            raise HTTPException(422, "Você não pode remover o próprio acesso administrativo.")
        updated = store.update_user(user_id, **payload.model_dump())
        if not updated:
            raise HTTPException(404, "Usuário não encontrado.")
        return updated

    @app.post("/api/admin/workspaces", status_code=201)
    def create_workspace(payload: WorkspacePayload, request: Request):
        require_global_admin(request)
        return store.create_workspace(payload.name)

    @app.put("/api/admin/workspaces/{workspace_id}/members")
    def set_workspace_member(
        workspace_id: str,
        payload: WorkspaceMembershipPayload,
        request: Request,
    ):
        require_global_admin(request)
        if not store.set_workspace_membership(
            workspace_id, payload.user_id, payload.enabled
        ):
            raise HTTPException(404, "Usuário ou workspace não encontrado.")
        return {"updated": True}

    @app.post("/api/teams", status_code=201)
    def create_team(payload: TeamPayload, request: Request):
        user, workspace, _ = require_permission(request, "manage_teams")
        return store.create_team(
            workspace_id=workspace["id"],
            created_by=user["id"],
            **payload.model_dump(),
        )

    @app.put("/api/teams/{team_id}")
    def update_team(team_id: str, payload: TeamPayload, request: Request):
        _, workspace, _ = require_permission(request, "manage_teams")
        updated = store.update_team(
            team_id, workspace["id"], **payload.model_dump()
        )
        if not updated:
            raise HTTPException(404, "Time não encontrado.")
        return updated

    @app.delete("/api/teams/{team_id}", status_code=204)
    def delete_team(team_id: str, request: Request):
        _, workspace, _ = require_permission(request, "manage_teams")
        if not store.delete_team(team_id, workspace["id"]):
            raise HTTPException(404, "Time não encontrado.")
        return Response(status_code=204)

    @app.put("/api/teams/{team_id}/members")
    def set_team_members(
        team_id: str, payload: TeamMembersPayload, request: Request
    ):
        _, workspace, _ = require_permission(request, "manage_teams")
        if not store.set_team_members(
            team_id, workspace["id"], payload.user_ids
        ):
            raise HTTPException(404, "Time não encontrado.")
        return {"updated": True}

    @app.get("/settings/providers", response_class=HTMLResponse, include_in_schema=False)
    def providers_page(request: Request):
        try:
            user, workspace = require_admin(request)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse("/login", status_code=303)
            raise
        return render_providers_page(
            store.list_providers(workspace["id"]),
            PROVIDER_TYPES,
            user,
            workspace,
            store.list_workspaces(user["id"]),
        )

    @app.get("/api/provider-types")
    def provider_types(request: Request):
        auth_context(request)
        return PROVIDER_TYPES

    @app.get("/api/providers")
    def providers(request: Request):
        _, workspace = auth_context(request)
        return store.list_providers(workspace["id"])

    @app.get("/api/templates")
    def workflow_templates(request: Request):
        user, workspace = auth_context(request)
        permissions = permissions_for(user, workspace)
        allowed = permissions.get("allowed_node_types")
        can_create = bool(permissions.get("create_workflows"))
        result = []
        for template in template_catalog():
            blocked = (
                sorted(set(template["node_types"]) - set(allowed))
                if allowed is not None
                else []
            )
            result.append(
                {
                    **template,
                    "compatible": can_create and not blocked,
                    "blocked_node_types": blocked,
                }
            )
        return result

    @app.post("/api/templates/{template_id}/instantiate", status_code=201)
    def create_from_template(
        template_id: str,
        payload: TemplateInstantiatePayload,
        request: Request,
    ):
        user, workspace, permissions = require_permission(
            request, "create_workflows"
        )
        try:
            workflow = instantiate_template(template_id, payload.name)
        except KeyError as exc:
            raise HTTPException(404, "Template não encontrado.") from exc
        validate_node_access(workflow, permissions)
        prepared = provision_webhooks(workflow)
        return store.create_workflow(
            prepared, workspace["id"], user["id"]
        )

    def provider_values(payload: ProviderPayload) -> tuple[str, str]:
        definition = PROVIDER_TYPE_MAP[payload.type]
        base_url = (payload.base_url or definition["base_url"]).strip().rstrip("/")
        default_model = (payload.default_model or definition["default_model"]).strip()
        if not base_url.startswith(("http://", "https://")):
            raise HTTPException(422, "A URL base precisa usar http:// ou https://.")
        if payload.enabled and definition["requires_key"] and not payload.api_key:
            raise HTTPException(422, "Informe a API key para ativar este provedor.")
        return base_url, default_model

    @app.post("/api/providers", status_code=201)
    def create_provider(payload: ProviderPayload, request: Request):
        _, workspace = require_admin(request)
        base_url, default_model = provider_values(payload)
        return store.create_provider(
            workspace_id=workspace["id"],
            name=payload.name.strip(),
            provider_type=payload.type,
            base_url=base_url,
            default_model=default_model,
            api_key_encrypted=provider_runtime.encrypt_key(payload.api_key),
            enabled=payload.enabled,
        )

    @app.put("/api/providers/{provider_id}")
    def update_provider(
        provider_id: str, payload: ProviderPayload, request: Request
    ):
        _, workspace = require_admin(request)
        current = store.get_provider(provider_id, workspace["id"])
        if not current:
            raise HTTPException(404, "Provedor não encontrado.")
        definition = PROVIDER_TYPE_MAP[payload.type]
        if (
            payload.enabled
            and definition["requires_key"]
            and not payload.api_key
            and not current["has_api_key"]
        ):
            raise HTTPException(422, "Informe a API key para ativar este provedor.")
        base_url = (payload.base_url or definition["base_url"]).strip().rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise HTTPException(422, "A URL base precisa usar http:// ou https://.")
        return store.update_provider(
            provider_id,
            workspace["id"],
            name=payload.name.strip(),
            provider_type=payload.type,
            base_url=base_url,
            default_model=(payload.default_model or definition["default_model"]).strip(),
            api_key_encrypted=(
                provider_runtime.encrypt_key(payload.api_key) if payload.api_key else None
            ),
            enabled=payload.enabled,
        )

    @app.delete("/api/providers/{provider_id}", status_code=204)
    def delete_provider(provider_id: str, request: Request):
        _, workspace = require_admin(request)
        if not store.delete_provider(provider_id, workspace["id"]):
            raise HTTPException(404, "Provedor não encontrado.")
        return Response(status_code=204)

    @app.post("/api/providers/{provider_id}/test")
    def test_provider(provider_id: str, request: Request):
        _, workspace = require_admin(request)
        provider = store.get_provider(provider_id, workspace["id"])
        if not provider:
            raise HTTPException(404, "Provedor não encontrado.")
        try:
            answer = provider_runtime.chat(
                provider_id=provider_id,
                workspace_id=workspace["id"],
                model="",
                instructions="Responda de forma curta.",
                prompt="Responda apenas: conexão funcionando",
                temperature=0,
            )
        except Exception as exc:
            raise HTTPException(422, f"Falha ao conectar: {exc}") from exc
        return {"status": "ok", "preview": answer[:200]}

    @app.get("/api/workflows")
    def workflows(request: Request):
        _, workspace = auth_context(request)
        return store.list_workflows(workspace["id"])

    @app.post("/api/workflows", status_code=201)
    def create_workflow(payload: WorkflowCreate, request: Request):
        user, workspace, permissions = require_permission(
            request, "create_workflows"
        )
        validate_node_access(payload, permissions)
        prepared = provision_webhooks(payload)
        if prepared.nodes:
            try:
                validate_workflow(Workflow(**prepared.model_dump()))
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
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
        _, workspace, permissions = require_permission(request, "edit_workflows")
        validate_node_access(payload, permissions)
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
        _, workspace, _ = require_permission(request, "edit_workflows")
        if not store.delete_workflow(workflow_id, workspace["id"]):
            raise HTTPException(404, "Workflow não encontrado.")
        return Response(status_code=204)

    @app.post("/api/workflows/{workflow_id}/run")
    def run_workflow(workflow_id: str, payload: RunRequest, request: Request):
        _, workspace, _ = require_permission(request, "run_workflows")
        workflow = store.get_workflow(workflow_id, workspace["id"])
        if not workflow:
            raise HTTPException(404, "Workflow não encontrado.")
        result = engine.run(workflow, payload, workspace_id=workspace["id"])
        store.save_run(result, workspace["id"])
        return result

    @app.get("/api/workflows/{workflow_id}/runs")
    def workflow_runs(workflow_id: str, request: Request, limit: int = 20):
        _, workspace = auth_context(request)
        if not store.get_workflow(workflow_id, workspace["id"]):
            raise HTTPException(404, "Workflow não encontrado.")
        return store.list_runs(workflow_id, workspace["id"], min(max(limit, 1), 100))

    @app.get("/api/workflows/{workflow_id}/vector-databases/{node_id}")
    def vector_database_stats(workflow_id: str, node_id: str, request: Request):
        _, workspace = auth_context(request)
        workflow = store.get_workflow(workflow_id, workspace["id"])
        if not workflow:
            raise HTTPException(404, "Workflow não encontrado.")
        if not any(
            node.id == node_id and node.type == "vector_database"
            for node in workflow.nodes
        ):
            raise HTTPException(404, "Banco de Vetores não encontrado.")
        return store.vector_stats(workspace["id"], workflow_id, node_id)

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
            workspace_id=workspace_id,
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
    uvicorn.run("agentic_flow.main:app", host="0.0.0.0", port=16777, reload=False)


if __name__ == "__main__":
    run()
