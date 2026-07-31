from agentic_flow import amd as detect_amd_gfx
from pathlib import Path


def test_extracts_and_deduplicates_gfx_targets():
    output = """
    Board name: AMD Radeon RX 9060 XT
    Name: gfx1200
    gcnArchName: gfx1200
    Name: gfx1101
    """
    assert detect_amd_gfx.targets_from_output(output) == ["gfx1200", "gfx1101"]


def test_forced_gfx_override_is_validated(monkeypatch):
    monkeypatch.setenv("AGENTIC_FLOW_AMD_GFX", "gfx1200,gfx1100")
    assert detect_amd_gfx.detect_targets() == ["gfx1200", "gfx1100"]


def test_unknown_amd_gpu_falls_back_to_device_all(monkeypatch, capsys):
    monkeypatch.delenv("AGENTIC_FLOW_AMD_GFX", raising=False)
    monkeypatch.setattr(detect_amd_gfx, "command_candidates", lambda: [])
    monkeypatch.setattr(detect_amd_gfx, "has_amd_gpu", lambda: True)
    assert detect_amd_gfx.main() == 0
    assert capsys.readouterr().out.strip() == "all"


def test_windows_launcher_uses_stable_rocm_safety_defaults():
    launcher = (Path(__file__).resolve().parents[1] / "start.bat").read_text(
        encoding="utf-8"
    )

    assert "TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=0" in launcher
    assert "AGENTIC_FLOW_ROCM_SAFE_MODE=1" in launcher
    assert "sys.version_info[:2] == (3, 12)" in launcher
    assert ":recover_native_crash" in launcher
    assert ".venv-python-backup-" in launcher
