#!/bin/sh

set -eu

printf '\n  AGENTICFLOW - INSTALADOR LINUX\n\n'

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return 0
    fi
    if [ -n "${HOME:-}" ] && [ -x "$HOME/.local/bin/uv" ]; then
        printf '%s\n' "$HOME/.local/bin/uv"
        return 0
    fi
    return 1
}

UV_BIN="$(find_uv || true)"
if [ -z "$UV_BIN" ]; then
    if ! command -v curl >/dev/null 2>&1; then
        printf '[ERRO] curl não foi encontrado. Instale curl e tente novamente.\n' >&2
        exit 1
    fi
    printf '[INFO] Instalando o gerenciador de ambientes uv...\n'
    curl -LsSf https://astral.sh/uv/install.sh | sh
    UV_BIN="$(find_uv || true)"
fi

if [ -z "$UV_BIN" ]; then
    printf '[ERRO] uv foi instalado, mas não foi localizado nesta sessão.\n' >&2
    exit 1
fi

printf '[INFO] Preparando Python 3.12 e o ambiente isolado...\n'
"$UV_BIN" python install 3.12
# O CLI instala o runtime de IA com `python -m pip`, portanto o ambiente da
# ferramenta inclui pip explicitamente.
"$UV_BIN" tool install --force --python 3.12 --with pip agenticflow-studio

# Garante que o diretório dos comandos instalados seja persistido no PATH dos
# próximos terminais. Falhas aqui não invalidam uma instalação já concluída.
"$UV_BIN" tool update-shell >/dev/null 2>&1 || true

printf '[INFO] Detectando GPU e preparando CUDA/ROCm/CPU...\n'
TOOL_BIN_DIR="$("$UV_BIN" tool dir --bin)"
AGENTICFLOW_BIN="$TOOL_BIN_DIR/agenticflow"
if [ ! -x "$AGENTICFLOW_BIN" ]; then
    printf '[ERRO] O pacote foi instalado, mas o comando agenticflow não foi localizado.\n' >&2
    exit 1
fi
"$AGENTICFLOW_BIN" install

printf '\n[OK] AgenticFlow instalado com sucesso.\n'
printf 'Abra um novo terminal e execute: agenticflow\n'
