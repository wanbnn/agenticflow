from __future__ import annotations

import base64
import ctypes
import gc
import io
import json
import os
import re
import shutil
import tempfile
import threading
import warnings
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .llama_cpp import LlamaCppManager, QUANTIZATION_RE, SHARD_RE
from .media import decode_asset


LOCAL_MODEL_TASKS = [
    {"task": "text-generation", "name": "LLM / geração de texto", "modality": "llm"},
    {"task": "image-text-to-text", "name": "LLM multimodal / imagem + texto", "modality": "vision"},
    {"task": "image-to-text", "name": "Visão / imagem para texto", "modality": "vision"},
    {"task": "automatic-speech-recognition", "name": "Áudio para texto", "modality": "audio"},
    {"task": "text-to-audio", "name": "Texto para áudio", "modality": "audio"},
    {"task": "text-to-image", "name": "Geração de imagem", "modality": "image"},
    {"task": "text-to-video", "name": "Texto para vídeo", "modality": "video"},
    {"task": "image-to-video", "name": "Imagem para vídeo", "modality": "video"},
    {"task": "image-to-3d", "name": "Imagem para 3D", "modality": "3d"},
    {"task": "text-to-3d", "name": "Texto para 3D", "modality": "3d"},
    {"task": "feature-extraction", "name": "Embeddings", "modality": "embedding"},
]
LOCAL_MODEL_TASK_NAMES = {item["task"] for item in LOCAL_MODEL_TASKS}
LOCAL_MODEL_SORTS = {
    "trending": "trending_score",
    "downloads": "downloads",
    "likes": "likes",
    "updated": "last_modified",
}
DIFFUSION_TASKS = {
    "text-to-image", "text-to-video", "image-to-video", "image-to-3d", "text-to-3d"
}
TASK_MODALITIES = {
    "text-generation": ({"text"}, {"text"}),
    "image-text-to-text": ({"image", "text"}, {"text"}),
    "image-to-text": ({"image"}, {"text"}),
    "automatic-speech-recognition": ({"audio"}, {"text"}),
    "text-to-audio": ({"text"}, {"audio"}),
    "text-to-image": ({"text"}, {"image"}),
    "text-to-video": ({"text"}, {"video"}),
    "image-to-video": ({"image"}, {"video"}),
    "image-to-3d": ({"image"}, {"3d"}),
    "text-to-3d": ({"text"}, {"3d"}),
    "feature-extraction": ({"text"}, {"embedding"}),
}
VISION_MARKERS = (
    "vision", "visual", "llava", "mllama", "paligemma", "idefics",
    "florence", "qwen2_vl", "qwen2_5_vl", "qwen3_vl", "internvl", "minicpmv",
)
INCOMPATIBLE_DIFFUSERS_LIBRARIES = {"mlx", "coreml"}
DIFFUSERS_PIPELINE_ALIASES = {
    "WanDMDPipeline": {
        "image-to-video": "WanImageToVideoPipeline",
        "default": "WanPipeline",
    },
}


def _data_uri(payload: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class LocalModelRuntime:
    """Downloads and serves Hugging Face models without a separate inference SaaS."""

    def __init__(
        self,
        store,
        cache_dir: str | Path,
        idle_seconds: float | None = None,
    ):
        self.store = store
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.llama_cpp = LlamaCppManager(self.cache_dir.parent / "llama.cpp")
        self._pipelines: dict[str, Any] = {}
        self._lock = threading.RLock()
        self.idle_seconds = max(
            1.0,
            float(
                idle_seconds
                if idle_seconds is not None
                else os.getenv("AGENTIC_FLOW_MODEL_IDLE_SECONDS", "60")
            ),
        )
        self._active_inferences: dict[str, int] = {}
        self._usage_scopes: dict[str, set[str]] = {}
        self._idle_timers: dict[str, threading.Timer] = {}
        self._release_when_idle: set[str] = set()
        self._queue_condition = threading.Condition()
        self._next_queue_ticket = 0
        self._serving_queue_ticket = 0

    @staticmethod
    def hardware() -> dict[str, Any]:
        result: dict[str, Any] = {"backend": "cpu", "available": True, "devices": []}
        try:
            import torch

            result["torch_version"] = torch.__version__
            result["rocm_version"] = getattr(torch.version, "hip", None)
            if torch.cuda.is_available():
                result["backend"] = "rocm" if result["rocm_version"] else "cuda"
                devices = []
                for index in range(torch.cuda.device_count()):
                    device = {
                        "index": index,
                        "name": torch.cuda.get_device_name(index),
                        "total_memory_bytes": torch.cuda.get_device_properties(index).total_memory,
                    }
                    try:
                        free_bytes, _ = torch.cuda.mem_get_info(index)
                        device["free_memory_bytes"] = int(free_bytes)
                    except RuntimeError:
                        pass
                    devices.append(device)
                result["devices"] = devices
            result["device"] = 0 if torch.cuda.is_available() else -1
        except ImportError:
            result.update(
                available=False,
                error="Instale o extra self-hosted e o pacote PyTorch adequado ao hardware.",
            )
        return result

    @staticmethod
    def _configure_acceleration() -> dict[str, Any]:
        """Prefer stable kernels for self-hosted inference, especially on Windows ROCm."""
        hardware = LocalModelRuntime.hardware()
        if hardware.get("backend") != "rocm":
            return hardware
        os.environ.setdefault("TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL", "0")
        try:
            import torch

            backend = getattr(torch.backends, "cuda", None)
            if backend is not None:
                for name, enabled in (
                    ("enable_flash_sdp", False),
                    ("enable_mem_efficient_sdp", False),
                    ("enable_math_sdp", True),
                ):
                    switch = getattr(backend, name, None)
                    if callable(switch):
                        switch(enabled)
        except (ImportError, RuntimeError):
            pass
        return hardware

    @staticmethod
    def _available_system_memory() -> int:
        try:
            import psutil

            return int(psutil.virtual_memory().available)
        except ImportError:
            pass
        if os.name == "nt":
            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.available_physical)
        return 0

    @staticmethod
    def _model_weight_bytes(source: str | Path) -> int:
        root = Path(source)
        if not root.is_dir():
            return 0
        weight_files = {
            path.resolve()
            for pattern in ("*.safetensors", "*.bin", "*.gguf")
            for path in root.rglob(pattern)
            if path.is_file()
        }
        return sum(path.stat().st_size for path in weight_files)

    @classmethod
    def _ensure_memory_capacity(
        cls, source: str | Path, hardware: dict[str, Any]
    ) -> list[str]:
        """Report memory pressure without preventing an attempted model load."""
        weight_bytes = cls._model_weight_bytes(source)
        if not weight_bytes:
            return []
        gib = 1024 ** 3
        notices = []
        available_ram = cls._available_system_memory()
        required_ram = int(weight_bytes * 1.05)
        if available_ram and required_ram > available_ram:
            notices.append(
                "O modelo precisa de aproximadamente "
                f"{required_ram / gib:.1f} GB considerando o tamanho dos pesos, enquanto há "
                f"{available_ram / gib:.1f} GB de RAM livres. Este valor não representa a "
                "VRAM disponível e é apenas uma estimativa; o AgenticFlow tentará carregar "
                "o modelo normalmente."
            )
        devices = hardware.get("devices") or []
        if hardware.get("device") == 0 and devices:
            free_vram = int(devices[0].get("free_memory_bytes") or 0)
            required_vram = int(weight_bytes * 1.20)
            if free_vram and required_vram > int(free_vram * 0.95):
                notices.append(
                    "O modelo pode usar aproximadamente "
                    f"{required_vram / gib:.1f} GB de VRAM com margem operacional, mas há "
                    f"{free_vram / gib:.1f} GB livres. O carregamento continuará e o runtime "
                    "poderá usar RAM, offload ou falhar se o hardware não comportar o modelo."
                )
        for notice in notices:
            warnings.warn(notice, RuntimeWarning, stacklevel=2)
        return notices

    def search(
        self,
        query: str,
        task: str = "",
        page: int = 1,
        page_size: int = 18,
        sort: str = "trending",
        token: str = "",
    ):
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise RuntimeError("Instale huggingface-hub para pesquisar modelos.") from exc
        page = max(page, 1)
        page_size = min(max(page_size, 1), 48)
        offset = (page - 1) * page_size
        fetch_limit = offset + page_size + 1
        models = HfApi(token=token or None).list_models(
            search=query or None,
            pipeline_tag=task or None,
            sort=LOCAL_MODEL_SORTS.get(sort, LOCAL_MODEL_SORTS["trending"]),
            limit=fetch_limit,
            expand=[
                "pipeline_tag",
                "downloads",
                "likes",
                "gated",
                "library_name",
                "tags",
                "safetensors",
                "lastModified",
                "trendingScore",
            ],
        )
        results = []
        for item in list(models)[offset:offset + page_size + 1]:
            tags = list(getattr(item, "tags", None) or [])
            lowered_tags = {str(tag).lower() for tag in tags}
            has_gguf = "gguf" in lowered_tags or str(item.id).lower().endswith("-gguf")
            safetensors = getattr(item, "safetensors", None)
            parameters = int(getattr(safetensors, "total", 0) or 0)
            license_name = next(
                (tag.split(":", 1)[1] for tag in tags if tag.startswith("license:")),
                "",
            )
            languages = [
                tag for tag in tags if len(tag) in {2, 3} and tag.isalpha()
            ][:5]
            results.append({
                "id": item.id,
                "task": getattr(item, "pipeline_tag", None) or task,
                "downloads": getattr(item, "downloads", 0) or 0,
                "likes": getattr(item, "likes", 0) or 0,
                "trending_score": getattr(item, "trending_score", 0) or 0,
                "private": bool(getattr(item, "private", False)),
                "gated": bool(getattr(item, "gated", False)),
                "library": getattr(item, "library_name", None) or "",
                "gguf": has_gguf,
                "runtime_format": (
                    "diffusers"
                    if task not in DIFFUSION_TASKS or "diffusers" in tags
                    else "auto-resolve"
                ),
                "parameters": parameters,
                "estimated_memory_bytes": int(parameters * 2.5) if parameters else 0,
                "license": license_name,
                "languages": languages,
                "capabilities": self._capabilities_for_task(
                    getattr(item, "pipeline_tag", None) or task, tags
                ),
                "updated_at": (
                    getattr(item, "last_modified", None).isoformat()
                    if getattr(item, "last_modified", None)
                    else None
                ),
            })
        has_next = len(results) > page_size
        return {
            "items": results[:page_size],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "has_previous": page > 1,
                "has_next": has_next,
                "start": offset + 1 if results else 0,
                "end": offset + min(len(results), page_size),
            },
            "sort": sort,
        }

    def gguf_variants(
        self, repository_id: str, revision: str = "main", token: str = ""
    ) -> dict[str, Any]:
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise RuntimeError("Instale huggingface-hub para consultar arquivos GGUF.") from exc
        info = HfApi(token=token or None).model_info(
            repository_id, revision=revision, files_metadata=True
        )
        files = []
        for sibling in getattr(info, "siblings", None) or []:
            name = str(getattr(sibling, "rfilename", "") or "")
            if not name.lower().endswith(".gguf"):
                continue
            size = int(getattr(sibling, "size", 0) or 0)
            files.append({"name": name, "size_bytes": size})
        main_files = [item for item in files if "mmproj" not in item["name"].lower()]
        mmproj_files = [item for item in files if "mmproj" in item["name"].lower()]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in main_files:
            key = SHARD_RE.sub("", item["name"])
            grouped.setdefault(key, []).append(item)
        variants = []
        for key, members in grouped.items():
            members.sort(key=lambda item: item["name"])
            match = QUANTIZATION_RE.search(Path(key).name)
            quantization = match.group(1).upper() if match else "GGUF"
            size = sum(int(item["size_bytes"]) for item in members)
            variants.append({
                "id": key,
                "quantization": quantization,
                "files": [item["name"] for item in members],
                "main_file": members[0]["name"],
                "size_bytes": size,
                "recommended": False,
                "description": self._quantization_description(quantization),
            })
        variants.sort(key=lambda item: (item["size_bytes"] or 2**63, item["quantization"]))
        if variants:
            devices = self.hardware().get("devices") or []
            memory = int(devices[0].get("total_memory_bytes") or 0) if devices else 0
            fitting = [
                item for item in variants
                if not memory or not item["size_bytes"] or item["size_bytes"] * 1.25 < memory
            ] or variants[:1]
            preference = ["Q5_K_M", "Q4_K_M", "Q4_K", "Q4_K_S", "Q4_0"]
            recommended = next(
                (item for quant in preference for item in fitting if item["quantization"] == quant),
                fitting[-1],
            )
            recommended["recommended"] = True
        return {
            "repository_id": repository_id,
            "revision": revision,
            "variants": variants,
            "mmproj_files": mmproj_files,
        }

    @staticmethod
    def _quantization_description(quantization: str) -> str:
        if quantization.startswith(("Q2", "Q3", "IQ2", "IQ3")):
            return "Menor uso de memória; perde mais qualidade."
        if quantization.startswith(("Q4", "Q5", "IQ4")):
            return "Bom equilíbrio entre qualidade, memória e velocidade."
        if quantization.startswith(("Q6", "Q8")):
            return "Mais qualidade; exige mais RAM/VRAM."
        if quantization in {"F16", "FP16", "BF16"}:
            return "Precisão alta; uso de memória muito elevado."
        return "Formato GGUF pronto para llama.cpp."

    @staticmethod
    def _capabilities_for_task(task: str, tags: list[str] | None = None) -> dict[str, Any]:
        inputs, outputs = TASK_MODALITIES.get(task, ({"text"}, {"text"}))
        inputs = set(inputs)
        lowered_tags = {str(tag).lower() for tag in (tags or [])}
        if task == "text-generation" and any(
            marker in tag
            for tag in lowered_tags
            for marker in ("multimodal", "vision-language", "image-text-to-text", "vlm")
        ):
            inputs.add("image")
        return {
            "input_modalities": sorted(inputs),
            "output_modalities": sorted(outputs),
            "multimodal": len(inputs) > 1,
        }

    @staticmethod
    def _snapshot_accepts_images(source: str | Path) -> bool:
        root = Path(source)
        if not root.is_dir():
            return False
        configs = []
        for filename in ("config.json", "processor_config.json", "preprocessor_config.json"):
            path = root / filename
            if not path.is_file():
                continue
            try:
                configs.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        for config in configs:
            if any(key in config for key in ("vision_config", "visual", "image_token_id", "image_token_index")):
                return True
            values = [
                str(config.get("model_type") or ""),
                str(config.get("image_processor_type") or ""),
                *(str(item) for item in (config.get("architectures") or [])),
            ]
            if any(marker in value.lower() for value in values for marker in VISION_MARKERS):
                return True
        return False

    @classmethod
    def capabilities(cls, model: dict[str, Any]) -> dict[str, Any]:
        task = str(model.get("task") or "text-generation")
        capabilities = cls._capabilities_for_task(task)
        configured = dict((model.get("options") or {}).get("capabilities") or {})
        inputs = set(capabilities["input_modalities"])
        outputs = set(capabilities["output_modalities"])
        inputs.update(configured.get("input_modalities") or [])
        outputs.update(configured.get("output_modalities") or [])
        source = str(model.get("local_path") or "")
        options = dict(model.get("options") or {})
        if options.get("runtime") == "llama_cpp" and options.get("mmproj_file"):
            inputs.update({"image", "text"})
        if source and cls._snapshot_accepts_images(source):
            inputs.add("image")
            if task == "text-generation":
                inputs.add("text")
        return {
            "input_modalities": sorted(inputs),
            "output_modalities": sorted(outputs),
            "multimodal": len(inputs) > 1,
        }

    @classmethod
    def describe_model(cls, model: dict[str, Any]) -> dict[str, Any]:
        described = dict(model)
        described["capabilities"] = cls.capabilities(model)
        return described

    @classmethod
    def _effective_task(cls, model: dict[str, Any]) -> str:
        task = str(model.get("task") or "text-generation")
        if task == "text-generation" and "image" in cls.capabilities(model)["input_modalities"]:
            return "image-text-to-text"
        return task

    @staticmethod
    def _has_diffusers_layout(model_info: Any) -> bool:
        return any(
            getattr(file, "rfilename", "") == "model_index.json"
            for file in (getattr(model_info, "siblings", None) or [])
        )

    @staticmethod
    def _base_model_from_info(model_info: Any) -> str:
        card_data = getattr(model_info, "card_data", None)
        value = getattr(card_data, "base_model", None) if card_data else None
        if isinstance(value, list):
            value = value[0] if value else ""
        return str(value or "")

    @staticmethod
    def _diffusers_class_from_info(model_info: Any) -> str:
        for tag in getattr(model_info, "tags", None) or []:
            if str(tag).startswith("diffusers:"):
                return str(tag).split(":", 1)[1]
        return ""

    @classmethod
    def _diffusers_info_compatible(cls, model_info: Any, task: str) -> bool:
        library = str(getattr(model_info, "library_name", "") or "").lower()
        if library in INCOMPATIBLE_DIFFUSERS_LIBRARIES:
            return False
        class_name = cls._diffusers_class_from_info(model_info)
        if not class_name:
            return True
        try:
            import diffusers
        except ImportError:
            return True
        if hasattr(diffusers, class_name):
            return True
        alias = DIFFUSERS_PIPELINE_ALIASES.get(class_name, {})
        replacement = alias.get(task) or alias.get("default")
        return bool(replacement and hasattr(diffusers, replacement))

    def _resolve_download_repository(
        self,
        repository_id: str,
        revision: str,
        task: str,
        token: str,
    ) -> str:
        if task not in DIFFUSION_TASKS:
            return repository_id
        from huggingface_hub import HfApi

        api = HfApi(token=token or None)
        info = api.model_info(repository_id, revision=revision)
        visited = set()
        candidate = repository_id
        while candidate and candidate not in visited:
            visited.add(candidate)
            if self._has_diffusers_layout(info) and self._diffusers_info_compatible(info, task):
                return candidate
            base_model = self._base_model_from_info(info)
            if not base_model:
                break
            candidate = base_model
            info = api.model_info(candidate, revision=revision)
        candidates = []
        if not repository_id.endswith(("_diffusers", "-diffusers")):
            candidates = [f"{repository_id}_diffusers", f"{repository_id}-diffusers"]
        for candidate in candidates:
            try:
                candidate_info = api.model_info(candidate, revision=revision)
            except Exception:
                continue
            if self._has_diffusers_layout(candidate_info):
                return candidate
        raise RuntimeError(
            f"O repositório {repository_id} contém pesos de treinamento, mas não um "
            "pipeline Diffusers executável (model_index.json ausente). Escolha uma "
            "variante Diffusers do modelo ou use a instalação avançada com um runtime próprio."
        )

    @staticmethod
    def _snapshot_library(source: str | Path) -> str:
        readme = Path(source) / "README.md"
        if not readme.is_file():
            return ""
        try:
            header = readme.read_text(encoding="utf-8", errors="ignore")[:4000]
        except OSError:
            return ""
        match = re.search(r"(?m)^library_name:\s*([^\s#]+)", header)
        return match.group(1).strip().lower() if match else ""

    @classmethod
    def _snapshot_needs_compatible_runtime(cls, source: str | Path) -> bool:
        if cls._snapshot_library(source) in INCOMPATIBLE_DIFFUSERS_LIBRARIES:
            return True
        for config_path in Path(source).glob("*/config.json"):
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if "quantization" in config and "quantization_config" not in config:
                return True
        return False

    def _repair_diffusers_snapshot(self, model: dict[str, Any], source: str) -> str:
        from huggingface_hub import snapshot_download

        repository = self._resolve_download_repository(
            str(model["repository_id"]), str(model["revision"]), str(model["task"]), ""
        )
        if repository == str(model["repository_id"]):
            raise RuntimeError(
                "O snapshot usa uma quantização de outro runtime e não existe uma variante "
                "Diffusers compatível declarada pelo repositório."
            )
        target = self.cache_dir / str(model["id"]) / "runtime-compatible"
        target.mkdir(parents=True, exist_ok=True)
        repaired = Path(snapshot_download(
            repo_id=repository,
            revision=str(model["revision"]),
            local_dir=target,
        )).resolve()
        if not (repaired / "model_index.json").is_file() or self._snapshot_needs_compatible_runtime(repaired):
            raise RuntimeError("A variante alternativa também não é compatível com PyTorch/Diffusers.")
        options = dict(model.get("options") or {})
        options.update({
            "resolved_repository": repository,
            "automatically_repaired": True,
            "original_runtime": self._snapshot_library(source) or "incompatível",
        })
        workspace_id = str(model.get("workspace_id") or "")
        if workspace_id:
            self.store.update_local_model(
                str(model["id"]), workspace_id, status="ready",
                local_path=str(repaired), options=options,
            )
        old = Path(source).resolve()
        if old.is_dir() and self.cache_dir in old.parents and old != repaired:
            shutil.rmtree(old)
        return str(repaired)

    @staticmethod
    def _diffusers_pipeline_class(source: str, task: str):
        import diffusers

        try:
            index = json.loads((Path(source) / "model_index.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return diffusers.DiffusionPipeline
        class_name = str(index.get("_class_name") or "")
        if hasattr(diffusers, class_name):
            return getattr(diffusers, class_name)
        alias = DIFFUSERS_PIPELINE_ALIASES.get(class_name, {})
        replacement = alias.get(task) or alias.get("default")
        if replacement and hasattr(diffusers, replacement):
            warnings.warn(
                f"{class_name} não existe nesta versão do Diffusers; "
                f"o AgenticFlow usará automaticamente {replacement}.",
                RuntimeWarning,
                stacklevel=2,
            )
            return getattr(diffusers, replacement)
        raise RuntimeError(
            f"O pipeline {class_name or 'desconhecido'} não é oferecido pela versão "
            "instalada do Diffusers e o repositório não declara um substituto compatível."
        )

    def install(self, model_id: str, workspace_id: str, token: str = "") -> None:
        model = self.store.get_local_model(model_id, workspace_id)
        if not model:
            return
        try:
            options = dict(model.get("options") or {})
            if options.get("runtime") == "llama_cpp":
                self._install_gguf(model, workspace_id, token)
                return
            from huggingface_hub import snapshot_download

            repository_id = self._resolve_download_repository(
                str(model["repository_id"]),
                str(model["revision"]),
                str(model["task"]),
                token,
            )
            target = self.cache_dir / model_id
            if str(model["task"]) in DIFFUSION_TASKS:
                target /= (
                    "runtime-compatible"
                    if repository_id != str(model["repository_id"])
                    else "runtime"
                )
            target.mkdir(parents=True, exist_ok=True)
            path = snapshot_download(
                repo_id=repository_id,
                revision=str(model["revision"]),
                token=token or None,
                local_dir=target,
            )
            if str(model["task"]) in DIFFUSION_TASKS and not (
                Path(path) / "model_index.json"
            ).is_file():
                raise RuntimeError(
                    "O download terminou, mas o modelo não contém model_index.json e "
                    "não pode ser carregado como pipeline Diffusers."
                )
            options = dict(model.get("options") or {})
            if repository_id != str(model["repository_id"]):
                options["resolved_repository"] = repository_id
                options["automatically_repaired"] = True
            if self._requires_remote_code(path):
                options["trust_remote_code"] = True
                options["remote_code_detected"] = True
            installed_model = {**model, "local_path": str(Path(path).resolve()), "options": options}
            options["capabilities"] = self.capabilities(installed_model)
            self.store.update_local_model(
                model_id,
                workspace_id,
                status="ready",
                local_path=str(Path(path).resolve()),
                options=options,
            )
        except Exception as exc:
            self.store.update_local_model(
                model_id,
                workspace_id,
                status="error",
                error=" ".join(str(exc).split())[:1000],
            )

    def _install_gguf(self, model: dict[str, Any], workspace_id: str, token: str) -> None:
        from huggingface_hub import hf_hub_download

        options = dict(model.get("options") or {})
        files = [str(item) for item in (options.get("gguf_files") or []) if item]
        if not files and options.get("gguf_file"):
            files = [str(options["gguf_file"])]
        if not files:
            raise RuntimeError("Selecione uma quantização GGUF antes de instalar.")
        target = self.cache_dir / str(model["id"])
        target.mkdir(parents=True, exist_ok=True)
        downloaded = []
        for filename in files:
            downloaded.append(hf_hub_download(
                repo_id=str(model["repository_id"]),
                filename=filename,
                revision=str(model["revision"]),
                token=token or None,
                local_dir=target,
            ))
        main_file = Path(downloaded[0]).resolve()
        mmproj_file = str(options.get("mmproj_file") or "")
        if mmproj_file:
            mmproj_path = Path(hf_hub_download(
                repo_id=str(model["repository_id"]),
                filename=mmproj_file,
                revision=str(model["revision"]),
                token=token or None,
                local_dir=target,
            )).resolve()
            options["mmproj_path"] = str(mmproj_path)
        options["runtime"] = "llama_cpp"
        options["gguf_file"] = files[0]
        installed = {**model, "local_path": str(main_file), "options": options}
        options["capabilities"] = self.capabilities(installed)
        self.store.update_local_model(
            str(model["id"]), workspace_id, status="ready",
            local_path=str(main_file), options=options,
        )

    @staticmethod
    def _requires_remote_code(source: str | Path) -> bool:
        root = Path(source)
        if not root.is_dir():
            return False
        for filename in ("config.json", "tokenizer_config.json", "processor_config.json"):
            config_path = root / filename
            if not config_path.is_file():
                continue
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            auto_map = config.get("auto_map")
            if isinstance(auto_map, dict) and any(auto_map.values()):
                return True
            if isinstance(auto_map, (list, tuple)) and any(auto_map):
                return True
        return False

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
            if self._requires_remote_code(source):
                pipeline_options["trust_remote_code"] = True
            else:
                pipeline_options.setdefault(
                    "trust_remote_code", bool(options.get("trust_remote_code", False))
                )
            hardware = self._configure_acceleration()
            effective_task = self._effective_task(model)
            if str(model["task"]) in DIFFUSION_TASKS:
                if Path(source).is_dir() and self._snapshot_needs_compatible_runtime(source):
                    source = self._repair_diffusers_snapshot(model, source)
                self._ensure_memory_capacity(source, hardware)
                if Path(source).is_dir() and not (Path(source) / "model_index.json").is_file():
                    raise RuntimeError(
                        "Este modelo foi baixado em um formato de checkpoint que não é "
                        "executável pelo Diffusers. Reinstale-o para o AgenticFlow resolver "
                        "automaticamente uma variante compatível."
                    )
                try:
                    import torch
                    pipeline_class = self._diffusers_pipeline_class(source, str(model["task"]))
                except ImportError as exc:
                    raise RuntimeError(
                        "Instale diffusers para executar modelos de imagem, vídeo ou 3D."
                    ) from exc
                if hardware.get("device") == 0:
                    pipeline_options.setdefault("dtype", torch.bfloat16)
                instance = pipeline_class.from_pretrained(source, **pipeline_options)
                if hardware.get("device") == 0:
                    devices = hardware.get("devices") or []
                    free_vram = int(devices[0].get("free_memory_bytes") or 0) if devices else 0
                    weight_bytes = self._model_weight_bytes(source)
                    should_offload = bool(
                        free_vram and weight_bytes and weight_bytes > int(free_vram * 0.82)
                    )
                    if should_offload and hasattr(instance, "enable_model_cpu_offload"):
                        instance.enable_model_cpu_offload(device="cuda")
                        if hasattr(instance, "enable_vae_slicing"):
                            instance.enable_vae_slicing()
                        if hasattr(instance, "enable_vae_tiling"):
                            instance.enable_vae_tiling()
                    else:
                        instance.to("cuda")
                else:
                    instance.to("cpu")
                self._pipelines[model_id] = instance
                return instance
            self._ensure_memory_capacity(source, hardware)
            pipeline_options.setdefault("device", hardware.get("device", -1))
            if hardware.get("backend") == "rocm":
                model_kwargs = dict(pipeline_options.get("model_kwargs") or {})
                model_kwargs.setdefault("attn_implementation", "eager")
                pipeline_options["model_kwargs"] = model_kwargs
            instance = pipeline(effective_task, model=source, **pipeline_options)
            self._pipelines[model_id] = instance
            return instance

    @classmethod
    def extract_image(cls, value: Any) -> Any | None:
        if isinstance(value, str):
            return value if value.startswith("data:image/") else None
        if isinstance(value, list):
            return next((image for item in value if (image := cls.extract_image(item)) is not None), None)
        if not isinstance(value, dict):
            return None
        if (
            str(value.get("data_uri", "")).startswith("data:image/")
            or str(value.get("data", "")).startswith("data:image/")
            or str(value.get("mime_type", "")).startswith("image/")
        ):
            return value
        for key in ("image", "images", "processed_image", "preview_image", "output"):
            if key in value:
                image = cls.extract_image(value[key])
                if image is not None:
                    return image
        return None

    @staticmethod
    def extract_text(value: Any) -> str:
        if isinstance(value, str) and not value.startswith("data:"):
            return value
        if isinstance(value, dict):
            for key in ("vision_prompt", "prompt", "instruction", "message", "text"):
                candidate = value.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        return ""

    @classmethod
    def _prepare_input(cls, task: str, value: Any) -> tuple[Any, str]:
        temp_path = ""
        if task == "image-text-to-text":
            asset = cls.extract_image(value)
            prompt = cls.extract_text(value) or (
                "Analise esta imagem em detalhes. Explique o que foi criado, "
                "aponte possíveis problemas e sugira melhorias."
            )
            if asset is None:
                return {"text": prompt}, temp_path
            from PIL import Image

            payload, _, _ = decode_asset(asset, default_name="image.png")
            image = Image.open(io.BytesIO(payload)).convert("RGB")
            return {"images": image, "text": prompt}, temp_path
        if task in {"image-to-text", "image-to-video", "image-to-3d"}:
            from PIL import Image

            asset = cls.extract_image(value)
            if asset is None:
                raise ValueError("Este modelo precisa receber uma imagem válida.")
            payload, _, _ = decode_asset(asset, default_name="image.png")
            image = Image.open(io.BytesIO(payload)).convert("RGB")
            return image, temp_path
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
        if hasattr(value, "frames"):
            frames = getattr(value, "frames")
            video = LocalModelRuntime._serialize_video_frames(frames)
            if video is not None:
                return {"video": video}
            return {"frames": LocalModelRuntime._serialize(frames)}
        for attribute in ("images", "audios", "meshes"):
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

    @staticmethod
    def _serialize_video_frames(frames: Any) -> dict[str, Any] | None:
        sequence = frames[0] if (
            isinstance(frames, list) and frames and isinstance(frames[0], list)
        ) else frames
        if not isinstance(sequence, list) or not sequence:
            return None
        try:
            import cv2
            import numpy as np
            from PIL import Image

            first = sequence[0]
            array = np.asarray(first.convert("RGB") if isinstance(first, Image.Image) else first)
            height, width = array.shape[:2]
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temporary:
                path = temporary.name
            writer = cv2.VideoWriter(
                path, cv2.VideoWriter_fourcc(*"mp4v"), 8.0, (width, height)
            )
            if not writer.isOpened():
                Path(path).unlink(missing_ok=True)
                return None
            try:
                for frame in sequence:
                    rgb = np.asarray(
                        frame.convert("RGB") if isinstance(frame, Image.Image) else frame
                    )
                    if rgb.shape[1] != width or rgb.shape[0] != height:
                        rgb = cv2.resize(rgb, (width, height))
                    writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            finally:
                writer.release()
            payload = Path(path).read_bytes()
            Path(path).unlink(missing_ok=True)
            return {"data_uri": _data_uri(payload, "video/mp4"), "fps": 8}
        except Exception:
            # Encoding is a presentation enhancement; callers can still receive frames.
            return None

    @staticmethod
    def _has_multimodal_chat_template(instance: Any) -> bool:
        processor = getattr(instance, "processor", None)
        if processor is None:
            return False
        return bool(
            getattr(processor, "chat_template", None)
            or getattr(getattr(processor, "tokenizer", None), "chat_template", None)
        )

    @classmethod
    def _run_image_text_pipeline(
        cls,
        instance: Any,
        prepared: dict[str, Any],
        parameters: dict[str, Any],
        *,
        force_chat: bool = False,
    ) -> Any:
        options = dict(parameters)
        options.setdefault("return_full_text", False)
        image = prepared.get("images")
        prompt = str(prepared.get("text") or "")
        use_chat = image is not None and (
            force_chat or cls._has_multimodal_chat_template(instance)
        )
        if use_chat:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt},
                    ],
                }
            ]
            return instance(text=messages, **options)
        return instance(**prepared, **options)

    def infer(
        self,
        *,
        model_id: str,
        workspace_id: str,
        value: Any,
        parameters: dict[str, Any] | None = None,
        usage_scope: str = "",
    ) -> Any:
        model = self.store.get_local_model(model_id, workspace_id)
        if not model:
            raise RuntimeError("Modelo local não encontrado.")
        if model["status"] != "ready":
            raise RuntimeError(f"O modelo local ainda não está pronto (status: {model['status']}).")
        with self._inference_slot():
            self._evict_other_models(model_id)
            self._begin_use(model_id, usage_scope)
            temp_path = ""
            instance = None
            try:
                options = dict(model.get("options") or {})
                if options.get("runtime") == "llama_cpp":
                    return self.llama_cpp.infer(
                        model_id=model_id,
                        model_file=str(model.get("local_path") or ""),
                        value=value,
                        options=options,
                        parameters=parameters or {},
                    )
                instance = self._pipeline(model)
                effective_task = self._effective_task(model)
                prepared, temp_path = self._prepare_input(effective_task, value)
                if effective_task == "image-text-to-text":
                    try:
                        output = self._run_image_text_pipeline(
                            instance, prepared, parameters or {}
                        )
                    except Exception as exc:
                        mismatch = "image features and image tokens do not match" in str(exc).lower()
                        if not mismatch or prepared.get("images") is None:
                            raise
                        output = self._run_image_text_pipeline(
                            instance, prepared, parameters or {}, force_chat=True
                        )
                else:
                    output = instance(prepared, **(parameters or {}))
                return self._serialize(output)
            finally:
                if temp_path:
                    Path(temp_path).unlink(missing_ok=True)
                instance = None
                self._end_use(model_id)

    def chat(self, *, model_id: str, workspace_id: str, instructions: str, prompt: str, temperature: float, usage_scope: str = "") -> str:
        text = f"{instructions}\n\n{prompt}" if instructions else prompt
        result = self.infer(
            model_id=model_id,
            workspace_id=workspace_id,
            value=text,
            parameters={"temperature": temperature, "return_full_text": False},
            usage_scope=usage_scope,
        )
        if isinstance(result, list) and result:
            result = result[0]
        if isinstance(result, dict):
            return str(result.get("generated_text") or result.get("text") or result)
        return str(result)

    @contextmanager
    def _inference_slot(self):
        """Serialize local inference in arrival order without blocking API providers."""
        with self._queue_condition:
            ticket = self._next_queue_ticket
            self._next_queue_ticket += 1
            while ticket != self._serving_queue_ticket:
                self._queue_condition.wait()
        try:
            yield
        finally:
            with self._queue_condition:
                self._serving_queue_ticket += 1
                self._queue_condition.notify_all()

    def _evict_other_models(self, model_id: str) -> None:
        """Keep at most one self-hosted pipeline resident in RAM/VRAM."""
        self.llama_cpp.unload_except(model_id)
        released = []
        with self._lock:
            for cached_id in list(self._pipelines):
                if cached_id == model_id:
                    continue
                if self._active_inferences.get(cached_id, 0):
                    raise RuntimeError(
                        "Outra inferência local ainda está ativa fora da fila exclusiva."
                    )
                timer = self._idle_timers.pop(cached_id, None)
                if timer:
                    timer.cancel()
                self._release_when_idle.discard(cached_id)
                self._usage_scopes.pop(cached_id, None)
                instance = self._pipelines.pop(cached_id, None)
                if instance is not None:
                    released.append(instance)
        instance = None
        if released:
            self._release_instances(released)

    def _begin_use(self, model_id: str, usage_scope: str = "") -> None:
        with self._lock:
            timer = self._idle_timers.pop(model_id, None)
            if timer:
                timer.cancel()
            self._release_when_idle.discard(model_id)
            self._active_inferences[model_id] = self._active_inferences.get(model_id, 0) + 1
            if usage_scope:
                self._usage_scopes.setdefault(model_id, set()).add(usage_scope)

    def _end_use(self, model_id: str) -> None:
        instance = None
        unload_llama = False
        with self._lock:
            active = max(self._active_inferences.get(model_id, 1) - 1, 0)
            if active:
                self._active_inferences[model_id] = active
                return
            self._active_inferences.pop(model_id, None)
            if model_id in self._release_when_idle:
                self._release_when_idle.discard(model_id)
                instance = self._pipelines.pop(model_id, None)
                unload_llama = instance is None
            else:
                timer = threading.Timer(self.idle_seconds, self._idle_unload, args=(model_id,))
                timer.daemon = True
                self._idle_timers[model_id] = timer
                timer.start()
        if instance is not None:
            self._release_pipeline(instance)
        elif unload_llama:
            self.llama_cpp.unload(model_id)

    @staticmethod
    def _release_instances(instances: list[Any]) -> None:
        # Never call model.to("cpu") here. Large models would allocate a second
        # copy in system RAM and can crash the native Windows/ROCm allocator.
        torch = None
        try:
            import torch as torch_module

            torch = torch_module
            if torch.cuda.is_available():
                # Wait for asynchronous ROCm/CUDA kernels before destroying the
                # objects that own their buffers.
                torch.cuda.synchronize()
        except (ImportError, RuntimeError):
            torch = None
        for index, _instance in enumerate(instances):
            instances[index] = None
        instances.clear()
        _instance = None
        gc.collect()
        if torch is not None:
            try:
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()
                    gc.collect()
                    torch.cuda.empty_cache()
            except RuntimeError:
                # The process remains recoverable even if a native backend has
                # already invalidated its device context.
                pass

    @classmethod
    def _release_pipeline(cls, instance: Any) -> None:
        cls._release_instances([instance])

    def _idle_unload(self, model_id: str) -> None:
        with self._lock:
            self._idle_timers.pop(model_id, None)
            if self._active_inferences.get(model_id, 0):
                return
            self._release_when_idle.discard(model_id)
            self._usage_scopes.pop(model_id, None)
            instance = self._pipelines.pop(model_id, None)
        if instance is not None:
            self._release_pipeline(instance)
        else:
            self.llama_cpp.unload(model_id)

    def release_scope(self, usage_scope: str) -> int:
        if not usage_scope:
            return 0
        with self._lock:
            candidates = []
            for model_id, scopes in list(self._usage_scopes.items()):
                scopes.discard(usage_scope)
                if not scopes:
                    self._usage_scopes.pop(model_id, None)
                    if self._active_inferences.get(model_id, 0):
                        self._release_when_idle.add(model_id)
                    else:
                        candidates.append(model_id)
        return sum(1 for model_id in candidates if self.unload(model_id))

    def unload(self, model_id: str) -> bool:
        with self._lock:
            if self._active_inferences.get(model_id, 0):
                return False
            timer = self._idle_timers.pop(model_id, None)
            if timer:
                timer.cancel()
            self._release_when_idle.discard(model_id)
            self._usage_scopes.pop(model_id, None)
            instance = self._pipelines.pop(model_id, None)
        if instance is not None:
            self._release_pipeline(instance)
            return True
        return self.llama_cpp.unload(model_id)

    def remove_files(self, model: dict[str, Any]) -> None:
        self.unload(str(model["id"]))
        path = Path(str(model.get("local_path") or self.cache_dir / str(model["id"]))).resolve()
        if path != self.cache_dir and self.cache_dir in path.parents and path.exists():
            target = path if path.is_dir() else next(
                (parent for parent in path.parents if parent.parent == self.cache_dir), path.parent
            )
            shutil.rmtree(target)
