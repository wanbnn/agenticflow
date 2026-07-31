import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

from agentic_flow.llama_cpp import LlamaCppManager
from agentic_flow.local_models import LocalModelRuntime
from PIL import Image


def test_llama_cpp_selects_hip_cuda_vulkan_and_cpu_assets(tmp_path):
    manager = LlamaCppManager(tmp_path)
    release = {
        "assets": [
            {"name": "llama-b1-bin-win-hip-radeon-x64.zip"},
            {"name": "llama-b1-bin-win-cuda-12.4-x64.zip"},
            {"name": "cudart-llama-bin-win-cuda-12.4-x64.zip"},
            {"name": "llama-b1-bin-win-vulkan-x64.zip"},
            {"name": "llama-b1-bin-win-cpu-x64.zip"},
        ]
    }

    assert [item["name"] for item in manager._select_assets(release, "hip")] == [
        "llama-b1-bin-win-hip-radeon-x64.zip"
    ]
    assert [item["name"] for item in manager._select_assets(release, "cuda")] == [
        "llama-b1-bin-win-cuda-12.4-x64.zip",
        "cudart-llama-bin-win-cuda-12.4-x64.zip",
    ]
    assert manager._select_assets(release, "vulkan")[0]["name"].endswith("vulkan-x64.zip")
    assert manager._select_assets(release, "cpu")[0]["name"].endswith("cpu-x64.zip")


def test_llama_cpp_rejects_archive_path_traversal(tmp_path):
    archive = tmp_path / "unsafe.zip"
    destination = tmp_path / "runtime"
    destination.mkdir()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.exe", "unsafe")

    try:
        LlamaCppManager._safe_extract(archive, destination)
    except RuntimeError as exc:
        assert "inseguro" in str(exc)
    else:
        raise AssertionError("A extração deveria bloquear caminhos fora do destino")
    assert not (tmp_path / "escape.exe").exists()


def test_gguf_catalog_groups_shards_and_marks_quantization(monkeypatch, tmp_path):
    siblings = [
        SimpleNamespace(rfilename="model-Q4_K_M-00001-of-00002.gguf", size=100),
        SimpleNamespace(rfilename="model-Q4_K_M-00002-of-00002.gguf", size=120),
        SimpleNamespace(rfilename="model-Q8_0.gguf", size=400),
        SimpleNamespace(rfilename="mmproj-model-f16.gguf", size=50),
        SimpleNamespace(rfilename="config.json", size=10),
    ]

    class FakeApi:
        def __init__(self, token=None):
            assert token == "hf_token"

        def model_info(self, repository_id, revision, files_metadata):
            assert (repository_id, revision, files_metadata) == ("org/model-GGUF", "main", True)
            return SimpleNamespace(siblings=siblings)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(HfApi=FakeApi))
    runtime = LocalModelRuntime(SimpleNamespace(), tmp_path / "models")

    catalog = runtime.gguf_variants("org/model-GGUF", token="hf_token")

    assert len(catalog["variants"]) == 2
    q4 = next(item for item in catalog["variants"] if item["quantization"] == "Q4_K_M")
    assert q4["size_bytes"] == 220
    assert len(q4["files"]) == 2
    assert q4["recommended"] is True
    assert catalog["mmproj_files"][0]["name"] == "mmproj-model-f16.gguf"


def test_gguf_install_downloads_only_selected_files(monkeypatch, tmp_path):
    downloads = []

    def hf_hub_download(**kwargs):
        downloads.append(kwargs["filename"])
        target = Path(kwargs["local_dir"]) / kwargs["filename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"gguf")
        return str(target)

    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_download=hf_hub_download)
    )

    class Store:
        def __init__(self):
            self.updated = None

        def get_local_model(self, model_id, workspace_id):
            return {
                "id": model_id,
                "repository_id": "org/model-GGUF",
                "revision": "main",
                "task": "text-generation",
                "options": {
                    "runtime": "llama_cpp",
                    "quantization": "Q4_K_M",
                    "gguf_file": "model-Q4_K_M-00001-of-00002.gguf",
                    "gguf_files": [
                        "model-Q4_K_M-00001-of-00002.gguf",
                        "model-Q4_K_M-00002-of-00002.gguf",
                    ],
                },
            }

        def update_local_model(self, *args, **kwargs):
            self.updated = (args, kwargs)

    store = Store()
    runtime = LocalModelRuntime(store, tmp_path / "models")
    runtime.install("mdl-1", "ws-1")

    assert downloads == [
        "model-Q4_K_M-00001-of-00002.gguf",
        "model-Q4_K_M-00002-of-00002.gguf",
    ]
    assert store.updated[1]["status"] == "ready"
    assert store.updated[1]["local_path"].endswith("model-Q4_K_M-00001-of-00002.gguf")


def test_diffusers_video_frames_are_serialized_for_canvas_preview():
    frames = [Image.new("RGB", (32, 24), (index * 20, 10, 30)) for index in range(3)]

    serialized = LocalModelRuntime._serialize(SimpleNamespace(frames=[frames]))

    assert serialized["video"]["data_uri"].startswith("data:video/mp4;base64,")
    assert serialized["video"]["fps"] == 8
