from agentic_flow import cli
from agentic_flow.main import DATA_DIR, database_from_environment
from agentic_flow.paths import default_data_dir


def test_default_data_dir_uses_local_app_data_on_windows(monkeypatch, tmp_path):
    monkeypatch.delenv("AGENTIC_FLOW_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr("agentic_flow.paths.os.name", "nt")

    assert default_data_dir() == tmp_path / "AgenticFlow"


def test_internal_database_is_always_sqlite_even_with_legacy_mysql_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql+pymysql://unsafe.example/app")
    monkeypatch.setenv("DB_HOST", "unsafe.example")

    database = database_from_environment()

    assert database == str(DATA_DIR / "agentic-flow-v2.db")
    assert "mysql" not in database


def test_runtime_backend_can_be_forced_without_hardware_probe(monkeypatch):
    monkeypatch.setenv("AGENTIC_FLOW_RUNTIME_BACKEND", "cpu")
    assert cli.detect_runtime_backend() == {
        "backend": "cpu",
        "device": "configuração manual",
    }


def test_runtime_installer_dry_run_never_executes_pip(monkeypatch):
    monkeypatch.setenv("AGENTIC_FLOW_RUNTIME_BACKEND", "cpu")
    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda command, **kwargs: calls.append(command))

    result = cli.install_runtime(force=True, dry_run=True)

    assert result["backend"] == "cpu"
    assert calls == []


def test_cli_exposes_expected_commands():
    help_text = cli.parser().format_help()
    assert "install" in help_text
    assert "doctor" in help_text
    assert "serve" in help_text
