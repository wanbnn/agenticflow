from agentic_flow.ui import render_auth_page, render_page


def test_editor_uses_uikitpr_provider_and_6cons_icons() -> None:
    html = render_page("workflow-test")

    assert 'class="uipr-root min-h-screen agenticflow-ui"' in html
    assert 'data-uipr-theme="dark"' in html
    assert 'data-uikitpr="core"' in html
    assert "uipr-button" in html
    assert "lucide-sparkles" in html
    assert "lucide-play" in html
    assert "lucide-wand-sparkles" in html
    assert 'data-workflow-id="workflow-test"' in html


def test_auth_page_uses_shared_design_system() -> None:
    html = render_auth_page("login")

    assert 'data-uipr-color-mode="dark"' in html
    assert "lucide-arrow-right" in html
    assert "/static/styles.css?v=" in html
