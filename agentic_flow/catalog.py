from __future__ import annotations

from typing import Any


NODE_CATALOG: list[dict[str, Any]] = [
    {
        "type": "input",
        "name": "Entrada",
        "description": "Inicia o fluxo com os dados recebidos.",
        "category": "Gatilhos",
        "color": "#7c5cff",
        "icon": "IN",
        "defaults": {"field": "message"},
        "fields": [
            {"key": "field", "label": "Campo principal", "type": "text"},
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
        "defaults": {
            "role": "Especialista",
            "provider_id": "mock",
            "model": "",
            "system_prompt": "Atue como {{role}}. Seja objetivo e útil.",
            "input_field": "prompt",
            "output_field": "response",
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
            {"key": "input_field", "label": "Campo de entrada", "type": "text"},
            {"key": "output_field", "label": "Campo de saída", "type": "text"},
            {"key": "temperature", "label": "Temperatura", "type": "number"},
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
            {"key": "field", "label": "Campo de saída", "type": "text"},
        ],
    },
]


CATALOG_BY_TYPE = {item["type"]: item for item in NODE_CATALOG}
