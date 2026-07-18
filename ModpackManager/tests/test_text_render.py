from modpack_manager.text_render import render_markdown, sanitize_html


def test_render_markdown_makes_html():
    out = render_markdown("- one\n- two")
    assert "<li>one</li>" in out
    assert "<li>two</li>" in out


def test_render_markdown_strips_scripts():
    out = render_markdown("hello <script>alert(1)</script>")
    assert "<script>" not in out


def test_sanitize_html_keeps_basic_tags_drops_danger():
    out = sanitize_html('<p onclick="x()">hi <b>there</b></p><script>bad()</script>')
    assert "<b>there</b>" in out
    assert "onclick" not in out
    assert "<script>" not in out


def test_empty_changelog_returns_empty_string():
    assert render_markdown("") == ""
    assert render_markdown(None) == ""
