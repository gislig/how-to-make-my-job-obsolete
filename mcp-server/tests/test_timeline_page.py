from fakes import FakeBackend

from obsolete_mcp.timeline_page import collect, render_html


def test_page_renders_and_escapes():
    fb = FakeBackend()
    fb.app["latestRevision"] = "<script>alert(1)</script>"
    app, events = collect(fb, "ca-demo-web", 3)
    page = render_html(app, events, 3)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    for kind in ("scaling", "change", "alert", "agent"):
        assert kind in page
