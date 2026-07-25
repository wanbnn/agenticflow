from __future__ import annotations

from typing import Any

from .models import Edge, Node, Position, WorkflowCreate


def _node(
    node_id: str,
    node_type: str,
    name: str,
    x: int,
    y: int,
    config: dict[str, Any],
) -> Node:
    return Node(
        id=node_id,
        type=node_type,
        name=name,
        position=Position(x=x, y=y),
        config=config,
    )


def _workflow(
    name: str,
    description: str,
    nodes: list[Node],
) -> WorkflowCreate:
    return WorkflowCreate(
        name=name,
        description=description,
        nodes=nodes,
        edges=[
            Edge(
                id=f"edge-{index}",
                source=nodes[index].id,
                target=nodes[index + 1].id,
            )
            for index in range(len(nodes) - 1)
        ],
    )


WORKFLOW_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "document-summary",
        "name": "Resumir documento com IA",
        "description": "Extrai texto de PDF, DOCX, TXT ou Markdown e produz um resumo executivo.",
        "category": "Documentos",
        "icon": "DOC",
        "color": "#14b8a6",
        "featured": True,
        "tags": ["PDF", "DOCX", "IA"],
        "workflow": _workflow(
            "Resumo inteligente de documento",
            "Extrai o conteúdo de um documento e gera um resumo executivo.",
            [
                _node("input", "input", "Receber documento", 80, 220, {"field": "file"}),
                _node(
                    "file",
                    "file",
                    "Extrair conteúdo",
                    360,
                    220,
                    {
                        "input_field": "file",
                        "output_field": "document_text",
                        "format": "auto",
                        "encoding": "utf-8",
                        "max_characters": 200000,
                    },
                ),
                _node(
                    "prompt",
                    "prompt",
                    "Preparar resumo",
                    640,
                    220,
                    {
                        "template": "Resuma o documento abaixo. Destaque decisões, riscos e próximos passos.\n\n{{document_text}}"
                    },
                ),
                _node(
                    "agent",
                    "agent",
                    "Analista de documentos",
                    920,
                    220,
                    {
                        "role": "Analista executivo",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Produza resumos claros, fiéis e estruturados.",
                        "input_field": "prompt",
                        "output_field": "response",
                        "temperature": 0.1,
                    },
                ),
                _node("output", "output", "Resumo final", 1200, 220, {"field": "response"}),
            ],
        ),
    },
    {
        "id": "image-optimizer",
        "name": "Otimizar imagem",
        "description": "Redimensiona e converte PNG, JPEG, WebP, GIF, BMP ou TIFF.",
        "category": "Imagens",
        "icon": "IMG",
        "color": "#0ea5e9",
        "featured": True,
        "tags": ["PNG", "JPEG", "WebP"],
        "workflow": _workflow(
            "Otimização de imagem",
            "Padroniza imagens para publicação e integrações.",
            [
                _node("input", "image_input", "Receber imagem", 140, 230, {"input_key": "image"}),
                _node(
                    "image",
                    "image",
                    "Redimensionar e converter",
                    460,
                    230,
                    {
                        "input_field": "image",
                        "output_field": "processed_image",
                        "operation": "resize",
                        "output_format": "WEBP",
                        "width": 1280,
                        "height": 1280,
                        "quality": 88,
                    },
                ),
                _node(
                    "output",
                    "output",
                    "Imagem otimizada",
                    780,
                    230,
                    {"field": "processed_image"},
                ),
            ],
        ),
    },
    {
        "id": "video-to-frames",
        "name": "Extrair frames de vídeo",
        "description": "Converte vídeos em uma sequência controlada de imagens JPEG ou PNG.",
        "category": "Vídeo",
        "icon": "VID",
        "color": "#6366f1",
        "featured": True,
        "tags": ["MP4", "Frames", "Imagem"],
        "workflow": _workflow(
            "Vídeo para frames",
            "Extrai frames de um vídeo em intervalos configuráveis.",
            [
                _node("input", "video_input", "Receber vídeo", 140, 230, {"input_key": "video"}),
                _node(
                    "video",
                    "video_frames",
                    "Extrair frames",
                    460,
                    230,
                    {
                        "input_field": "video",
                        "output_field": "frames",
                        "interval_seconds": 1,
                        "max_frames": 12,
                        "output_format": "jpeg",
                        "quality": 88,
                    },
                ),
                _node("output", "output", "Frames gerados", 780, 230, {"field": "frames"}),
            ],
        ),
    },
    {
        "id": "webhook-support",
        "name": "Atendimento por webhook",
        "description": "Recebe solicitações externas, processa com um agente e devolve a resposta.",
        "category": "Atendimento",
        "icon": "WH",
        "color": "#f97316",
        "featured": False,
        "tags": ["Webhook", "Agente", "API"],
        "workflow": _workflow(
            "Atendimento inteligente",
            "Atendimento automatizado acionado por webhook.",
            [
                _node(
                    "webhook",
                    "webhook",
                    "Nova solicitação",
                    120,
                    220,
                    {"webhook_id": "", "response_mode": "workflow_result"},
                ),
                _node(
                    "agent",
                    "agent",
                    "Agente de atendimento",
                    440,
                    220,
                    {
                        "role": "Especialista em atendimento",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Responda com clareza, cordialidade e objetividade.",
                        "input_field": "message",
                        "output_field": "response",
                        "temperature": 0.2,
                    },
                ),
                _node("output", "output", "Enviar resposta", 760, 220, {"field": "response"}),
            ],
        ),
    },
    {
        "id": "research-review",
        "name": "Pesquisa com revisão",
        "description": "Dois agentes pesquisam e revisam uma resposta antes da entrega.",
        "category": "Produtividade",
        "icon": "AI",
        "color": "#ec4899",
        "featured": False,
        "tags": ["Multiagente", "Revisão", "Pesquisa"],
        "workflow": _workflow(
            "Pesquisa com revisão",
            "Pipeline multiagente para respostas pesquisadas e revisadas.",
            [
                _node(
                    "input",
                    "text_input",
                    "Nova pesquisa",
                    80,
                    220,
                    {
                        "input_key": "text",
                        "placeholder": "Qual tema devemos pesquisar?",
                    },
                ),
                _node(
                    "prompt",
                    "prompt",
                    "Preparar contexto",
                    360,
                    220,
                    {"template": "Pesquise e responda com evidências:\n\n{{message}}"},
                ),
                _node(
                    "researcher",
                    "agent",
                    "Agente pesquisador",
                    640,
                    220,
                    {
                        "role": "Pesquisador",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Investigue o tema e estruture os achados.",
                        "input_field": "prompt",
                        "output_field": "research",
                        "temperature": 0.2,
                    },
                ),
                _node(
                    "reviewer",
                    "agent",
                    "Agente revisor",
                    920,
                    220,
                    {
                        "role": "Revisor",
                        "provider_id": "mock",
                        "model": "",
                        "system_prompt": "Revise os achados e produza uma resposta final.",
                        "input_field": "research",
                        "output_field": "response",
                        "temperature": 0.1,
                    },
                ),
                _node("output", "output", "Resposta final", 1200, 220, {"field": "response"}),
            ],
        ),
    },
]


TEMPLATES_BY_ID = {item["id"]: item for item in WORKFLOW_TEMPLATES}


def template_catalog() -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in template.items()
            if key != "workflow"
        }
        | {
            "node_types": sorted(
                {node.type for node in template["workflow"].nodes}
            ),
            "nodes_count": len(template["workflow"].nodes),
        }
        for template in WORKFLOW_TEMPLATES
    ]


def instantiate_template(template_id: str, name: str | None = None) -> WorkflowCreate:
    template = TEMPLATES_BY_ID.get(template_id)
    if not template:
        raise KeyError(template_id)
    workflow = template["workflow"].model_copy(deep=True)
    if name and name.strip():
        workflow.name = name.strip()
    return workflow
