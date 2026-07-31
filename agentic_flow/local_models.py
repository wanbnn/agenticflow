from __future__ import annotations

import base64
import gc
import io
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from .media import decode_asset


LOCAL_MODEL_TASKS = [
    {"task": "text-generation", "name": "LLM / geração de texto", "modality": "llm"},
    {"task": "image-to-text", "name": "Visão / imagem para texto", "modality": "vision"},
    {"task": "automatic-speech-recognition", "name": "Áudio para texto", "modality": "audio"},
    {"task": "text-to-audio", "name": "Texto para áudio", "modality": "audio"},
    {"task": "text-to-image", "name": "Geração de imagem", "modality": "image"},
    {"task": "image-to-3d", "name": "Imagem para 3D", "modality": "3d"},
    {"task": "text-to-3d", "name": "Texto para 3D", "modality": "3d"},
    {"task": "feature-extraction", "name": "Embeddings", "modality": "embedding"},
]
LOCAL_MODEL_TASK_NAMES = {item["task"] for item in LOCAL_MODEL_TASKS}


def _data_uri(payload: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class LocalModelRuntime:
    """Downloads and serves Hugging Face models without a separate inference SaaS."""

    def __init__(self, store, cache_dir: str | Path):
        self.store = store
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._pipelines: dict[str, Any] = {}
        self._lock = threading.RLock()

    @staticmethod
    def hardware() -> dict[str, Any]:
        result: dict[str, Any] = {"backend": "cpu", "available": True, "devices": []}
        try:
            import torch

            result["torch_version"] = torch.__version__
            result["rocm_version"] = getattr(torch.version, "hip", None)
            if torch.cuda.is_available():
                result["backend"] = "rocm" if result["rocm_version"] else "cuda"
                result["devices"] = [
                    {"index": index, "name": torch.cuda.get_device_name(index)}
                    for index in range(torch.cuda.device_count())
                ]
            result["device"] = 0 if torch.cuda.is_available() else -1
        except ImportError:
            result.update(
                available=False,
                error="Instale o extra self-hosted e o pacote PyTorch adequado ao hardware.",
            )
        return result

    def search(self, query: str, task: str = "", limit: int = 20, token: str = ""):
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise RuntimeError("Instale huggingface-hub para pesquisar modelos.") from exc
        models = HfApi(token=token or None).list_models(
            search=query or None,
            pipeline_tag=task or None,
            sort="downloads",
            direction=-1,
            limit=min(max(limit, 1), 50),
        )
        return [
            {
                "id": item.id,
                "task": getattr(item, "pipeline_tag", None),
                "downloads": getattr(item, "downloads", 0) or 0,
                "likes": getattr(item, "likes", 0) or 0,
                "private": bool(getattr(item, "private", False)),
            }
            for item in models
        ]

    def install(self, model_id: str, workspace_id: str, token: str = "") -> None:
        model = self.store.get_local_model(model_id, workspace_id)
        if not model:
            return
        try:
            from huggingface_hub import snapshot_download

            target = self.cache_dir / model_id
            target.mkdir(parents=True, exist_ok=True)
            path = snapshot_download(
                repo_id=str(model["repository_id"]),
                revision=str(model["revision"]),
                token=token or None,
                local_dir=target,
            )
            self.store.update_local_model(
                model_id, workspace_id, status="ready", local_path=str(Path(path).resolve())
            )
        except Exception as exc:
            self.store.update_local_model(
                model_id,
                workspace_id,
                status="error",
                error=" ".join(str(exc).split())[:1000],
            )

    def _pipeline(self, model: dict[str, Any]):
        model_id = str(model["id"])
        with self._lock:
            if model_id in self._pipelines:
                return self._pipelines[model_id]
            try:
                from transformers import pipeline
            except ImportError as exc:
                raise RuntimeError(
                    "Instale o extra agentic-flow[self-hosted] para executar modelos locais."
                ) from exc
            source = str(model.get("local_path") or model["repository_id"])
            options = dict(model.get("options") or {})
            pipeline_options = dict(options.get("pipeline_options") or {})
            pipeline_options.setdefault("trust_remote_code", bool(options.get("trust_remote_code", False)))
            hardware = self.hardware()
            if str(model["task"]) in {"text-to-image", "image-to-3d", "text-to-3d"}:
                try:
                    from diffusers import DiffusionPipeline
                except ImportError as exc:
                    raise RuntimeError("Instale diffusers para executar modelos de imagem ou 3D.") from exc
                instance = DiffusionPipeline.from_pretrained(source, **pipeline_options)
                instance.to("cuda" if hardware.get("device") == 0 else "cpu")
                self._pipelines[model_id] = instance
                return instance
            pipeline_options.setdefault("device", hardware.get("device", -1))
            instance = pipeline(str(model["task"]), model=source, **pipeline_options)
            self._pipelines[model_id] = instance
            return instance

    @staticmethod
    def _prepare_input(task: str, value: Any) -> tuple[Any, str]:
        temp_path = ""
        if task == "image-to-text" or task == "image-to-3d":
            from PIL import Image

            payload, _, _ = decode_asset(value, default_name="image.png")
            return Image.open(io.BytesIO(payload)).convert("RGB"), temp_path
        if task == "automatic-speech-recognition":
            payload, name, _ = decode_asset(value, default_name="audio.wav")
            suffix = Path(name).suffix or ".wav"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                temporary.write(payload)
                temp_path = temporary.name
            return temp_path, temp_path
        return value, temp_path

    @staticmethod
    def _serialize(value: Any) -> Any:
        for attribute in ("images", "audios", "frames", "meshes"):
            if hasattr(value, attribute):
                return {attribute: LocalModelRuntime._serialize(getattr(value, attribute))}
        try:
            from PIL import Image

            if isinstance(value, Image.Image):
                output = io.BytesIO()
                value.save(output, format="PNG")
                return {"data_uri": _data_uri(output.getvalue(), "image/png")}
        except ImportError:
            pass
        if isinstance(value, list):
            return [LocalModelRuntime._serialize(item) for item in value]
        if isinstance(value, dict) and "audio" in value and (
            "sampling_rate" in value or "sample_rate" in value
        ):
            rate = int(value.get("sampling_rate") or value.get("sample_rate"))
            try:
                import soundfile as sf

                output = io.BytesIO()
                sf.write(output, value["audio"], rate, format="WAV")
                return {"data_uri": _data_uri(output.getvalue(), "audio/wav"), "sample_rate": rate}
            except ImportError:
                pass
        if isinstance(value, tuple) and len(value) == 2:
            audio, rate = value
            try:
                import soundfile as sf

                output = io.BytesIO()
                sf.write(output, audio, int(rate), format="WAV")
                return {"data_uri": _data_uri(output.getvalue(), "audio/wav"), "sample_rate": rate}
            except ImportError:
                return {"audio": getattr(audio, "tolist", lambda: audio)(), "sample_rate": rate}
        if isinstance(value, dict):
            return {key: LocalModelRuntime._serialize(item) for key, item in value.items()}
        if hasattr(value, "export"):
            output = io.BytesIO()
            value.export(output, file_type="glb")
            return {"data_uri": _data_uri(output.getvalue(), "model/gltf-binary")}
        if hasattr(value, "tolist"):
            return value.tolist()
        return value

    def infer(
        self,
        *,
        model_id: str,
        workspace_id: str,
        value: Any,
        parameters: dict[str, Any] | None = None,
    ) -> Any:
        model = self.store.get_local_model(model_id, workspace_id)
        if not model:
            raise RuntimeError("Modelo local não encontrado.")
        if model["status"] != "ready":
            raise RuntimeError(f"O modelo local ainda não está pronto (status: {model['status']}).")
        instance = self._pipeline(model)
        prepared, temp_path = self._prepare_input(str(model["task"]), value)
        try:
            return self._serialize(instance(prepared, **(parameters or {})))
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)

    def chat(self, *, model_id: str, workspace_id: str, instructions: str, prompt: str, temperature: float) -> str:
        text = f"{instructions}\n\n{prompt}" if instructions else prompt
        result = self.infer(
            model_id=model_id,
            workspace_id=workspace_id,
            value=text,
            parameters={"temperature": temperature, "return_full_text": False},
        )
        if isinstance(result, list) and result:
            result = result[0]
        if isinstance(result, dict):
            return str(result.get("generated_text") or result.get("text") or result)
        return str(result)

    def unload(self, model_id: str) -> bool:
        with self._lock:
            removed = self._pipelines.pop(model_id, None) is not None
        if removed:
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
        return removed

    def remove_files(self, model: dict[str, Any]) -> None:
        self.unload(str(model["id"]))
        path = Path(str(model.get("local_path") or self.cache_dir / str(model["id"]))).resolve()
        if path != self.cache_dir and self.cache_dir in path.parents and path.exists():
            shutil.rmtree(path)
