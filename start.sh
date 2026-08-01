#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

show_help() {
    cat <<'EOF'
Uso: ./start.sh [opção]

Cria .venv com Python 3.12, instala as dependências e inicia o servidor.

Opções:
  --install-only   Instala ou verifica o ambiente sem iniciar o servidor
  --check-python   Exibe a versão do Python do ambiente
  --check-gpu      Exibe o diagnóstico de GPU e runtimes
  --help           Exibe esta ajuda

Variáveis opcionais:
  AGENTIC_FLOW_RUNTIME_BACKEND       Força rocm, cuda, mps ou cpu
  AGENTIC_FLOW_HOST                  Host HTTP (padrão: 127.0.0.1)
  AGENTIC_FLOW_PORT                  Porta HTTP (padrão: 16777)
  AGENTIC_FLOW_DATA_DIR              Diretório de dados persistentes
  AGENTIC_FLOW_LLAMA_CPP_BACKEND     Força hip, cuda, vulkan ou cpu
  AGENTIC_FLOW_DISABLE_LLAMA_CPP=1   Não instala o runtime GGUF
EOF
}

find_python312() {
    local candidate
    for candidate in python3.12 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))' >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
    elif [[ -n "${HOME:-}" && -x "$HOME/.local/bin/uv" ]]; then
        printf '%s\n' "$HOME/.local/bin/uv"
    else
        return 1
    fi
}

ensure_uv() {
    local uv_bin
    uv_bin="$(find_uv || true)"
    if [[ -z "$uv_bin" ]]; then
        if ! command -v curl >/dev/null 2>&1; then
            echo '[ERRO] curl não foi encontrado. Instale curl e tente novamente.' >&2
            return 1
        fi
        echo '[INFO] Instalando o gerenciador de ambientes uv...' >&2
        curl -LsSf https://astral.sh/uv/install.sh | sh >&2
        uv_bin="$(find_uv || true)"
    fi
    if [[ -z "$uv_bin" ]]; then
        echo '[ERRO] uv foi instalado, mas não foi localizado nesta sessão.' >&2
        return 1
    fi
    printf '%s\n' "$uv_bin"
}

create_venv() {
    local python_bin uv_bin
    python_bin="$(find_python312 || true)"
    if [[ -n "$python_bin" ]] && "$python_bin" -m venv .venv >/dev/null 2>&1; then
        return 0
    fi

    uv_bin="$(ensure_uv)"
    echo '[INFO] Baixando Python 3.12 e criando o ambiente virtual...'
    "$uv_bin" venv --seed --python 3.12 .venv
}

case "${1:-}" in
    --help|-h)
        show_help
        exit 0
        ;;
    --check-python)
        if [[ ! -x .venv/bin/python ]]; then
            echo '[ERRO] O ambiente .venv ainda não existe. Execute ./start.sh primeiro.' >&2
            exit 1
        fi
        .venv/bin/python --version
        exit 0
        ;;
    --check-gpu)
        if [[ ! -x .venv/bin/python ]]; then
            echo '[ERRO] O ambiente .venv ainda não existe. Execute ./start.sh primeiro.' >&2
            exit 1
        fi
        .venv/bin/python -m agentic_flow.cli doctor
        exit $?
        ;;
    --install-only|'') ;;
    *)
        echo "[ERRO] Opção desconhecida: $1" >&2
        show_help >&2
        exit 2
        ;;
esac

printf '\n  ========================================\n'
printf '          AGENTIC FLOW - START\n'
printf '  ========================================\n\n'

if [[ -x .venv/bin/python ]] &&
    ! .venv/bin/python -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))' >/dev/null 2>&1; then
    backup_dir=".venv-python-backup-$(date +%Y%m%d%H%M%S)-$$"
    echo "[INFO] A .venv existente não usa Python 3.12; movendo para $backup_dir."
    mv -- .venv "$backup_dir"
fi

if [[ ! -x .venv/bin/python ]]; then
    echo '[INFO] Criando ambiente virtual em .venv...'
    create_venv
fi

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
INSTALL_MARKER="$SCRIPT_DIR/.venv/.agentic-flow-installed"

if [[ ! -f "$INSTALL_MARKER" || pyproject.toml -nt "$INSTALL_MARKER" ]]; then
    echo '[INFO] Instalando AgenticFlow no ambiente local...'
    "$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
    "$VENV_PYTHON" -m pip install -e .

    echo '[INFO] Detectando hardware e instalando o runtime adequado...'
    "$VENV_PYTHON" -m agentic_flow.cli install
    touch "$INSTALL_MARKER"
else
    echo '[OK] Dependências já estão instaladas.'
fi

if [[ "${1:-}" == '--install-only' ]]; then
    echo '[OK] Instalação concluída.'
    exit 0
fi

export AGENTIC_FLOW_DATA_DIR="${AGENTIC_FLOW_DATA_DIR:-$SCRIPT_DIR/data}"
export AGENTIC_FLOW_HOST="${AGENTIC_FLOW_HOST:-127.0.0.1}"
export AGENTIC_FLOW_PORT="${AGENTIC_FLOW_PORT:-16777}"
mkdir -p -- "$AGENTIC_FLOW_DATA_DIR"

printf '\n[OK] Ambiente pronto.\n'
printf '[OK] Agentic Flow: http://%s:%s\n' "$AGENTIC_FLOW_HOST" "$AGENTIC_FLOW_PORT"
printf '[INFO] Pressione Ctrl+C para encerrar.\n\n'

native_restarts=0
while true; do
    set +e
    "$VENV_PYTHON" -m agentic_flow.cli serve --skip-runtime --no-browser \
        --host "$AGENTIC_FLOW_HOST" --port "$AGENTIC_FLOW_PORT"
    app_exit=$?
    set -e

    if (( app_exit == 0 || app_exit == 130 )); then
        exit "$app_exit"
    fi
    if (( app_exit != 134 && app_exit != 139 )); then
        echo "[ERRO] O Agentic Flow encerrou com código $app_exit." >&2
        exit "$app_exit"
    fi

    ((native_restarts += 1))
    if (( native_restarts >= 3 )); then
        echo '[ERRO] O runtime nativo falhou repetidamente; o reinício automático foi interrompido.' >&2
        exit "$app_exit"
    fi
    echo "[AVISO] O runtime nativo foi interrompido; reiniciando o servidor ($native_restarts/3)..." >&2
    sleep 2
done
