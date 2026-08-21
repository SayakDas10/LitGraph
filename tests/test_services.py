import io

from litgraph.services import build_edges, valid_attachment
from litgraph.evidence import validate_evidence_value, validate_field


def paper(path: str, title: str, text: str):
    return {"path": path, "title": title, "text": text}


def test_numeric_citation_context_and_provenance():
    source = paper(
        "source.pdf",
        "A Source Paper",
        "Prior accelerators used analog arrays [4]. A different result appears [14].\n"
        "References\n[4] A. Author, Robust In Memory Acceleration for Neural Networks, 2024.\n"
        "[14] B. Author, Unrelated Work, 2023.",
    )
    target = paper("target.pdf", "Robust In-Memory Acceleration for Neural Networks", "")
    edges = build_edges([source, target])
    assert len(edges) == 1
    assert edges[0]["marker"] == "4"
    assert "analog arrays [4]" in edges[0]["contexts"]
    assert edges[0]["confidence"] >= 0.9


def test_title_mention_outside_references_does_not_create_edge():
    source = paper("source.pdf", "Source", "We discuss Robust In-Memory Acceleration for Neural Networks in prose.")
    target = paper("target.pdf", "Robust In-Memory Acceleration for Neural Networks", "")
    assert build_edges([source, target]) == []


def test_incremental_edge_build_only_returns_affected_pairs():
    first = paper("first.pdf", "First Source Paper", "References\n[1] A. Author, Target Architecture for Efficient Research, 2024.")
    second = paper("second.pdf", "Target Architecture for Efficient Research", "")
    third = paper("third.pdf", "An Unaffected Paper", "")
    edges = build_edges([first, second, third], {"second.pdf"})
    assert {(edge["source"], edge["target"]) for edge in edges} == {("first.pdf", "second.pdf")}


def test_attachment_signatures():
    assert valid_attachment(io.BytesIO(b"%PDF-1.7"), "pdf")
    assert valid_attachment(io.BytesIO(b"PK\x03\x04data"), "docx")
    assert valid_attachment(io.BytesIO(b"plain text"), "md")
    assert not valid_attachment(io.BytesIO(b"not a pdf"), "pdf")
    assert not valid_attachment(io.BytesIO(b"\x00binary"), "txt")


def test_evidence_field_and_typed_values():
    field = validate_field({"label": "Energy efficiency", "type": "number", "unit": "TOPS/W"})
    assert field["key"] == "energy_efficiency"
    assert validate_evidence_value("number", "12.4") == 12.4
    assert validate_evidence_value("range", {"min": "1", "max": "2", "uncertainty": "0.1"}) == {
        "min": 1.0, "max": 2.0, "uncertainty": "0.1"
    }
