import base64
import io
import json
import sys
import threading
import weakref
from types import SimpleNamespace

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

    repeated = client.post(
        "/api/local-models",
        json={
            "repository_id": "organization/private-multimodal-model",
            "revision": "v1",
            "task": "image-to-text",
            "download": False,
        },
    )
    assert repeated.status_code == 202
    assert repeated.json()["id"] == model["id"]
    assert len(client.get("/api/local-models").json()) == 1


def test_local_runtime_detects_and_trusts_required_snapshot_code(tmp_path, monkeypatch):
    model_path = tmp_path / "custom-model"
    model_path.mkdir()
    (model_path / "config.json").write_text(
        json.dumps(
            {
                "model_type": "custom",
                "auto_map": {
                    "AutoConfig": "configuration_custom.CustomConfig",
                    "AutoModelForCausalLM": "modeling_custom.CustomModel",
                },
            }
        ),
        encoding="utf-8",
    )
    captured = {}
    pipeline_instance = lambda value, **_parameters: value

    def fake_pipeline(task, model, **options):
        captured.update(task=task, model=model, options=options)
        return pipeline_instance

    monkeypatch.setitem(
        sys.modules, "transformers", SimpleNamespace(pipeline=fake_pipeline)
    )
    monkeypatch.setattr(
        LocalModelRuntime,
        "hardware",
        staticmethod(lambda: {"backend": "cpu", "device": -1}),
    )
    runtime = LocalModelRuntime(SimpleNamespace(), tmp_path / "cache")
    model = {
        "id": "mdl-custom",
        "repository_id": "org/custom",
        "local_path": str(model_path),
        "task": "text-generation",
        "options": {"trust_remote_code": False},
    }

    assert runtime._pipeline(model) is pipeline_instance
    assert captured["model"] == str(model_path)
    assert captured["options"]["trust_remote_code"] is True


def test_model_library_search_validates_task_and_renders_easy_install_ui(tmp_path):
    app = create_app(tmp_path / "library.db")
    client = TestClient(app)
    bootstrap(client)
    runtime: LocalModelRuntime = app.state.local_model_runtime
    runtime.search = lambda query, task, page, page_size, sort: {
        "items": [
            {
                "id": "Qwen/Qwen3-0.6B",
                "task": task,
                "downloads": 100,
                "likes": 10,
                "estimated_memory_bytes": 1_500_000_000,
            }
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "has_previous": page > 1,
            "has_next": True,
            "start": 19,
            "end": 36,
        },
        "sort": sort,
    }

    response = client.get(
        "/api/huggingface/models",
        params={
            "q": "qwen",
            "task": "text-generation",
            "page": 2,
            "per_page": 18,
            "sort": "trending",
        },
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == "Qwen/Qwen3-0.6B"
    assert response.json()["pagination"]["page"] == 2
    assert client.get(
        "/api/huggingface/models", params={"task": "unknown-task"}
    ).status_code == 422
    assert client.get(
        "/api/huggingface/models", params={"sort": "unknown-sort"}
    ).status_code == 422

    page = client.get("/settings/providers")
    assert page.status_code == 200
    assert "Biblioteca de modelos" in page.text
    assert 'id="model-library-search"' in page.text
    assert 'id="model-discovery-grid"' in page.text
    assert 'id="model-sort"' in page.text
    assert 'id="model-pagination"' in page.text


def test_huggingface_catalog_paginates_and_sorts_without_repeating(monkeypatch, tmp_path):
    captured = {}

    class FakeHfApi:
        def __init__(self, token=None):
            pass

        def list_models(self, **kwargs):
            captured.update(kwargs)
            return [
                SimpleNamespace(
                    id=f"org/model-{index}",
                    pipeline_tag="text-generation",
                    downloads=100 - index,
                    likes=index,
                    trending_score=50 - index,
                    private=False,
                    gated=False,
                    library_name="transformers",
                    tags=["license:apache-2.0"],
                    safetensors=None,
                    last_modified=None,
                )
                for index in range(kwargs["limit"])
            ]

    monkeypatch.setattr("huggingface_hub.HfApi", FakeHfApi)
    runtime = LocalModelRuntime(SimpleNamespace(), tmp_path / "models")
    result = runtime.search(
        "model", "text-generation", page=2, page_size=18, sort="likes"
    )

    assert captured["sort"] == "likes"
    assert captured["limit"] == 37
    assert result["items"][0]["id"] == "org/model-18"
    assert result["items"][-1]["id"] == "org/model-35"
    assert result["pagination"] == {
        "page": 2,
        "page_size": 18,
        "has_previous": True,
        "has_next": True,
        "start": 19,
        "end": 36,
    }


def test_diffusion_repository_resolves_official_diffusers_variant(monkeypatch, tmp_path):
    class FakeHfApi:
        def __init__(self, token=None):
            pass

        def model_info(self, repository_id, revision):
            files = (
                [SimpleNamespace(rfilename="model_index.json")]
                if repository_id.endswith("_diffusers")
                else [SimpleNamespace(rfilename="checkpoints/model.pth")]
            )
            return SimpleNamespace(siblings=files)

    monkeypatch.setattr("huggingface_hub.HfApi", FakeHfApi)
    runtime = LocalModelRuntime(SimpleNamespace(), tmp_path / "models")

    assert runtime._resolve_download_repository(
        "org/image-model", "main", "text-to-image", ""
    ) == "org/image-model_diffusers"


def test_diffusion_repository_rejects_non_executable_checkpoint(monkeypatch, tmp_path):
    class FakeHfApi:
        def __init__(self, token=None):
            pass

        def model_info(self, repository_id, revision):
            if repository_id == "org/image-model":
                return SimpleNamespace(
                    siblings=[SimpleNamespace(rfilename="checkpoints/model.pth")]
                )
            raise RuntimeError("not found")

    monkeypatch.setattr("huggingface_hub.HfApi", FakeHfApi)
    runtime = LocalModelRuntime(SimpleNamespace(), tmp_path / "models")

    try:
        runtime._resolve_download_repository(
            "org/image-model", "main", "text-to-image", ""
        )
    except RuntimeError as exc:
        assert "model_index.json ausente" in str(exc)
    else:
        raise AssertionError("Um checkpoint bruto não pode ser marcado como executável.")


def test_diffusion_repository_replaces_mlx_with_declared_diffusers_base(monkeypatch, tmp_path):
    class FakeHfApi:
        def __init__(self, token=None):
            pass

        def model_info(self, repository_id, revision):
            if repository_id == "org/model-mlx":
                return SimpleNamespace(
                    siblings=[SimpleNamespace(rfilename="model_index.json")],
                    library_name="mlx",
                    tags=["mlx", "image-to-video"],
                    card_data=SimpleNamespace(base_model="org/model-diffusers"),
                )
            assert repository_id == "org/model-diffusers"
            return SimpleNamespace(
                siblings=[SimpleNamespace(rfilename="model_index.json")],
                library_name="diffusers",
                tags=["diffusers:WanPipeline"],
                card_data=None,
            )

    monkeypatch.setattr("huggingface_hub.HfApi", FakeHfApi)
    runtime = LocalModelRuntime(SimpleNamespace(), tmp_path / "models")

    assert runtime._resolve_download_repository(
        "org/model-mlx", "main", "image-to-video", ""
    ) == "org/model-diffusers"


def test_wan_dmd_pipeline_uses_supported_task_specific_replacement(tmp_path):
    source = tmp_path / "wan"
    source.mkdir()
    (source / "model_index.json").write_text(
        json.dumps({"_class_name": "WanDMDPipeline"}), encoding="utf-8"
    )

    with __import__("pytest").warns(RuntimeWarning, match="WanImageToVideoPipeline"):
        pipeline_class = LocalModelRuntime._diffusers_pipeline_class(
            str(source), "image-to-video"
        )

    assert pipeline_class.__name__ == "WanImageToVideoPipeline"


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


def test_local_runtime_keeps_only_the_latest_model_loaded(tmp_path):
    released = threading.Event()
    offloaded = []

    class Store:
        def get_local_model(self, model_id, workspace_id):
            return {
                "id": model_id,
                "workspace_id": workspace_id,
                "repository_id": f"org/{model_id}",
                "task": "text-generation",
                "status": "ready",
                "options": {},
            }

    class Pipeline:
        def __call__(self, value, **_parameters):
            return value

        def to(self, device):
            offloaded.append(device)
            return self

    runtime = LocalModelRuntime(Store(), tmp_path / "models")
    pipeline = Pipeline()
    weakref.finalize(pipeline, released.set)
    runtime._pipelines["model-text"] = pipeline
    del pipeline

    assert runtime.infer(
        model_id="model-text", workspace_id="ws-1", value="texto"
    ) == "texto"
    runtime._pipelines["model-image"] = lambda value, **_parameters: value
    assert runtime.infer(
        model_id="model-image", workspace_id="ws-1", value="imagem"
    ) == "imagem"

    assert set(runtime._pipelines) == {"model-image"}
    assert "model-text" not in runtime._idle_timers
    assert offloaded == []
    assert released.wait(2)


def test_local_runtime_warns_but_does_not_block_memory_pressure(tmp_path, monkeypatch):
    model_path = tmp_path / "oversized-model"
    model_path.mkdir()
    (model_path / "model.safetensors").write_bytes(b"x" * 100)
    monkeypatch.setattr(LocalModelRuntime, "_available_system_memory", staticmethod(lambda: 50))

    import pytest

    with pytest.warns(RuntimeWarning, match="tentará carregar"):
        notices = LocalModelRuntime._ensure_memory_capacity(
            model_path, {"backend": "cpu", "device": -1, "devices": []}
        )
    assert len(notices) == 1
    assert "não representa a VRAM" in notices[0]


def test_local_runtime_never_copies_model_to_cpu_while_unloading():
    calls = []

    class Pipeline:
        def to(self, device):
            calls.append(device)

    instances = [Pipeline()]
    LocalModelRuntime._release_instances(instances)

    assert instances == []
    assert calls == []


def test_local_runtime_processes_distinct_models_in_fifo_order(tmp_path, monkeypatch):
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    call_order = []

    class Store:
        def get_local_model(self, model_id, workspace_id):
            return {
                "id": model_id,
                "workspace_id": workspace_id,
                "repository_id": f"org/{model_id}",
                "task": "text-generation",
                "status": "ready",
                "options": {},
            }

    class Pipeline:
        def __init__(self, model_id):
            self.model_id = model_id

        def __call__(self, value, **_parameters):
            call_order.append(self.model_id)
            if self.model_id == "model-a":
                first_started.set()
                assert release_first.wait(2)
            else:
                second_started.set()
            return value

    runtime = LocalModelRuntime(Store(), tmp_path / "models")

    def load_pipeline(model):
        model_id = str(model["id"])
        instance = runtime._pipelines.get(model_id)
        if instance is None:
            instance = Pipeline(model_id)
            runtime._pipelines[model_id] = instance
        return instance

    monkeypatch.setattr(runtime, "_pipeline", load_pipeline)
    first = threading.Thread(
        target=lambda: runtime.infer(
            model_id="model-a", workspace_id="ws-1", value="a"
        )
    )
    second = threading.Thread(
        target=lambda: runtime.infer(
            model_id="model-b", workspace_id="ws-1", value="b"
        )
    )

    first.start()
    assert first_started.wait(2)
    second.start()
    assert not second_started.wait(0.1)
    release_first.set()
    first.join(2)
    second.join(2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert call_order == ["model-a", "model-b"]
    assert set(runtime._pipelines) == {"model-b"}


def test_local_model_catalog_exposes_all_modalities(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    bootstrap(client)
    tasks = {item["task"] for item in client.get("/api/local-model-tasks").json()}
    assert {
        "text-generation",
        "image-text-to-text",
        "image-to-text",
        "automatic-speech-recognition",
        "text-to-audio",
        "text-to-image",
        "image-to-3d",
        "text-to-3d",
    }.issubset(tasks)
    catalog = {item["type"] for item in client.get("/api/catalog").json()}
    assert {"local_model", "audio_input", "image_preview"}.issubset(catalog)


def test_multimodal_text_model_receives_generated_image_and_prompt(tmp_path):
    from PIL import Image

    model_path = tmp_path / "vision-llm"
    model_path.mkdir()
    (model_path / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen2_5_vl",
                "architectures": ["Qwen2_5_VLForConditionalGeneration"],
                "vision_config": {"hidden_size": 32},
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    class Pipeline:
        def __call__(self, *args, **kwargs):
            captured.update(args=args, kwargs=kwargs)
            return [{"generated_text": "A imagem foi analisada."}]

    class Store:
        def get_local_model(self, model_id, workspace_id):
            return {
                "id": model_id,
                "workspace_id": workspace_id,
                "repository_id": "org/vision-llm",
                "local_path": str(model_path),
                "task": "text-generation",
                "status": "ready",
                "options": {},
            }

    image = Image.new("RGB", (2, 2), "#7657ff")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image_uri = "data:image/png;base64," + base64.b64encode(
        buffer.getvalue()
    ).decode()
    runtime = LocalModelRuntime(Store(), tmp_path / "models")
    runtime._pipelines["vision"] = Pipeline()

    result = runtime.infer(
        model_id="vision",
        workspace_id="ws-1",
        value={
            "images": [{"data_uri": image_uri}],
            "vision_prompt": "Identifique problemas nesta imagem.",
        },
    )

    assert result[0]["generated_text"] == "A imagem foi analisada."
    assert captured["args"] == ()
    assert isinstance(captured["kwargs"]["images"], Image.Image)
    assert captured["kwargs"]["text"] == "Identifique problemas nesta imagem."


def test_multimodal_chat_template_receives_image_inside_message(tmp_path):
    from PIL import Image

    captured = {}

    class Processor:
        chat_template = "{{ messages }}"

    class Pipeline:
        processor = Processor()

        def __call__(self, *args, **kwargs):
            captured.update(args=args, kwargs=kwargs)
            return [{"generated_text": "Imagem analisada"}]

    image = Image.new("RGB", (4, 4), "#7657ff")
    result = LocalModelRuntime._run_image_text_pipeline(
        Pipeline(),
        {"images": image, "text": "Avalie a imagem."},
        {"max_new_tokens": 32},
    )

    messages = captured["kwargs"]["text"]
    assert result[0]["generated_text"] == "Imagem analisada"
    assert captured["args"] == ()
    assert "images" not in captured["kwargs"]
    assert captured["kwargs"]["return_full_text"] is False
    assert captured["kwargs"]["max_new_tokens"] == 32
    assert messages[0]["role"] == "user"
    assert messages[0]["content"][0]["type"] == "image"
    assert messages[0]["content"][0]["image"] is image
    assert messages[0]["content"][1] == {"type": "text", "text": "Avalie a imagem."}


def test_generated_image_flows_directly_into_local_vision_llm_node(tmp_path):
    app = create_app(tmp_path / "image-review.db")
    client = TestClient(app)
    bootstrap(client)
    generator = client.post(
        "/api/local-models",
        json={"repository_id": "org/generator", "task": "text-to-image", "download": False},
    ).json()
    reviewer = client.post(
        "/api/local-models",
        json={"repository_id": "org/reviewer", "task": "image-text-to-text", "download": False},
    ).json()
    image_uri = "data:image/png;base64,iVBORw0KGgo="
    reviewed = {}

    def infer(**kwargs):
        if kwargs["model_id"] == generator["id"]:
            return {"images": [{"data_uri": image_uri}]}
        reviewed.update(kwargs["value"])
        return [{"generated_text": "A composição precisa de mais contraste."}]

    app.state.local_model_runtime.infer = infer
    workflow = client.post(
        "/api/workflows",
        json={
            "name": "Gerar e revisar imagem",
            "nodes": [
                {"id": "input", "type": "text_input", "name": "Prompt", "config": {"input_key": "prompt"}},
                {"id": "generate", "type": "local_model", "name": "Gerar", "config": {"model_id": generator["id"]}},
                {
                    "id": "review",
                    "type": "local_model",
                    "name": "Avaliar imagem",
                    "config": {
                        "model_id": reviewer["id"],
                        "vision_prompt": "Explique o que está errado na imagem.",
                    },
                },
                {"id": "output", "type": "output", "name": "Análise", "config": {}},
            ],
            "edges": [
                {"id": "e1", "source": "input", "target": "generate"},
                {"id": "e2", "source": "generate", "source_handle": "image", "target": "review"},
                {"id": "e3", "source": "review", "target": "output"},
            ],
        },
    ).json()

    result = client.post(
        f"/api/workflows/{workflow['id']}/run",
        json={"input": {"prompt": "uma cidade futurista"}},
    )

    assert result.status_code == 200
    assert reviewed["image"]["data_uri"] == image_uri
    assert reviewed["vision_prompt"] == "Explique o que está errado na imagem."
    assert result.json()["output"][0]["generated_text"].startswith("A composição")


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
    release = client.post(f"/api/workflows/{workflow['id']}/release-models")
    assert release.status_code == 200
    assert release.json()["unloaded"] == 1
    assert model["id"] not in app.state.local_model_runtime._pipelines


def test_local_model_is_unloaded_after_idle_timeout(tmp_path):
    released = threading.Event()

    class Pipeline:
        def __call__(self, value, **_parameters):
            return [{"generated_text": value}]

    class Store:
        def get_local_model(self, model_id, workspace_id):
            return {
                "id": model_id,
                "workspace_id": workspace_id,
                "repository_id": "org/tiny",
                "task": "text-generation",
                "status": "ready",
                "options": {},
            }

    runtime = LocalModelRuntime(Store(), tmp_path / "models")
    pipeline = Pipeline()
    weakref.finalize(pipeline, released.set)
    runtime._pipelines["mdl-idle"] = pipeline
    del pipeline
    assert runtime.infer(
        model_id="mdl-idle",
        workspace_id="ws-1",
        value="olá",
        usage_scope="wf-idle",
    )[0]["generated_text"] == "olá"
    assert "mdl-idle" in runtime._idle_timers

    runtime._idle_unload("mdl-idle")

    assert "mdl-idle" not in runtime._pipelines
    assert "mdl-idle" not in runtime._usage_scopes
    assert released.wait(2)


def test_leaving_workflow_waits_for_active_inference_before_unloading(tmp_path):
    started = threading.Event()
    finish = threading.Event()
    released = threading.Event()

    class Pipeline:
        def __call__(self, value, **_parameters):
            started.set()
            assert finish.wait(2)
            return [{"generated_text": value}]

    class Store:
        def get_local_model(self, model_id, workspace_id):
            return {
                "id": model_id,
                "workspace_id": workspace_id,
                "repository_id": "org/tiny",
                "task": "text-generation",
                "status": "ready",
                "options": {},
            }

    runtime = LocalModelRuntime(Store(), tmp_path / "models")
    pipeline = Pipeline()
    weakref.finalize(pipeline, released.set)
    runtime._pipelines["mdl-active"] = pipeline
    del pipeline
    worker = threading.Thread(
        target=lambda: runtime.infer(
            model_id="mdl-active",
            workspace_id="ws-1",
            value="olá",
            usage_scope="wf-active",
        )
    )
    worker.start()
    assert started.wait(2)

    assert runtime.release_scope("wf-active") == 0
    assert "mdl-active" in runtime._pipelines
    finish.set()
    worker.join(2)

    assert not worker.is_alive()
    assert released.wait(2)
    assert "mdl-active" not in runtime._pipelines


def test_generated_images_flow_into_canvas_preview_node(tmp_path):
    app = create_app(tmp_path / "image-preview.db")
    client = TestClient(app)
    bootstrap(client)
    model = client.post(
        "/api/local-models",
        json={
            "repository_id": "org/tiny-image-model",
            "task": "text-to-image",
            "download": False,
        },
    ).json()
    image_uri = "data:image/png;base64,iVBORw0KGgo="
    app.state.local_model_runtime.infer = lambda **_kwargs: {
        "images": [{"data_uri": image_uri}]
    }
    workflow = client.post(
        "/api/workflows",
        json={
            "name": "Preview de imagem",
            "nodes": [
                {"id": "input", "type": "text_input", "name": "Prompt", "config": {"input_key": "prompt"}},
                {
                    "id": "model",
                    "type": "local_model",
                    "name": "Gerar imagem",
                    "config": {"model_id": model["id"], "input_field": "prompt"},
                },
                {
                    "id": "preview",
                    "type": "image_preview",
                    "name": "Visualizar imagem",
                    "config": {"input_field": "images", "output_field": "preview_image"},
                },
                {"id": "output", "type": "output", "name": "Saída", "config": {"field": "preview_image"}},
            ],
            "edges": [
                {"id": "e1", "source": "input", "target": "model"},
                {"id": "e2", "source": "model", "source_handle": "image", "target": "preview"},
                {"id": "e3", "source": "preview", "target": "output"},
            ],
        },
    ).json()

    result = client.post(
        f"/api/workflows/{workflow['id']}/run",
        json={"input": {"prompt": "uma cidade futurista"}},
    )

    assert result.status_code == 200
    assert result.json()["output"] == {"images": [{"data_uri": image_uri}]}
    preview_event = next(
        event for event in result.json()["events"] if event["node_id"] == "preview"
    )
    assert preview_event["output"]["images"][0]["data_uri"] == image_uri
