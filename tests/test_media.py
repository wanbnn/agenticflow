import base64
import io

from PIL import Image
from pypdf import PdfWriter

from agentic_flow.engine import WorkflowEngine, validate_workflow
from agentic_flow.media import process_image, read_document
from agentic_flow.models import Edge, Node, Position, RunRequest, Workflow
from agentic_flow.templates import WORKFLOW_TEMPLATES, instantiate_template


def data_uri(payload: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(payload).decode()}"


def test_text_and_markdown_document_reader():
    result = read_document(
        {
            "name": "manual.md",
            "mime_type": "text/markdown",
            "data": data_uri(
                "# Manual\n\nConteúdo importante.".encode(), "text/markdown"
            ),
        },
        {"format": "auto", "encoding": "utf-8", "max_characters": 1000},
    )
    assert "Conteúdo importante" in result["text"]
    assert result["metadata"]["extension"] == ".md"
    assert result["metadata"]["truncated"] is False


def test_image_node_resizes_and_returns_reusable_data_uri():
    source = io.BytesIO()
    Image.new("RGB", (80, 40), "#7657ff").save(source, format="PNG")
    result = process_image(
        {
            "name": "banner.png",
            "mime_type": "image/png",
            "data": data_uri(source.getvalue(), "image/png"),
        },
        {
            "operation": "resize",
            "width": 20,
            "height": 20,
            "output_format": "WEBP",
            "quality": 85,
        },
    )
    assert result["data_uri"].startswith("data:image/webp;base64,")
    assert result["metadata"]["width"] == 20
    assert result["metadata"]["height"] == 10
    assert result["metadata"]["original_width"] == 80


def test_typed_image_input_flows_without_manual_field_mapping():
    source = io.BytesIO()
    Image.new("RGB", (64, 32), "#7657ff").save(source, format="PNG")
    workflow = Workflow(
        name="Imagem tipada",
        nodes=[
            Node(
                id="input",
                type="image_input",
                name="Escolher imagem",
                config={"input_key": "image"},
            ),
            Node(
                id="process",
                type="image",
                name="Processar",
                config={
                    "operation": "resize",
                    "width": 16,
                    "height": 16,
                    "output_format": "PNG",
                },
            ),
            Node(id="output", type="output", name="Visualizar", config={}),
        ],
        edges=[
            Edge(source="input", target="process"),
            Edge(source="process", target="output"),
        ],
    )
    result = WorkflowEngine().run(
        workflow,
        RunRequest(
            input={
                "image": {
                    "name": "source.png",
                    "mime_type": "image/png",
                    "data": data_uri(source.getvalue(), "image/png"),
                }
            }
        ),
    )
    assert result.status == "success"
    assert result.output["data_uri"].startswith("data:image/png;base64,")
    assert result.output["metadata"]["width"] == 16
    assert [event.node_id for event in result.events] == [
        "input",
        "process",
        "output",
    ]


def test_incompatible_typed_media_connections_are_rejected():
    workflow = Workflow(
        name="Tipos incompatíveis",
        nodes=[
            Node(id="image", type="image_input", name="Imagem"),
            Node(id="frames", type="video_frames", name="Frames"),
        ],
        edges=[Edge(source="image", target="frames")],
    )
    try:
        validate_workflow(workflow)
    except ValueError as exc:
        assert "espera video" in str(exc)
    else:
        raise AssertionError("Imagem não deveria conectar em uma entrada de vídeo")


def test_pdf_document_reader_reports_pages():
    source = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(source)
    result = read_document(
        {
            "name": "arquivo.pdf",
            "mime_type": "application/pdf",
            "data": data_uri(source.getvalue(), "application/pdf"),
        },
        {"format": "auto", "max_characters": 1000},
    )
    assert result["metadata"]["extension"] == ".pdf"
    assert result["metadata"]["pages_or_sheets"] == 1


def test_file_node_executes_inside_workflow():
    workflow = Workflow(
        name="Ler arquivo",
        nodes=[
            Node(
                id="file",
                type="file",
                name="Documento",
                position=Position(),
                config={
                    "input_field": "file",
                    "output_field": "document_text",
                    "format": "auto",
                },
            ),
            Node(
                id="output",
                type="output",
                name="Texto",
                position=Position(x=200),
                config={"field": "document_text"},
            ),
        ],
        edges=[Edge(source="file", target="output")],
    )
    result = WorkflowEngine().run(
        workflow,
        RunRequest(
            input={
                "file": {
                    "name": "notas.txt",
                    "data": data_uri(b"linha um\nlinha dois", "text/plain"),
                }
            }
        ),
    )
    assert result.status == "success"
    assert result.output == "linha um\nlinha dois"


def test_all_builtin_templates_are_valid_workflows():
    for template in WORKFLOW_TEMPLATES:
        workflow_create = instantiate_template(template["id"])
        workflow = Workflow(**workflow_create.model_dump())
        validate_workflow(workflow)
        assert workflow.nodes
