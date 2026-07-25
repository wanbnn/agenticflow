from fastapi.testclient import TestClient

from agentic_flow.main import create_app


def bootstrap(client: TestClient):
    response = client.post(
        "/api/auth/setup",
        json={
            "name": "Admin",
            "email": "admin@example.com",
            "password": "senha-segura-123",
            "workspace_name": "Workspace de testes",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_first_run_requires_admin_and_then_opens_dashboard(tmp_path):
    app = create_app(tmp_path / "test.db")
    client = TestClient(app)
    with app.state.store.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    response = client.get("/")
    assert response.status_code == 200
    assert "Crie o administrador" in response.text
    assert client.get("/favicon.ico").status_code == 200

    bootstrap(client)
    response = client.get("/")
    assert response.status_code == 200
    assert "Workflows" in response.text
    assert "Equipe de pesquisa" in response.text
    context = client.get("/api/auth/me").json()
    assert context["workspace"]["membership_role"] == "owner"


def test_editor_is_rendered_with_pyreact_after_login(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    bootstrap(client)
    workflow = client.get("/api/workflows").json()[0]
    response = client.get(f"/workflows/{workflow['id']}")
    assert "Agentic Flow" in response.text
    assert 'id="canvas"' in response.text
    assert "/static/app.js" in response.text


def test_crud_and_run_sample(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    bootstrap(client)
    workflows = client.get("/api/workflows").json()
    assert len(workflows) == 1
    workflow = workflows[0]

    result = client.post(
        f"/api/workflows/{workflow['id']}/run",
        json={"input": {"message": "Explique LangGraph"}},
    ).json()

    assert result["status"] == "success"
    assert "Explique LangGraph" in result["output"]
    assert len(result["events"]) == 5
    assert client.get(f"/api/workflows/{workflow['id']}/runs").json()[0]["id"] == result["id"]


def test_invalid_edge_returns_validation_error(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    bootstrap(client)
    workflow = client.get("/api/workflows").json()[0]
    workflow["edges"].append(
        {"id": "bad", "source": "missing", "target": "input-1", "source_handle": "default"}
    )
    response = client.put(
        f"/api/workflows/{workflow['id']}",
        json={
            "name": workflow["name"],
            "description": workflow["description"],
            "nodes": workflow["nodes"],
            "edges": workflow["edges"],
        },
    )
    assert response.status_code == 422


def test_webhook_gets_random_url_and_executes_its_workflow(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    bootstrap(client)
    payload = {
        "name": "Atendimento por webhook",
        "nodes": [
            {
                "id": "hook",
                "type": "webhook",
                "name": "Mensagem recebida",
                "position": {"x": 0, "y": 0},
                "config": {"webhook_id": "", "response_mode": "workflow_result"},
            },
            {
                "id": "agent",
                "type": "agent",
                "name": "Atendente",
                "position": {"x": 250, "y": 0},
                "config": {
                    "role": "Atendente",
                    "provider": "mock",
                    "input_field": "message",
                    "output_field": "response",
                },
            },
            {
                "id": "out",
                "type": "output",
                "name": "Resposta",
                "position": {"x": 500, "y": 0},
                "config": {"field": "response"},
            },
        ],
        "edges": [
            {"source": "hook", "target": "agent"},
            {"source": "agent", "target": "out"},
        ],
    }
    workflow = client.post("/api/workflows", json=payload).json()
    webhook_id = workflow["nodes"][0]["config"]["webhook_id"]
    assert webhook_id.startswith("wh_")
    assert len(webhook_id) > 25

    response = client.post(
        f"/webhooks/{webhook_id}",
        json={"message": "Olá pelo sistema externo"},
    )
    result = response.json()
    assert response.status_code == 200
    assert result["status"] == "success"
    assert "Olá pelo sistema externo" in result["output"]
    assert [event["node_id"] for event in result["events"]] == ["hook", "agent", "out"]

    saved_again = client.put(
        f"/api/workflows/{workflow['id']}",
        json={
            "name": workflow["name"],
            "description": workflow["description"],
            "nodes": workflow["nodes"],
            "edges": workflow["edges"],
        },
    ).json()
    assert saved_again["nodes"][0]["config"]["webhook_id"] == webhook_id


def test_unknown_webhook_is_not_exposed(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    response = client.post("/webhooks/wh_inexistente", json={"message": "teste"})
    assert response.status_code == 404


def test_authentication_protects_workflows_and_login_restores_session(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    bootstrap(client)
    client.post("/api/auth/logout")
    assert client.get("/api/workflows").status_code == 401

    bad = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "errada"},
    )
    assert bad.status_code == 401
    good = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "senha-segura-123"},
    )
    assert good.status_code == 200
    assert client.get("/api/workflows").status_code == 200


def test_dashboard_can_create_multiple_empty_workflows(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    bootstrap(client)
    first = client.post(
        "/api/workflows",
        json={"name": "Atendimento", "description": "", "nodes": [], "edges": []},
    )
    second = client.post(
        "/api/workflows",
        json={"name": "Vendas", "description": "", "nodes": [], "edges": []},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    names = {workflow["name"] for workflow in client.get("/api/workflows").json()}
    assert {"Equipe de pesquisa", "Atendimento", "Vendas"}.issubset(names)
    dashboard = client.get("/dashboard")
    assert 'id="template-library-button"' in dashboard.text
    assert 'id="template-modal"' in dashboard.text
    assert "/static/dashboard.js?v=" in dashboard.text


def test_workflow_template_library_creates_ready_to_edit_workflow(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    bootstrap(client)
    templates = client.get("/api/templates")
    assert templates.status_code == 200
    by_id = {item["id"]: item for item in templates.json()}
    assert by_id["document-summary"]["compatible"] is True
    assert {"file", "agent", "output"}.issubset(
        by_id["document-summary"]["node_types"]
    )

    created = client.post(
        "/api/templates/document-summary/instantiate",
        json={"name": "Resumidor de contratos"},
    )
    assert created.status_code == 201
    workflow = created.json()
    assert workflow["name"] == "Resumidor de contratos"
    assert {node["type"] for node in workflow["nodes"]} >= {
        "input",
        "file",
        "prompt",
        "agent",
        "output",
    }
    assert client.post(
        "/api/templates/inexistente/instantiate", json={}
    ).status_code == 404


def test_admin_manages_visual_ai_providers_without_exposing_key(tmp_path):
    app = create_app(tmp_path / "test.db")
    client = TestClient(app)
    context = bootstrap(client)

    created = client.post(
        "/api/providers",
        json={
            "name": "Minha API compatível",
            "type": "openai_compatible",
            "base_url": "https://llm.example.com/v1",
            "default_model": "modelo-local",
            "api_key": "chave-super-secreta",
            "enabled": True,
        },
    )
    assert created.status_code == 201
    provider = created.json()
    assert provider["has_api_key"] is True
    assert "api_key" not in provider
    assert "api_key_encrypted" not in provider

    stored = app.state.store.get_provider(
        provider["id"], context["workspace"]["id"], include_secret=True
    )
    assert stored["api_key_encrypted"] != "chave-super-secreta"
    assert "chave-super-secreta" not in stored["api_key_encrypted"]

    updated = client.put(
        f"/api/providers/{provider['id']}",
        json={
            "name": "Minha API renomeada",
            "type": "openai_compatible",
            "base_url": "https://llm.example.com/v1",
            "default_model": "modelo-local",
            "api_key": "",
            "enabled": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["has_api_key"] is True
    assert client.get("/settings/providers").status_code == 200
    assert "Minha API renomeada" in client.get("/settings/providers").text


def test_ollama_provider_does_not_require_api_key(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    bootstrap(client)
    response = client.post(
        "/api/providers",
        json={
            "name": "Ollama local",
            "type": "ollama",
            "base_url": "http://host.docker.internal:11434/v1",
            "default_model": "llama3.2",
            "api_key": "",
            "enabled": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["has_api_key"] is False


def test_admin_manages_users_and_multiple_workspaces(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    setup = bootstrap(client)
    first_workspace = setup["workspace"]["id"]

    manager = client.post(
        "/api/admin/users",
        json={
            "name": "Gestora",
            "email": "manager@example.com",
            "password": "senha-manager-123",
            "role": "manager",
        },
    )
    assert manager.status_code == 201
    member = client.post(
        "/api/admin/users",
        json={
            "name": "Pessoa usuária",
            "email": "user@example.com",
            "password": "senha-user-123",
            "role": "user",
        },
    )
    assert member.status_code == 201
    without_access = client.post(
        "/api/admin/users",
        json={
            "name": "Sem acesso",
            "email": "waiting@example.com",
            "password": "senha-waiting-123",
            "role": "user",
        },
    )
    assert without_access.status_code == 201

    second_workspace = client.post(
        "/api/admin/workspaces", json={"name": "Operação Sul"}
    )
    assert second_workspace.status_code == 201
    second_workspace_id = second_workspace.json()["id"]

    for workspace_id, user_id in [
        (first_workspace, manager.json()["id"]),
        (second_workspace_id, manager.json()["id"]),
        (second_workspace_id, member.json()["id"]),
    ]:
        response = client.put(
            f"/api/admin/workspaces/{workspace_id}/members",
            json={"user_id": user_id, "enabled": True},
        )
        assert response.status_code == 200

    context = client.get("/api/auth/me").json()
    assert {item["id"] for item in context["workspaces"]} == {
        first_workspace,
        second_workspace_id,
    }
    assert client.post(
        f"/api/auth/workspace/{second_workspace_id}"
    ).status_code == 200
    assert client.get("/api/auth/me").json()["workspace"]["id"] == second_workspace_id
    access_page = client.get("/settings/access")
    assert "Usuários, times e políticas" in access_page.text
    assert 'class="workspace-popover"' in access_page.text
    assert 'data-access-tab="people"' in access_page.text
    assert 'data-access-tab="teams"' in access_page.text
    assert 'data-access-tab="workspaces"' in access_page.text
    assert "/static/workspace.js" in access_page.text
    assert "/static/workspace.js?v=" in access_page.text
    assert "/static/access.js?v=" in access_page.text
    assert "/static/styles.css?v=" in access_page.text
    assert 'id="workspace-select"' not in access_page.text

    client.post("/api/auth/logout")
    denied = client.post(
        "/api/auth/login",
        json={"email": "waiting@example.com", "password": "senha-waiting-123"},
    )
    assert denied.status_code == 403


def test_manager_creates_team_and_team_policy_controls_user(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    setup = bootstrap(client)
    workspace_id = setup["workspace"]["id"]
    manager = client.post(
        "/api/admin/users",
        json={
            "name": "Manager",
            "email": "manager@example.com",
            "password": "senha-manager-123",
            "role": "manager",
        },
    ).json()
    user = client.post(
        "/api/admin/users",
        json={
            "name": "User",
            "email": "user@example.com",
            "password": "senha-user-123",
            "role": "user",
        },
    ).json()
    for user_id in (manager["id"], user["id"]):
        assert client.put(
            f"/api/admin/workspaces/{workspace_id}/members",
            json={"user_id": user_id, "enabled": True},
        ).status_code == 200

    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"email": "manager@example.com", "password": "senha-manager-123"},
    ).status_code == 200
    assert client.post(
        "/api/admin/workspaces", json={"name": "Não permitido"}
    ).status_code == 403

    team = client.post(
        "/api/teams",
        json={
            "name": "Criadores básicos",
            "description": "Pode montar fluxos simples.",
            "policy": {
                "create_workflows": True,
                "edit_workflows": True,
                "run_workflows": False,
                "manage_providers": False,
                "allowed_node_types": ["input", "output"],
            },
        },
    )
    assert team.status_code == 201
    assert client.put(
        f"/api/teams/{team.json()['id']}/members",
        json={"user_ids": [user["id"]]},
    ).status_code == 200

    client.post("/api/auth/logout")
    assert client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "senha-user-123"},
    ).status_code == 200
    me = client.get("/api/auth/me").json()
    assert me["permissions"]["create_workflows"] is True
    assert me["permissions"]["run_workflows"] is False
    assert me["permissions"]["allowed_node_types"] == ["input", "output"]
    assert {item["type"] for item in client.get("/api/catalog").json()} == {
        "input",
        "output",
    }
    templates = {
        item["id"]: item for item in client.get("/api/templates").json()
    }
    assert templates["document-summary"]["compatible"] is False
    assert "file" in templates["document-summary"]["blocked_node_types"]
    assert client.post(
        "/api/templates/document-summary/instantiate", json={}
    ).status_code == 403

    allowed = client.post(
        "/api/workflows",
        json={
            "name": "Fluxo permitido",
            "nodes": [
                {
                    "id": "in",
                    "type": "input",
                    "name": "Entrada",
                    "position": {"x": 0, "y": 0},
                    "config": {"field": "message"},
                }
            ],
            "edges": [],
        },
    )
    assert allowed.status_code == 201
    blocked = client.post(
        "/api/workflows",
        json={
            "name": "Fluxo bloqueado",
            "nodes": [
                {
                    "id": "agent",
                    "type": "agent",
                    "name": "Agente",
                    "position": {"x": 0, "y": 0},
                    "config": {},
                }
            ],
            "edges": [],
        },
    )
    assert blocked.status_code == 403
    assert client.post(
        f"/api/workflows/{allowed.json()['id']}/run",
        json={"input": {"message": "teste"}},
    ).status_code == 403
    assert client.get("/api/access/overview").status_code == 403
