"""Detect AMD GFX targets without requiring a working PyTorch installation."""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


GFX_PATTERN = re.compile(r"\bgfx(?:9[0-9a-f]{2}|10[0-9]{2}|11[0-9]{2}|12[0-9]{2})\b", re.I)


def command_candidates() -> list[list[str]]:
    candidates: list[list[str]] = []
    for name in ("clinfo", "hipinfo", "hipInfo", "rocminfo"):
        path = shutil.which(name)
        if path:
            candidates.append([path])
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        patterns = (
            str(Path(program_files) / "AMD" / "ROCm" / "*" / "bin" / "hipInfo.exe"),
            str(Path(program_files) / "AMD" / "ROCm" / "*" / "bin" / "rocminfo.exe"),
        )
        for pattern in patterns:
            candidates.extend([path] for path in sorted(glob.glob(pattern), reverse=True))
    return candidates


def targets_from_output(output: str) -> list[str]:
    return list(dict.fromkeys(match.lower() for match in GFX_PATTERN.findall(output)))


def has_amd_gpu() -> bool:
    if os.name != "nt":
        for vendor_file in Path("/sys/class/drm").glob("card*/device/vendor"):
            try:
                if vendor_file.read_text().strip().lower() == "0x1002":
                    return True
            except OSError:
                continue
        return False
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name) -join \"`n\"",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return "amd" in result.stdout.lower() or "radeon" in result.stdout.lower()
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect_targets() -> list[str]:
    forced = os.getenv("AGENTIC_FLOW_AMD_GFX", "").strip().lower()
    if forced:
        targets = targets_from_output(forced.replace(",", " "))
        if not targets:
            raise ValueError("AGENTIC_FLOW_AMD_GFX não contém uma arquitetura gfx válida.")
        return targets
    for command in command_candidates():
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        targets = targets_from_output(f"{result.stdout}\n{result.stderr}")
        if targets:
            return targets
    return []


def main() -> int:
    try:
        targets = detect_targets()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if targets:
        print(",".join(targets))
        return 0
    if has_amd_gpu():
        print("all")
        return 0
    print("none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
