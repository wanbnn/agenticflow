from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__
from .amd import detect_targets, has_amd_gpu
from .llama_cpp import LlamaCppManager
from .paths import default_data_dir


RUNTIME_PACKAGES = [
    "huggingface-hub>=0.34",
    "transformers==5.14.1",
    "accelerate>=1.9",
    "diffusers>=0.39",
    "safetensors>=0.5",
    "sentencepiece>=0.2",
    "soundfile>=0.13",
    "trimesh>=4.7",
]
RUNTIME_MODULES = (
    "torch", "torchvision", "torchaudio", "huggingface_hub", "transformers",
    "accelerate", "diffusers", "safetensors", "sentencepiece", "soundfile", "trimesh",
)


def _video_controller_names() -> str:
    if os.name != "nt":
        return ""
    try:
        return subprocess.check_output(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-CimInstance Win32_VideoController).Name -join ';'",
            ],
            text=True,
            timeout=15,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def detect_runtime_backend() -> dict[str, str]:
    forced = os.getenv("AGENTIC_FLOW_RUNTIME_BACKEND", "").strip().lower()
    if forced in {"rocm", "cuda", "mps", "cpu"}:
        return {"backend": forced, "device": "configuração manual"}
    names = _video_controller_names()
    lowered = names.lower()
    if "nvidia" in lowered or shutil.which("nvidia-smi"):
        return {"backend": "cuda", "device": names or "NVIDIA"}
    if "amd" in lowered or "radeon" in lowered or has_amd_gpu():
        return {"backend": "rocm", "device": names or "AMD Radeon"}
    if platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        return {"backend": "mps", "device": "Apple Silicon"}
    return {"backend": "cpu", "device": names or "CPU"}


def _run(command: list[str], *, dry_run: bool = False) -> None:
    display = " ".join(command)
    print(f"[INFO] {display}")
    if not dry_run:
        subprocess.run(command, check=True)


def _pip(*arguments: str, dry_run: bool = False) -> None:
    _run(
        [sys.executable, "-m", "pip", "--disable-pip-version-check", *arguments],
        dry_run=dry_run,
    )


def _runtime_modules_installed() -> bool:
    return all(importlib.util.find_spec(module) is not None for module in RUNTIME_MODULES)


def _torch_backend_ready(backend: str) -> bool:
    if importlib.util.find_spec("torch") is None:
        return False
    expression = {
        "rocm": "bool(torch.version.hip and torch.cuda.is_available())",
        "cuda": "bool(torch.cuda.is_available() and not torch.version.hip)",
        "mps": "bool(torch.backends.mps.is_available())",
        "cpu": "True",
    }[backend]
    result = subprocess.run(
        [sys.executable, "-c", f"import torch,sys;sys.exit(0 if {expression} else 1)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def runtime_ready(backend: str) -> bool:
    return _runtime_modules_installed() and _torch_backend_ready(backend)


def install_runtime(*, force: bool = False, dry_run: bool = False) -> dict[str, str]:
    detection = detect_runtime_backend()
    backend = detection["backend"]
    print(f"[INFO] Hardware detectado: {detection['device']} · backend {backend.upper()}")
    if not force and runtime_ready(backend):
        print("[OK] Runtime PyTorch e bibliotecas multimodais já estão prontos.")
        return detection

    _pip("install", "--upgrade", *RUNTIME_PACKAGES, dry_run=dry_run)
    if force:
        _pip("uninstall", "-y", "torch", "torchvision", "torchaudio", dry_run=dry_run)

    if backend == "rocm" and os.name == "nt":
        targets = detect_targets()
        extras = [f"device-{target}" for target in targets] or ["device-all"]
        extra_list = ",".join(extras)
        _pip(
            "install", "--upgrade",
            "--extra-index-url", "https://repo.amd.com/rocm/whl-multi-arch/",
            f"rocm[libraries,{extra_list}]==7.14.0",
            f"torch[{extra_list}]==2.12.0+rocm7.14.0",
            f"torchvision[{extra_list}]==0.27.0+rocm7.14.0",
            "torchaudio==2.11.0+rocm7.14.0",
            dry_run=dry_run,
        )
    elif backend == "rocm":
        _pip(
            "install", "--upgrade", "torch==2.10.0", "torchvision==0.25.0",
            "torchaudio==2.10.0", "--index-url", "https://download.pytorch.org/whl/rocm7.1",
            dry_run=dry_run,
        )
    elif backend == "cuda":
        _pip(
            "install", "--upgrade", "torch==2.11.0", "torchvision==0.26.0",
            "torchaudio==2.11.0", "--index-url", "https://download.pytorch.org/whl/cu128",
            dry_run=dry_run,
        )
    elif backend == "cpu":
        _pip(
            "install", "--upgrade", "torch==2.11.0", "torchvision==0.26.0",
            "torchaudio==2.11.0", "--index-url", "https://download.pytorch.org/whl/cpu",
            dry_run=dry_run,
        )
    else:
        _pip(
            "install", "--upgrade", "torch==2.11.0", "torchvision==0.26.0",
            "torchaudio==2.11.0", dry_run=dry_run,
        )

    if not dry_run and not runtime_ready(backend):
        raise RuntimeError(
            f"Os pacotes foram instalados, mas o backend {backend.upper()} não ficou operacional. "
            "Execute 'agenticflow doctor' para ver o diagnóstico."
        )
    return detection


def install_all(*, force: bool = False, dry_run: bool = False) -> dict[str, object]:
    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    detection = install_runtime(force=force, dry_run=dry_run)
    llama_status: dict[str, object] = {"installed": False}
    if not dry_run and os.getenv("AGENTIC_FLOW_DISABLE_LLAMA_CPP") != "1":
        print("[INFO] Instalando o runtime GGUF llama.cpp adequado ao hardware...")
        try:
            llama_status = LlamaCppManager(data_dir / "llama.cpp").install(force=force)
        except Exception as exc:
            print(f"[AVISO] llama.cpp não pôde ser instalado agora: {' '.join(str(exc).split())}")
    state = {"version": __version__, "data_dir": str(data_dir), **detection, "llama_cpp": llama_status}
    if not dry_run:
        (data_dir / "runtime.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def doctor() -> int:
    detection = detect_runtime_backend()
    data_dir = default_data_dir()
    print(f"AgenticFlow {__version__}")
    print(f"Python: {sys.version.split()[0]} · {sys.executable}")
    print(f"Dados: {data_dir}")
    print(f"Hardware: {detection['device']} · {detection['backend'].upper()}")
    print(f"Runtime PyTorch: {'pronto' if runtime_ready(detection['backend']) else 'não instalado/incompatível'}")
    llama = LlamaCppManager(data_dir / "llama.cpp").status()
    print(f"llama.cpp: {'pronto' if llama.get('installed') else 'não instalado'} · {llama.get('backend')}")
    print(f"SQLite interno: {os.getenv('AGENTIC_FLOW_SQLITE_PATH') or data_dir / 'agentic-flow-v2.db'}")
    return 0


def serve(*, host: str, port: int, open_browser: bool, skip_runtime: bool) -> int:
    os.environ.setdefault("AGENTIC_FLOW_DATA_DIR", str(default_data_dir()))
    os.environ["AGENTIC_FLOW_HOST"] = host
    os.environ["AGENTIC_FLOW_PORT"] = str(port)
    if not skip_runtime:
        install_all()
    if open_browser:
        browser_timer = threading.Timer(
            1.5, webbrowser.open, args=(f"http://127.0.0.1:{port}",)
        )
        browser_timer.daemon = True
        browser_timer.start()
    from .main import run

    run()
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="agenticflow", description="AgenticFlow self-hosted")
    root.add_argument("--version", action="version", version=f"AgenticFlow {__version__}")
    commands = root.add_subparsers(dest="command")
    serve_parser = commands.add_parser("serve", help="Inicia a aplicação (comando padrão)")
    serve_parser.add_argument("--host", default=os.getenv("AGENTIC_FLOW_HOST", "127.0.0.1"))
    serve_parser.add_argument("--port", type=int, default=int(os.getenv("AGENTIC_FLOW_PORT", "16777")))
    serve_parser.add_argument("--no-browser", action="store_true")
    serve_parser.add_argument("--skip-runtime", action="store_true")
    install_parser = commands.add_parser("install", help="Instala ou repara runtimes locais")
    install_parser.add_argument("--force", action="store_true")
    install_parser.add_argument("--dry-run", action="store_true")
    commands.add_parser("doctor", help="Mostra o diagnóstico do ambiente")
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "install":
            install_all(force=args.force, dry_run=args.dry_run)
            return 0
        if args.command == "doctor":
            return doctor()
        return serve(
            host=getattr(args, "host", os.getenv("AGENTIC_FLOW_HOST", "127.0.0.1")),
            port=getattr(args, "port", int(os.getenv("AGENTIC_FLOW_PORT", "16777"))),
            open_browser=not getattr(args, "no_browser", False),
            skip_runtime=getattr(args, "skip_runtime", False),
        )
    except KeyboardInterrupt:
        return 130
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"[ERRO] {' '.join(str(exc).split())}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
