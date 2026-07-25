from agentic_flow.engine import WorkflowEngine, WorkflowValidationError, render_template, validate_workflow
from agentic_flow.models import Edge, Node, Position, RunRequest, Workflow


def make_workflow() -> Workflow:
    return Workflow(
        name="Teste",
        nodes=[
            Node(id="a", type="input", name="Entrada", position=Position(x=0, y=0)),
            Node(
                id="b",
                type="prompt",
                name="Prompt",
                position=Position(x=200, y=0),
                config={"template": "Olá, {{user.name}}!"},
            ),
            Node(
                id="c",
                type="llm",
                name="LLM",
                position=Position(x=400, y=0),
                config={"provider": "mock"},
            ),
            Node(
                id="d",
                type="output",
                name="Saída",
                position=Position(x=600, y=0),
                config={"field": "response"},
            ),
        ],
        edges=[
            Edge(source="a", target="b"),
            Edge(source="b", target="c"),
            Edge(source="c", target="d"),
        ],
    )


def test_template_supports_nested_values():
    assert render_template("Oi {{ person.name }}", {"person": {"name": "Ada"}}) == "Oi Ada"


def test_typed_text_input_feeds_agent_without_field_configuration():
    workflow = Workflow(
        name="Texto fácil",
        nodes=[
            Node(
                id="text",
                type="text_input",
                name="Pergunta",
                config={"input_key": "text"},
            ),
            Node(
                id="agent",
                type="agent",
                name="Assistente",
                config={"role": "Assistente", "provider_id": "mock"},
            ),
            Node(id="output", type="output", name="Resposta", config={}),
        ],
        edges=[
            Edge(source="text", target="agent"),
            Edge(source="agent", target="output"),
        ],
    )
    result = WorkflowEngine().run(
        workflow, RunRequest(input={"text": "Explique este recurso"})
    )
    assert result.status == "success"
    assert "Explique este recurso" in result.output


def test_langgraph_executes_visual_workflow():
    result = WorkflowEngine().run(
        make_workflow(),
        RunRequest(input={"user": {"name": "Ada"}}),
    )
    assert result.status == "success"
    assert result.output == "Resposta simulada do agente: Olá, Ada!"
    assert [event.node_id for event in result.events] == ["a", "b", "c", "d"]


def test_cycle_is_rejected():
    workflow = make_workflow()
    workflow.edges.append(Edge(source="d", target="a"))
    try:
        validate_workflow(workflow)
    except WorkflowValidationError as exc:
        assert "ciclo" in str(exc)
    else:
        raise AssertionError("Um ciclo deveria ser rejeitado")


def test_condition_routes_to_true_branch():
    workflow = Workflow(
        name="Condição",
        nodes=[
            Node(id="in", type="input", name="Entrada"),
            Node(
                id="if",
                type="condition",
                name="Aprovado?",
                config={"field": "approved", "operator": "equals", "value": "true"},
            ),
            Node(id="yes", type="transform", name="Sim", config={"target": "answer", "template": "aprovado"}),
            Node(id="no", type="transform", name="Não", config={"target": "answer", "template": "reprovado"}),
            Node(id="out-yes", type="output", name="Saída sim", config={"field": "answer"}),
            Node(id="out-no", type="output", name="Saída não", config={"field": "answer"}),
        ],
        edges=[
            Edge(source="in", target="if"),
            Edge(source="if", target="yes", source_handle="true"),
            Edge(source="if", target="no", source_handle="false"),
            Edge(source="yes", target="out-yes"),
            Edge(source="no", target="out-no"),
        ],
    )
    result = WorkflowEngine().run(workflow, RunRequest(input={"approved": True}))
    assert result.status == "success"
    assert result.output == "aprovado"
    assert "no" not in [event.node_id for event in result.events]


def test_multiple_agents_can_pass_results_between_each_other():
    workflow = Workflow(
        name="Equipe",
        nodes=[
            Node(id="in", type="input", name="Entrada"),
            Node(
                id="researcher",
                type="agent",
                name="Pesquisador",
                config={
                    "role": "Pesquisador",
                    "provider": "mock",
                    "input_field": "message",
                    "output_field": "research",
                },
            ),
            Node(
                id="reviewer",
                type="agent",
                name="Revisor",
                config={
                    "role": "Revisor",
                    "provider": "mock",
                    "input_field": "research",
                    "output_field": "final",
                },
            ),
            Node(id="out", type="output", name="Saída", config={"field": "final"}),
        ],
        edges=[
            Edge(source="in", target="researcher"),
            Edge(source="researcher", target="reviewer"),
            Edge(source="reviewer", target="out"),
        ],
    )
    result = WorkflowEngine().run(workflow, RunRequest(input={"message": "Tema original"}))
    assert result.status == "success"
    assert "Resposta simulada de Revisor" in result.output
    assert "Resposta simulada de Pesquisador" in result.output


def test_agent_uses_provider_selected_in_visual_configuration():
    class FakeProviderRuntime:
        def __init__(self):
            self.call = None

        def chat(self, **kwargs):
            self.call = kwargs
            return "resposta do provedor visual"

    runtime = FakeProviderRuntime()
    workflow = Workflow(
        name="Provedor visual",
        nodes=[
            Node(id="in", type="input", name="Entrada"),
            Node(
                id="agent",
                type="agent",
                name="Especialista",
                config={
                    "role": "Especialista",
                    "provider_id": "prv-visual",
                    "model": "",
                    "input_field": "message",
                    "output_field": "response",
                },
            ),
            Node(id="out", type="output", name="Saída", config={"field": "response"}),
        ],
        edges=[Edge(source="in", target="agent"), Edge(source="agent", target="out")],
    )
    result = WorkflowEngine(runtime).run(
        workflow,
        RunRequest(input={"message": "olá"}),
        workspace_id="ws-teste",
    )
    assert result.status == "success"
    assert result.output == "resposta do provedor visual"
    assert runtime.call["provider_id"] == "prv-visual"
    assert runtime.call["workspace_id"] == "ws-teste"
    assert runtime.call["prompt"] == "olá"
