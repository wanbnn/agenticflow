from __future__ import annotations

from typing import Any

from pyreact.server import render_to_static_markup
from sixcons import icon as six_icon

from .databases import DATABASE_TYPES


NODE_CATALOG: list[dict[str, Any]] = [
    {
        "type": "input",
        "name": "Entrada JSON",
        "description": "Entrada genérica para integrações e dados estruturados.",
        "category": "Gatilhos",
        "color": "#7c5cff",
        "icon": "IN",
        "defaults": {"field": "message"},
        "fields": [
            {"key": "field", "label": "Campo principal", "type": "text"},
        ],
    },
    {
        "type": "text_input",
        "name": "Entrada de texto",
        "description": "Recebe texto em um campo amigável no playground.",
        "category": "Entradas",
        "color": "#8b5cf6",
        "icon": "TXT",
        "inputs": [],
        "outputs": [
            {"id": "default", "label": "texto", "kind": "flow", "data_type": "text"}
        ],
        "defaults": {"input_key": "text", "placeholder": "Digite ou cole o texto..."},
        "fields": [
            {"key": "placeholder", "label": "Texto de orientação", "type": "text"},
            {
                "key": "input_key",
                "label": "Chave técnica",
                "type": "text",
                "advanced": True,
            },
        ],
    },
    {
        "type": "image_input",
        "name": "Entrada de imagem",
        "description": "Permite selecionar ou arrastar uma imagem com pré-visualização.",
        "category": "Entradas",
        "color": "#0ea5e9",
        "icon": "IMG",
        "inputs": [],
        "outputs": [
            {"id": "default", "label": "imagem", "kind": "flow", "data_type": "image"}
        ],
        "defaults": {"input_key": "image"},
        "fields": [
            {
                "key": "input_key",
                "label": "Chave técnica",
                "type": "text",
                "advanced": True,
            }
        ],
    },
    {
        "type": "video_input",
        "name": "Entrada de vídeo",
        "description": "Permite selecionar ou arrastar um vídeo com player integrado.",
        "category": "Entradas",
        "color": "#6366f1",
        "icon": "VID",
        "inputs": [],
        "outputs": [
            {"id": "default", "label": "vídeo", "kind": "flow", "data_type": "video"}
        ],
        "defaults": {"input_key": "video"},
        "fields": [
            {
                "key": "input_key",
                "label": "Chave técnica",
                "type": "text",
                "advanced": True,
            }
        ],
    },
    {
        "type": "webhook",
        "name": "Webhook",
        "description": "Recebe mensagens externas por uma URL exclusiva.",
        "category": "Gatilhos",
        "color": "#f97316",
        "icon": "WH",
        "defaults": {
            "webhook_id": "",
            "response_mode": "workflow_result",
        },
        "fields": [
            {
                "key": "webhook_id",
                "label": "URL do webhook",
                "type": "webhook_url",
            },
            {
                "key": "response_mode",
                "label": "Resposta HTTP",
                "type": "select",
                "options": ["workflow_result", "accepted"],
            },
        ],
    },
    {
        "type": "prompt",
        "name": "Prompt",
        "description": "Monta instruções usando variáveis {{campo}}.",
        "category": "IA",
        "color": "#a855f7",
        "icon": "PR",
        "defaults": {
            "template": "Você é um analista prestativo. Responda à solicitação:\n\n{{message}}"
        },
        "fields": [
            {"key": "template", "label": "Template", "type": "textarea"},
        ],
    },
    {
        "type": "llm",
        "name": "Modelo LLM",
        "description": "Executa uma chamada direta a um modelo.",
        "category": "IA",
        "color": "#ec4899",
        "icon": "AI",
        "defaults": {
            "provider_id": "mock",
            "model": "",
            "system_prompt": "Seja objetivo e útil.",
            "temperature": 0.2,
        },
        "fields": [
            {
                "key": "provider_id",
                "label": "Provedor",
                "type": "provider_select",
            },
            {"key": "model", "label": "Modelo (opcional)", "type": "text"},
            {"key": "system_prompt", "label": "Instrução do sistema", "type": "textarea"},
            {"key": "temperature", "label": "Temperatura", "type": "number"},
        ],
    },
    {
        "type": "agent",
        "name": "Agente IA",
        "description": "Especialista independente; adicione quantos precisar.",
        "category": "IA",
        "color": "#ec4899",
        "icon": "AG",
        "inputs": [
            {"id": "input", "label": "entrada", "kind": "flow", "multiple": True},
            {"id": "tools", "label": "tools", "kind": "tool", "multiple": True},
        ],
        "defaults": {
            "role": "Especialista",
            "provider_id": "mock",
            "model": "",
            "system_prompt": "Atue como {{role}}. Seja objetivo e útil.",
            "input_field": "prompt",
            "output_field": "response",
            "vector_db_node_id": "",
            "rag_top_k": 5,
            "rag_min_score": 0,
            "temperature": 0.2,
        },
        "fields": [
            {"key": "role", "label": "Papel do agente", "type": "text"},
            {
                "key": "provider_id",
                "label": "Provedor",
                "type": "provider_select",
            },
            {"key": "model", "label": "Modelo (opcional)", "type": "text"},
            {"key": "system_prompt", "label": "Instrução do sistema", "type": "textarea"},
            {"key": "input_field", "label": "Campo de entrada", "type": "text", "advanced": True},
            {"key": "output_field", "label": "Campo de saída", "type": "text", "advanced": True},
            {"key": "rag_top_k", "label": "Trechos recuperados", "type": "number"},
            {
                "key": "rag_min_score",
                "label": "Similaridade mínima",
                "type": "number",
            },
            {"key": "temperature", "label": "Temperatura", "type": "number"},
        ],
    },
    {
        "type": "vector_database",
        "name": "Banco de Vetores",
        "description": "Cria uma base isolada, processa textos recebidos e os mantém indexados.",
        "category": "Conhecimento",
        "color": "#22c55e",
        "icon": "DB",
        "outputs": [
            {"id": "default", "label": "saída", "kind": "flow"},
            {"id": "database", "label": "database", "kind": "database"},
        ],
        "defaults": {
            "input_field": "document_text",
            "output_field": "vector_database",
            "metadata_field": "document_text_metadata",
            "chunk_size": 900,
            "chunk_overlap": 120,
            "write_mode": "append",
        },
        "fields": [
            {"key": "input_field", "label": "Campo com conteúdo", "type": "text"},
            {"key": "metadata_field", "label": "Campo de metadados", "type": "text"},
            {"key": "output_field", "label": "Campo de resultado", "type": "text"},
            {"key": "chunk_size", "label": "Tamanho dos trechos", "type": "number"},
            {"key": "chunk_overlap", "label": "Sobreposição", "type": "number"},
            {
                "key": "write_mode",
                "label": "Modo de gravação",
                "type": "select",
                "options": ["append", "replace"],
            },
        ],
    },
    {
        "type": "rag",
        "name": "Busca RAG",
        "description": "Recupera os trechos mais relevantes de um Banco de Vetores para agentes e modelos.",
        "category": "Conhecimento",
        "color": "#10b981",
        "icon": "RAG",
        "inputs": [
            {"id": "input", "label": "entrada", "kind": "flow", "multiple": True},
            {"id": "database", "label": "database", "kind": "database"},
        ],
        "outputs": [
            {"id": "default", "label": "saída", "kind": "flow"},
            {"id": "tool", "label": "tool", "kind": "tool"},
        ],
        "defaults": {
            "vector_db_node_id": "",
            "query_field": "message",
            "context_field": "rag_context",
            "matches_field": "rag_matches",
            "top_k": 5,
            "min_score": 0,
            "separator": "\n\n---\n\n",
        },
        "fields": [
            {"key": "query_field", "label": "Campo da consulta", "type": "text"},
            {"key": "context_field", "label": "Campo do contexto", "type": "text"},
            {"key": "matches_field", "label": "Campo dos resultados", "type": "text"},
            {"key": "top_k", "label": "Máximo de trechos", "type": "number"},
            {"key": "min_score", "label": "Similaridade mínima", "type": "number"},
            {"key": "separator", "label": "Separador de trechos", "type": "textarea"},
        ],
    },
    {
        "type": "mcp_server",
        "name": "MCP Server",
        "description": "Conecta ferramentas remotas de um servidor MCP ao Agente IA.",
        "category": "Ferramentas",
        "color": "#f97316",
        "icon": "MCP",
        "inputs": [],
        "outputs": [
            {"id": "tool", "label": "tool", "kind": "tool"},
        ],
        "defaults": {
            "url": "http://localhost:8000/mcp",
            "tool_name": "",
            "arguments": "",
            "timeout": 30,
        },
        "fields": [
            {"key": "url", "label": "URL Streamable HTTP", "type": "text"},
            {"key": "tool_name", "label": "Ferramenta preferida (opcional)", "type": "text"},
            {
                "key": "arguments",
                "label": "Argumentos JSON (opcional)",
                "type": "textarea",
            },
            {"key": "timeout", "label": "Timeout (s)", "type": "number"},
        ],
    },
    {
        "type": "condition",
        "name": "Condição",
        "description": "Divide o fluxo em saídas verdadeiro e falso.",
        "category": "Lógica",
        "color": "#f59e0b",
        "icon": "IF",
        "defaults": {"field": "approved", "operator": "equals", "value": "true"},
        "fields": [
            {"key": "field", "label": "Campo", "type": "text"},
            {
                "key": "operator",
                "label": "Operador",
                "type": "select",
                "options": ["equals", "not_equals", "contains", "gt", "gte", "lt", "lte", "exists"],
            },
            {"key": "value", "label": "Valor", "type": "text"},
        ],
        "handles": ["true", "false"],
    },
    {
        "type": "file",
        "name": "Ler documento",
        "description": "Extrai texto e metadados de PDF, TXT, Markdown, CSV, JSON, DOCX e XLSX.",
        "category": "Arquivos e mídia",
        "color": "#14b8a6",
        "icon": "DOC",
        "defaults": {
            "input_field": "file",
            "output_field": "document_text",
            "format": "auto",
            "encoding": "utf-8",
            "max_characters": 200000,
        },
        "fields": [
            {"key": "input_field", "label": "Campo do arquivo", "type": "text", "advanced": True},
            {"key": "output_field", "label": "Campo do texto extraído", "type": "text", "advanced": True},
            {
                "key": "format",
                "label": "Formato",
                "type": "select",
                "options": [
                    "auto",
                    "pdf",
                    "txt",
                    "md",
                    "csv",
                    "json",
                    "xml",
                    "html",
                    "yaml",
                    "docx",
                    "xlsx",
                ],
            },
            {"key": "encoding", "label": "Codificação de texto", "type": "text"},
            {"key": "max_characters", "label": "Limite de caracteres", "type": "number"},
        ],
    },
    {
        "type": "image",
        "name": "Processar imagem",
        "description": "Inspeciona, redimensiona, converte ou aplica escala de cinza em imagens.",
        "category": "Arquivos e mídia",
        "color": "#0ea5e9",
        "icon": "IMG",
        "inputs": [
            {"id": "input", "label": "imagem", "kind": "flow", "data_type": "image", "multiple": False}
        ],
        "outputs": [
            {"id": "default", "label": "imagem", "kind": "flow", "data_type": "image"}
        ],
        "defaults": {
            "input_field": "image",
            "output_field": "processed_image",
            "operation": "inspect",
            "output_format": "PNG",
            "width": 1280,
            "height": 1280,
            "quality": 90,
        },
        "fields": [
            {"key": "input_field", "label": "Campo da imagem", "type": "text", "advanced": True},
            {"key": "output_field", "label": "Campo de saída", "type": "text", "advanced": True},
            {
                "key": "operation",
                "label": "Operação",
                "type": "select",
                "options": ["inspect", "resize", "convert", "grayscale"],
            },
            {
                "key": "output_format",
                "label": "Formato de saída",
                "type": "select",
                "options": ["PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF"],
            },
            {"key": "width", "label": "Largura máxima", "type": "number"},
            {"key": "height", "label": "Altura máxima", "type": "number"},
            {"key": "quality", "label": "Qualidade", "type": "number"},
        ],
    },
    {
        "type": "video_frames",
        "name": "Vídeo para frames",
        "description": "Transforma MP4, WebM, MOV, AVI e outros vídeos em uma sequência de imagens.",
        "category": "Arquivos e mídia",
        "color": "#6366f1",
        "icon": "VID",
        "inputs": [
            {"id": "input", "label": "vídeo", "kind": "flow", "data_type": "video", "multiple": False}
        ],
        "outputs": [
            {"id": "default", "label": "frames", "kind": "flow", "data_type": "frames"}
        ],
        "defaults": {
            "input_field": "video",
            "output_field": "frames",
            "interval_seconds": 1,
            "max_frames": 12,
            "output_format": "jpeg",
            "quality": 88,
        },
        "fields": [
            {"key": "input_field", "label": "Campo do vídeo", "type": "text", "advanced": True},
            {"key": "output_field", "label": "Campo dos frames", "type": "text", "advanced": True},
            {"key": "interval_seconds", "label": "Intervalo em segundos", "type": "number"},
            {"key": "max_frames", "label": "Máximo de frames", "type": "number"},
            {
                "key": "output_format",
                "label": "Formato dos frames",
                "type": "select",
                "options": ["jpeg", "png"],
            },
            {"key": "quality", "label": "Qualidade JPEG", "type": "number"},
        ],
    },
    {
        "type": "transform",
        "name": "Transformar",
        "description": "Cria ou altera um campo a partir de um template.",
        "category": "Dados",
        "color": "#06b6d4",
        "icon": "TF",
        "defaults": {"target": "result", "template": "{{message}}"},
        "fields": [
            {"key": "target", "label": "Campo de destino", "type": "text"},
            {"key": "template", "label": "Template", "type": "textarea"},
        ],
    },
    {
        "type": "http",
        "name": "HTTP Request",
        "description": "Integra com APIs REST externas.",
        "category": "Conectores",
        "color": "#10b981",
        "icon": "HT",
        "defaults": {"method": "GET", "url": "https://httpbin.org/json", "timeout": 15},
        "fields": [
            {"key": "method", "label": "Método", "type": "select", "options": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
            {"key": "url", "label": "URL", "type": "text"},
            {"key": "timeout", "label": "Timeout (s)", "type": "number"},
        ],
    },
    {
        "type": "memory",
        "name": "Memória",
        "description": "Mantém contexto durante a execução do agente.",
        "category": "IA",
        "color": "#8b5cf6",
        "icon": "ME",
        "defaults": {"key": "conversation", "source": "message"},
        "fields": [
            {"key": "key", "label": "Chave da memória", "type": "text"},
            {"key": "source", "label": "Campo de origem", "type": "text"},
        ],
    },
    {
        "type": "output",
        "name": "Saída",
        "description": "Define a resposta final do workflow.",
        "category": "Dados",
        "color": "#3b82f6",
        "icon": "OUT",
        "defaults": {"field": "response"},
        "fields": [
            {"key": "field", "label": "Campo de saída", "type": "text", "advanced": True},
        ],
    },
]


def _database_node(definition: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": definition["node_type"],
        "name": definition["name"],
        "description": (
            f"Consulta {definition['name']} em modo somente leitura e "
            "disponibiliza schema e dados ao Agente IA."
        ),
        "category": "Bancos de dados",
        "color": definition["color"],
        "icon": definition["icon"],
        "inputs": [
            {"id": "input", "label": "entrada", "kind": "flow", "multiple": True}
        ],
        "outputs": [
            {"id": "default", "label": "resultado", "kind": "flow"},
            {"id": "tool", "label": "tool", "kind": "tool"},
        ],
        "defaults": {
            "connection_id": "",
            "operation": "auto",
            "query": "",
            "schema_name": "",
            "tables": "",
            "max_rows": 200,
            "output_field": "database_result",
        },
        "fields": [
            {
                "key": "connection_id",
                "label": f"Conexão {definition['name']}",
                "type": "database_connection_select",
                "database_type": definition["type"],
            },
            {
                "key": "operation",
                "label": "Operação",
                "type": "select",
                "options": ["auto", "schema", "query"],
            },
            {
                "key": "query",
                "label": "Consulta de leitura",
                "type": "textarea",
                "placeholder": "SELECT * FROM tabela WHERE id = {{id}}",
            },
            {
                "key": "schema_name",
                "label": "Schema (opcional)",
                "type": "text",
            },
            {
                "key": "tables",
                "label": "Tabelas permitidas (separadas por vírgula)",
                "type": "text",
            },
            {
                "key": "max_rows",
                "label": "Máximo de linhas",
                "type": "number",
            },
            {
                "key": "output_field",
                "label": "Campo de resultado",
                "type": "text",
                "advanced": True,
            },
        ],
    }


NODE_CATALOG.extend(_database_node(item) for item in DATABASE_TYPES)

NODE_ICON_NAMES = {
    "input": "braces",
    "text_input": "type",
    "image_input": "image",
    "video_input": "video",
    "webhook": "webhook",
    "prompt": "message-square-code",
    "llm": "cpu",
    "agent": "bot",
    "vector_database": "database-zap",
    "rag": "search-code",
    "mcp_server": "plug-zap",
    "condition": "git-branch",
    "file": "file-text",
    "image": "image",
    "video_frames": "film",
    "transform": "shuffle",
    "http": "globe",
    "memory": "brain",
    "output": "circle-check",
}

for item in NODE_CATALOG:
    icon_name = NODE_ICON_NAMES.get(item["type"], "database")
    item["icon_name"] = icon_name
    item["icon_svg"] = render_to_static_markup(
        six_icon(
            icon_name,
            size=18,
            stroke_width=1.8,
            class_name="catalog-lucide-icon",
        )
    )


CATALOG_BY_TYPE = {item["type"]: item for item in NODE_CATALOG}
