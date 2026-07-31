from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


RELEASE_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
QUANTIZATION_RE = re.compile(
    r"(?:^|[-_.])((?:IQ\d(?:_[A-Z0-9]+)*)|(?:Q\d(?:_[A-Z0-9]+)*)|BF16|F16|FP16|MXFP4)(?:[-_.]|$)",
    re.IGNORECASE,
)
SHARD_RE = re.compile(r"-\d{5}-of-\d{5}(?=\.gguf$)", re.IGNORECASE)


def _json_request(url: str, payload: dict[str, Any] | None = None, timeout: int = 30):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AgenticFlow-llama.cpp",
        },
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def detect_backend() -> dict[str, str]:
    forced = os.getenv("AGENTIC_FLOW_LLAMA_CPP_BACKEND", "").strip().lower()
    if forced in {"hip", "cuda", "vulkan", "cpu"}:
        return {"backend": forced, "reason": "configuração manual"}
    try:
        import torch

        if torch.cuda.is_available():
            if getattr(torch.version, "hip", None):
                return {"backend": "hip", "reason": torch.cuda.get_device_name(0)}
            return {"backend": "cuda", "reason": torch.cuda.get_device_name(0)}
    except (ImportError, RuntimeError):
        pass
    names = ""
    if os.name == "nt":
        try:
            command = [
                "powershell", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_VideoController).Name -join ';'",
            ]
            names = subprocess.check_output(
                command, text=True, timeout=10, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.SubprocessError):
            pass
    lowered = names.lower()
    if any(marker in lowered for marker in ("amd", "radeon")):
        return {"backend": "hip", "reason": names}
    if "nvidia" in lowered or shutil.which("nvidia-smi"):
        return {"backend": "cuda", "reason": names or "nvidia-smi"}
    if names and not any(marker in lowered for marker in ("microsoft basic", "remote")):
        return {"backend": "vulkan", "reason": names}
    return {"backend": "cpu", "reason": "nenhuma GPU compatível detectada"}


def _asset_patterns(backend: str) -> list[re.Pattern[str]]:
    system = platform.system().lower()
    if system == "windows":
        mapping = {
            "hip": [r"^llama-.*bin-win-hip-radeon-x64\.zip$"],
            "cuda": [r"^llama-.*bin-win-cuda-12\.4-x64\.zip$"],
            "vulkan": [r"^llama-.*bin-win-vulkan-x64\.zip$"],
            "cpu": [r"^llama-.*bin-win-cpu-x64\.zip$"],
        }
    else:
        mapping = {
            "hip": [r"^llama-.*bin-ubuntu-rocm-[\d.]+-x64\.tar\.gz$"],
            "cuda": [],
            "vulkan": [r"^llama-.*bin-ubuntu-vulkan-x64\.tar\.gz$"],
            "cpu": [r"^llama-.*bin-ubuntu-x64\.tar\.gz$"],
        }
    return [re.compile(pattern, re.IGNORECASE) for pattern in mapping.get(backend, [])]


class LlamaCppManager:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"
        self._process: subprocess.Popen | None = None
        self._active_model_id = ""
        self._port = 0
        self._lock = threading.RLock()

    def status(self) -> dict[str, Any]:
        manifest: dict[str, Any] = {}
        if self.manifest_path.is_file():
            try:
                manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        server = Path(str(manifest.get("server_path") or ""))
        return {
            **detect_backend(),
            **manifest,
            "installed": server.is_file(),
            "running": bool(self._process and self._process.poll() is None),
            "active_model_id": self._active_model_id,
        }

    def _select_assets(self, release: dict[str, Any], backend: str) -> list[dict[str, Any]]:
        assets = list(release.get("assets") or [])
        selected = [
            asset for asset in assets
            if any(pattern.search(str(asset.get("name") or "")) for pattern in _asset_patterns(backend))
        ]
        if backend == "cuda" and selected:
            cuda_version = re.search(r"cuda-([\d.]+)-", str(selected[0]["name"]), re.I)
            if cuda_version:
                needle = f"cudart-llama-bin-win-cuda-{cuda_version.group(1)}-x64.zip"
                selected.extend(asset for asset in assets if asset.get("name") == needle)
        return selected

    @staticmethod
    def _safe_extract(archive: Path, destination: Path) -> None:
        destination = destination.resolve()
        if archive.name.lower().endswith(".zip"):
            with zipfile.ZipFile(archive) as bundle:
                for member in bundle.infolist():
                    target = (destination / member.filename).resolve()
                    if destination != target and destination not in target.parents:
                        raise RuntimeError("Arquivo llama.cpp contém um caminho inseguro.")
                bundle.extractall(destination)
            return
        with tarfile.open(archive, "r:gz") as bundle:
            for member in bundle.getmembers():
                target = (destination / member.name).resolve()
                if destination != target and destination not in target.parents:
                    raise RuntimeError("Arquivo llama.cpp contém um caminho inseguro.")
            bundle.extractall(destination, filter="data")

    def install(self, force: bool = False) -> dict[str, Any]:
        current = self.status()
        if current.get("installed") and not force:
            return current
        detection = detect_backend()
        release = _json_request(RELEASE_API)
        requested = detection["backend"]
        candidates = [requested]
        if requested in {"hip", "cuda"}:
            candidates.append("vulkan")
        candidates.append("cpu")
        chosen = ""
        selected: list[dict[str, Any]] = []
        for candidate in dict.fromkeys(candidates):
            selected = self._select_assets(release, candidate)
            if selected:
                chosen = candidate
                break
        if not selected:
            raise RuntimeError(
                "O release atual do llama.cpp não oferece um binário compatível com este sistema."
            )
        version = str(release.get("tag_name") or "latest")
        final_dir = self.root / version / chosen
        with tempfile.TemporaryDirectory(prefix="agenticflow-llama-") as temporary:
            temporary_dir = Path(temporary)
            extracted = temporary_dir / "extracted"
            extracted.mkdir()
            for asset in selected:
                url = str(asset.get("browser_download_url") or "")
                archive = temporary_dir / str(asset["name"])
                request = urllib.request.Request(url, headers={"User-Agent": "AgenticFlow-llama.cpp"})
                with urllib.request.urlopen(request, timeout=120) as response, archive.open("wb") as output:
                    shutil.copyfileobj(response, output)
                self._safe_extract(archive, extracted)
            if final_dir.exists():
                shutil.rmtree(final_dir)
            final_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(extracted), str(final_dir))
        executable = "llama-server.exe" if os.name == "nt" else "llama-server"
        servers = list(final_dir.rglob(executable))
        if not servers:
            raise RuntimeError("O pacote oficial foi baixado, mas llama-server não foi encontrado.")
        server = servers[0].resolve()
        if os.name != "nt":
            server.chmod(server.stat().st_mode | 0o111)
        manifest = {
            "version": version,
            "backend": chosen,
            "detected_backend": requested,
            "device": detection.get("reason", ""),
            "assets": [asset["name"] for asset in selected],
            "server_path": str(server),
            "installed_at": int(time.time()),
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return self.status()

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _stop_locked(self) -> bool:
        process = self._process
        self._process = None
        self._active_model_id = ""
        self._port = 0
        if not process or process.poll() is not None:
            return False
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return True

    def unload(self, model_id: str = "") -> bool:
        with self._lock:
            if model_id and self._active_model_id != model_id:
                return False
            return self._stop_locked()

    def unload_except(self, model_id: str) -> bool:
        with self._lock:
            if self._active_model_id and self._active_model_id != model_id:
                return self._stop_locked()
            return False

    def _start(self, model_id: str, model_file: Path, options: dict[str, Any]) -> None:
        with self._lock:
            if self._active_model_id == model_id and self._process and self._process.poll() is None:
                return
            self._stop_locked()
            state = self.status()
            if not state.get("installed"):
                state = self.install()
            server = Path(str(state["server_path"]))
            port = self._free_port()
            gpu_layers = "0" if state.get("backend") == "cpu" else str(options.get("gpu_layers", "auto"))
            command = [
                str(server), "--model", str(model_file), "--host", "127.0.0.1",
                "--port", str(port), "--n-gpu-layers", gpu_layers,
                "--ctx-size", str(options.get("context_size", 4096)),
            ]
            if state.get("backend") != "cpu" and "gpu_layers" not in options:
                command.extend(["--fit", "on", "--fit-target", "1024"])
            mmproj = str(options.get("mmproj_path") or "")
            if mmproj and Path(mmproj).is_file():
                command.extend(["--mmproj", mmproj])
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            environment = os.environ.copy()
            environment.setdefault("GGML_CUDA_ENABLE_UNIFIED_MEMORY", "0")
            self._process = subprocess.Popen(
                command,
                cwd=str(server.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
                env=environment,
            )
            self._active_model_id = model_id
            self._port = port
        deadline = time.monotonic() + 90
        last_error = ""
        while time.monotonic() < deadline:
            if self._process and self._process.poll() is not None:
                raise RuntimeError(
                    "llama-server encerrou durante o carregamento. Escolha uma quantização menor ou verifique o driver da GPU."
                )
            try:
                _json_request(f"http://127.0.0.1:{port}/health", timeout=2)
                return
            except (OSError, ValueError, urllib.error.URLError) as exc:
                last_error = str(exc)
                time.sleep(0.3)
        self.unload(model_id)
        raise RuntimeError(f"llama-server não ficou pronto a tempo. {last_error}".strip())

    def infer(
        self,
        *,
        model_id: str,
        model_file: str | Path,
        value: Any,
        options: dict[str, Any],
        parameters: dict[str, Any],
    ) -> str:
        path = Path(model_file).resolve()
        if not path.is_file():
            raise RuntimeError("O arquivo GGUF selecionado não foi encontrado.")
        self._start(model_id, path, options)
        prompt = value if isinstance(value, str) else str(value.get("text") or value.get("prompt") or "") if isinstance(value, dict) else str(value)
        content: Any = prompt
        image = None
        if isinstance(value, dict):
            image = value.get("image") or value.get("data_uri")
            if not image and isinstance(value.get("images"), list) and value["images"]:
                candidate = value["images"][0]
                image = candidate.get("data_uri") if isinstance(candidate, dict) else candidate
        if image:
            if not options.get("mmproj_path"):
                raise RuntimeError("Este GGUF precisa de um arquivo mmproj para receber imagens.")
            if isinstance(image, dict):
                image = image.get("data_uri") or image.get("data")
            content = [
                {"type": "text", "text": prompt or "Analise esta imagem."},
                {"type": "image_url", "image_url": {"url": str(image)}},
            ]
        body = {
            "model": path.name,
            "messages": [{"role": "user", "content": content}],
            "temperature": float(parameters.get("temperature", 0.7)),
            "max_tokens": int(parameters.get("max_new_tokens", parameters.get("max_tokens", 512))),
            "stream": False,
        }
        response = _json_request(
            f"http://127.0.0.1:{self._port}/v1/chat/completions", body, timeout=600
        )
        try:
            return str(response["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Resposta inesperada do llama-server: {response}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Instalador automático do llama.cpp")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--data-dir", default=os.getenv("AGENTIC_FLOW_DATA_DIR", "data"))
    args = parser.parse_args()
    manager = LlamaCppManager(Path(args.data_dir) / "llama.cpp")
    try:
        result = manager.install(force=args.force) if args.install else manager.status()
    except Exception as exc:
        print(f"[AVISO] llama.cpp: {' '.join(str(exc).split())}")
        return 1
    print(
        "[OK] llama.cpp: "
        f"{result.get('backend')} · {result.get('version', 'não instalado')} · "
        f"{result.get('device') or result.get('reason', '')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
