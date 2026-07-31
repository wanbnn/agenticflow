from fastapi.testclient import TestClient

from agentic_flow.local_models import LocalModelRuntime
from agentic_flow.main import create_app


def bootstrap(client: TestClient):
    response = client.post(
        "/api/auth/setup",
        json={
            "name": "Admin",
            "email": "admin@example.com",
            "password": "senha-segura-123",
            "workspace_name": "Local AI",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_registers_any_huggingface_model_without_exposing_token(tmp_path):
    app = create_app(tmp_path / "test.db")
    client = TestClient(app)
    bootstrap(client)

    response = client.post(
        "/api/local-models",
        json={
            "repository_id": "organization/private-multimodal-model",
            "revision": "v1",
            "task": "image-to-text",
            "token": "hf_super_secret",
            "download": False,
            "options": {"trust_remote_code": False},
        },
    )

    assert response.status_code == 202
    model = response.json()
    assert model["status"] == "ready"
    assert model["task"] == "image-to-text"
    assert "token" not in model
    assert "hf_super_secret" not in response.text
    listed = client.get("/api/local-models").json()
    assert listed == [model]


def test_local_runtime_serializes_text_pipeline_and_unloads(tmp_path):
    app = create_app(tmp_path / "test.db")
    client = TestClient(app)
    context = bootstrap(client)
    model = client.post(
        "/api/local-models",
        json={
            "repository_id": "org/tiny-text",
            "task": "text-generation",
            "download": False,
        },
    ).json()
    runtime: LocalModelRuntime = app.state.local_model_runtime
    runtime._pipelines[model["id"]] = lambda value, **parameters: [
        {"generated_text": f"local: {value}", "parameters": parameters}
    ]

    response = client.post(
        f"/api/local-models/{model['id']}/infer",
        json={"input": "olá", "parameters": {"max_new_tokens": 12}},
    )
    assert response.status_code == 200
    assert response.json()["output"][0]["generated_text"] == "local: olá"
    assert runtime.unload(model["id"]) is True


def test_local_model_catalog_exposes_all_modalities(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    bootstrap(client)
    tasks = {item["task"] for item in client.get("/api/local-model-tasks").json()}
    assert {
        "text-generation",
        "image-to-text",
        "automatic-speech-recognition",
        "text-to-audio",
        "text-to-image",
        "image-to-3d",
        "text-to-3d",
    }.issubset(tasks)
    catalog = {item["type"] for item in client.get("/api/catalog").json()}
    assert {"local_model", "audio_input"}.issubset(catalog)


def test_workflow_executes_installed_local_model_node(tmp_path):
    app = create_app(tmp_path / "test.db")
    client = TestClient(app)
    bootstrap(client)
    model = client.post(
        "/api/local-models",
        json={
            "repository_id": "org/tiny-workflow-model",
            "task": "text-generation",
            "download": False,
        },
    ).json()
    app.state.local_model_runtime._pipelines[model["id"]] = (
        lambda value, **_parameters: [{"generated_text": str(value).upper()}]
    )
    workflow = client.post(
        "/api/workflows",
        json={
            "name": "Modelo self-hosted",
            "nodes": [
                {"id": "input", "type": "text_input", "name": "Texto", "config": {"input_key": "text"}},
                {
                    "id": "model",
                    "type": "local_model",
                    "name": "HF local",
                    "config": {"model_id": model["id"], "input_field": "text", "output_field": "local_output"},
                },
                {"id": "output", "type": "output", "name": "Saída", "config": {"field": "local_output"}},
            ],
            "edges": [
                {"id": "e1", "source": "input", "target": "model"},
                {"id": "e2", "source": "model", "target": "output"},
            ],
        },
    ).json()
    result = client.post(
        f"/api/workflows/{workflow['id']}/run", json={"input": {"text": "local"}}
    )
    assert result.status_code == 200
    assert result.json()["output"][0]["generated_text"] == "LOCAL"
