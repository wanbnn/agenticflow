import sqlite3

import pytest
from fastapi.testclient import TestClient

from agentic_flow.databases import DATABASE_NODE_TYPES, validate_read_query
from agentic_flow.main import create_app


def bootstrap(client: TestClient):
    response = client.post(
        "/api/auth/setup",
        json={
            "name": "Admin",
            "email": "admin@example.com",
            "password": "senha-segura-123",
            "workspace_name": "Workspace de dados",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_source_database(path):
    with sqlite3.connect(path) as database:
        database.execute(
            "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, total REAL)"
        )
        database.executemany(
            "INSERT INTO customers (name, total) VALUES (?, ?)",
            [("Ada", 125.5), ("Linus", 80.0)],
        )
        database.commit()


def create_sqlite_connection(client: TestClient, path):
    response = client.post(
        "/api/database-connections",
        json={
            "name": "Analytics local",
            "type": "sqlite",
            "database_name": str(path),
            "secret": "não-deve-voltar",
            "enabled": True,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_database_catalog_has_a_separate_node_for_each_engine(tmp_path):
    client = TestClient(create_app(tmp_path / "app.db"))
    bootstrap(client)

    catalog = {
        item["type"]: item for item in client.get("/api/catalog").json()
    }
    assert set(DATABASE_NODE_TYPES).issubset(catalog)
    assert len(DATABASE_NODE_TYPES) >= 6
    for node_type, database_type in DATABASE_NODE_TYPES.items():
        node = catalog[node_type]
        assert node["fields"][0]["database_type"] == database_type
        assert {"default", "tool"} == {
            output["id"] for output in node["outputs"]
        }


def test_workspace_database_crud_encrypts_secret_and_tests_connection(tmp_path):
    source = tmp_path / "source.db"
    create_source_database(source)
    app = create_app(tmp_path / "app.db")
    client = TestClient(app)
    context = bootstrap(client)
    created = create_sqlite_connection(client, source)

    assert created["workspace_id"] == context["workspace"]["id"]
    assert created["has_secret"] is True
    assert "secret" not in created
    listed = client.get("/api/database-connections").json()
    assert listed == [created]
    stored = app.state.store.get_database_connection(
        created["id"], context["workspace"]["id"], include_secret=True
    )
    assert stored["secret_encrypted"] != "não-deve-voltar"

    tested = client.post(
        f"/api/database-connections/{created['id']}/test"
    )
    assert tested.status_code == 200
    assert tested.json()["status"] == "ok"

    page = client.get("/settings/databases")
    assert page.status_code == 200
    assert "Conexões de bancos" in page.text
    assert "/static/databases.js" in page.text

    deleted = client.delete(f"/api/database-connections/{created['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/database-connections").json() == []


def test_sqlite_node_executes_read_query_and_blocks_writes(tmp_path):
    source = tmp_path / "source.db"
    create_source_database(source)
    client = TestClient(create_app(tmp_path / "app.db"))
    bootstrap(client)
    connection = create_sqlite_connection(client, source)

    workflow = client.post(
        "/api/workflows",
        json={
            "name": "Consulta segura",
            "nodes": [
                {
                    "id": "input",
                    "type": "input",
                    "name": "Entrada",
                    "position": {"x": 0, "y": 0},
                    "config": {},
                },
                {
                    "id": "database",
                    "type": "database_sqlite",
                    "name": "SQLite",
                    "position": {"x": 250, "y": 0},
                    "config": {
                        "connection_id": connection["id"],
                        "operation": "query",
                        "query": "SELECT name, total FROM customers ORDER BY total DESC",
                        "max_rows": 10,
                        "output_field": "database_result",
                    },
                },
                {
                    "id": "output",
                    "type": "output",
                    "name": "Resultado",
                    "position": {"x": 500, "y": 0},
                    "config": {"field": "database_result"},
                },
            ],
            "edges": [
                {"id": "e1", "source": "input", "target": "database"},
                {"id": "e2", "source": "database", "target": "output"},
            ],
        },
    )
    assert workflow.status_code == 201
    result = client.post(
        f"/api/workflows/{workflow.json()['id']}/run", json={"input": {}}
    ).json()
    assert result["status"] == "success"
    assert result["output"]["rows"][0] == {"name": "Ada", "total": 125.5}

    analyst = client.post(
        "/api/templates/sqlite-data-analyst/instantiate", json={}
    ).json()
    for node in analyst["nodes"]:
        if node["type"] == "database_sqlite":
            node["config"]["connection_id"] = connection["id"]
    updated = client.put(
        f"/api/workflows/{analyst['id']}",
        json={
            "name": analyst["name"],
            "description": analyst["description"],
            "nodes": analyst["nodes"],
            "edges": analyst["edges"],
        },
    )
    assert updated.status_code == 200
    agent_result = client.post(
        f"/api/workflows/{analyst['id']}/run",
        json={
            "input": {
                "text": "SELECT name, total FROM customers ORDER BY total DESC"
            }
        },
    ).json()
    assert agent_result["status"] == "success"
    assert "Ada" in agent_result["output"]

    with pytest.raises(ValueError, match="não permitida"):
        validate_read_query("SELECT 1; DROP TABLE customers")
    with pytest.raises(ValueError, match="Somente consultas"):
        validate_read_query("UPDATE customers SET total = 0")

    with sqlite3.connect(source) as database:
        assert database.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 2


def test_database_templates_attach_each_engine_as_agent_tool(tmp_path):
    client = TestClient(create_app(tmp_path / "app.db"))
    bootstrap(client)
    catalog = client.get("/api/templates").json()
    database_templates = [
        item for item in catalog if item["category"] == "Bancos de dados"
    ]
    assert len(database_templates) == len(DATABASE_NODE_TYPES)

    for template in database_templates:
        created = client.post(
            f"/api/templates/{template['id']}/instantiate", json={}
        )
        assert created.status_code == 201
        workflow = created.json()
        database_node = next(
            node
            for node in workflow["nodes"]
            if node["type"] in DATABASE_NODE_TYPES
        )
        assert any(
            edge["source"] == database_node["id"]
            and edge["source_handle"] == "tool"
            and edge["target_handle"] == "tools"
            for edge in workflow["edges"]
        )
