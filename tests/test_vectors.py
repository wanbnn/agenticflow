import pytest
from fastapi.testclient import TestClient

from agentic_flow.main import create_app
from agentic_flow.vectors import chunk_text, cosine_similarity, embed_text


def bootstrap(client: TestClient) -> None:
    response = client.post(
        "/api/auth/setup",
        json={
            "name": "Admin",
            "email": "admin-vectors@example.com",
            "password": "senha-segura-123",
            "workspace_name": "Conhecimento",
        },
    )
    assert response.status_code == 201


def vector_workflow() -> dict:
    return {
        "name": "RAG de produtos",
        "description": "Indexa uma base própria e responde usando recuperação.",
        "nodes": [
            {
                "id": "input",
                "type": "input",
                "name": "Entrada",
                "position": {"x": 0, "y": 0},
                "config": {"field": "message"},
            },
            {
                "id": "products-db",
                "type": "vector_database",
                "name": "Produtos",
                "position": {"x": 220, "y": 0},
                "config": {
                    "input_field": "document_text",
                    "output_field": "vector_database",
                    "chunk_size": 120,
                    "chunk_overlap": 20,
                    "write_mode": "append",
                },
            },
            {
                "id": "rag",
                "type": "rag",
                "name": "Consultar produtos",
                "position": {"x": 440, "y": 0},
                "config": {
                    "vector_db_node_id": "products-db",
                    "query_field": "message",
                    "context_field": "rag_context",
                    "matches_field": "rag_matches",
                    "top_k": 3,
                    "min_score": 0,
                },
            },
            {
                "id": "agent",
                "type": "agent",
                "name": "Especialista",
                "position": {"x": 660, "y": 0},
                "config": {
                    "role": "Especialista",
                    "provider_id": "mock",
                    "input_field": "message",
                    "output_field": "response",
                    "vector_db_node_id": "products-db",
                    "rag_top_k": 3,
                    "rag_min_score": 0,
                },
            },
            {
                "id": "output",
                "type": "output",
                "name": "Saída",
                "position": {"x": 880, "y": 0},
                "config": {"field": "response"},
            },
        ],
        "edges": [
            {"source": "input", "target": "products-db"},
            {"source": "products-db", "target": "rag"},
            {"source": "rag", "target": "agent"},
            {"source": "agent", "target": "output"},
        ],
    }


def test_local_embeddings_and_chunking_are_deterministic():
    first = embed_text("plano empresarial com suporte prioritário")
    second = embed_text("plano empresarial com suporte prioritário")
    unrelated = embed_text("receita de bolo de chocolate")
    assert first == second
    assert cosine_similarity(first, second) == pytest.approx(1)
    assert cosine_similarity(first, unrelated) < 1
    assert len(chunk_text("palavra " * 100, size=120, overlap=20)) > 1


def test_vector_node_persists_and_rag_supplies_context_to_agent(tmp_path):
    app = create_app(tmp_path / "vectors.db")
    client = TestClient(app)
    bootstrap(client)
    created = client.post("/api/workflows", json=vector_workflow())
    assert created.status_code == 201
    workflow_id = created.json()["id"]
    empty_stats = client.get(
        f"/api/workflows/{workflow_id}/vector-databases/products-db"
    ).json()
    assert empty_stats["collection_id"]
    assert empty_stats["chunks_total"] == 0

    result = client.post(
        f"/api/workflows/{workflow_id}/run",
        json={
            "input": {
                "message": "Qual plano tem suporte prioritário?",
                "document_text": (
                    "O plano Enterprise inclui suporte prioritário durante 24 horas. "
                    "O plano Básico oferece apenas suporte por e-mail."
                ),
            }
        },
    )
    assert result.status_code == 200
    payload = result.json()
    assert payload["status"] == "success"
    assert "plano Enterprise" in payload["output"]
    rag_event = next(item for item in payload["events"] if item["node_id"] == "rag")
    assert rag_event["output"]["matches"]
    assert rag_event["output"]["vector_db_node_id"] == "products-db"

    stats = client.get(
        f"/api/workflows/{workflow_id}/vector-databases/products-db"
    )
    assert stats.status_code == 200
    assert stats.json()["chunks_total"] >= 1

    # Reindexing identical content does not duplicate it.
    client.post(
        f"/api/workflows/{workflow_id}/run",
        json={
            "input": {
                "message": "suporte prioritário",
                "document_text": (
                    "O plano Enterprise inclui suporte prioritário durante 24 horas. "
                    "O plano Básico oferece apenas suporte por e-mail."
                ),
            }
        },
    )
    assert client.get(
        f"/api/workflows/{workflow_id}/vector-databases/products-db"
    ).json()["chunks_total"] == stats.json()["chunks_total"]


def test_each_vector_node_owns_an_isolated_collection(tmp_path):
    app = create_app(tmp_path / "isolated-vectors.db")
    client = TestClient(app)
    bootstrap(client)
    workflow = vector_workflow()
    workflow["nodes"].insert(
        2,
        {
            "id": "private-db",
            "type": "vector_database",
            "name": "Base privada",
            "position": {"x": 220, "y": 180},
            "config": {
                "input_field": "private_text",
                "output_field": "private_database",
                "chunk_size": 900,
                "chunk_overlap": 120,
                "write_mode": "append",
            },
        },
    )
    workflow["edges"].append({"source": "input", "target": "private-db"})
    created = client.post("/api/workflows", json=workflow).json()
    workflow_id = created["id"]
    client.post(
        f"/api/workflows/{workflow_id}/run",
        json={
            "input": {
                "message": "produto",
                "document_text": "conteúdo público",
                "private_text": "conteúdo secreto",
            }
        },
    )
    public_stats = client.get(
        f"/api/workflows/{workflow_id}/vector-databases/products-db"
    ).json()
    private_stats = client.get(
        f"/api/workflows/{workflow_id}/vector-databases/private-db"
    ).json()
    assert public_stats["collection_id"] != private_stats["collection_id"]
    assert public_stats["chunks_total"] == 1
    assert private_stats["chunks_total"] == 1


def test_invalid_vector_reference_is_rejected(tmp_path):
    client = TestClient(create_app(tmp_path / "invalid-vector.db"))
    bootstrap(client)
    workflow = vector_workflow()
    rag = next(node for node in workflow["nodes"] if node["type"] == "rag")
    rag["config"]["vector_db_node_id"] = "missing"
    created = client.post("/api/workflows", json=workflow)
    assert created.status_code == 422
