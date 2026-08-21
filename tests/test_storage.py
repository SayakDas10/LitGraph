from pathlib import Path

from litgraph.storage import Repository


def record(path: str = "paper.pdf"):
    return {
        "path": path,
        "uuid": "a" * 32,
        "mtime": 1.0,
        "size": 100,
        "title": "Extracted title",
        "manual_title": 0,
        "status": "none",
        "text": "Paper text",
        "metadata_source": "local",
    }


def test_manual_title_and_status_survive_pdf_refresh(tmp_path: Path):
    repository = Repository(tmp_path / "litgraph.db")
    repository.initialize()
    repository.upsert_paper(record())
    assert repository.set_title("paper.pdf", "My corrected title")
    assert repository.set_status("paper.pdf", "prioritize")
    refreshed = record()
    refreshed.update({"mtime": 2.0, "size": 200, "title": "New extracted title", "text": "Updated text"})
    repository.upsert_paper(refreshed)
    stored = repository.paper_map()["paper.pdf"]
    assert stored["title"] == "My corrected title"
    assert stored["status"] == "prioritize"
    assert stored["text"] == "Updated text"


def test_deleting_paper_cascades_edges(tmp_path: Path):
    repository = Repository(tmp_path / "litgraph.db")
    repository.initialize()
    first = record("first.pdf")
    second = {**record("second.pdf"), "uuid": "b" * 32}
    repository.upsert_paper(first)
    repository.upsert_paper(second)
    repository.replace_edges([{
        "source": "first.pdf", "target": "second.pdf", "marker": "1", "contexts": "[]",
        "bibliography": "entry", "confidence": 0.9, "method": "test",
    }])
    repository.delete_paper("second.pdf")
    assert repository.edges() == []


def test_generic_evidence_is_default_and_templates_compose(tmp_path: Path):
    repository = Repository(tmp_path / "litgraph.db")
    repository.initialize()
    repository.upsert_paper(record("project/paper.pdf"))
    initial = repository.evidence_for_paper("a" * 32)
    assert initial is not None
    assert initial["active_schema_ids"] == ["generic_research"]
    repository.set_folder_schema("project", "machine_learning", True)
    repository.set_paper_schema("a" * 32, "hardware_accelerators", True)
    composed = repository.evidence_for_paper("a" * 32)
    assert set(composed["active_schema_ids"]) == {
        "generic_research", "machine_learning", "hardware_accelerators"
    }
    repository.set_paper_schema("a" * 32, "machine_learning", False)
    assert "machine_learning" not in repository.evidence_for_paper("a" * 32)["active_schema_ids"]


def test_custom_schema_and_evidence_provenance(tmp_path: Path):
    repository = Repository(tmp_path / "litgraph.db")
    repository.initialize()
    repository.upsert_paper(record())
    schema_id = repository.save_custom_schema("My Template", "Description", [{
        "id": "", "key": "reported_value", "label": "Reported value", "type": "number",
        "unit": "J", "options": [], "group_name": "Results",
    }])
    repository.set_paper_schema("a" * 32, schema_id, True)
    schema = repository.schema(schema_id)
    field_id = schema["fields"][0]["id"]
    repository.save_evidence_value("a" * 32, field_id, 3.2, {
        "source_excerpt": "The measured energy was 3.2 J.", "page": "7", "location": "Table II",
        "extraction_method": "manual", "confidence": 1.0, "verification_status": "confirmed",
    })
    evidence = repository.evidence_for_paper("a" * 32)
    assert evidence["values"][field_id]["value"] == 3.2
    assert evidence["values"][field_id]["location"] == "Table II"
    assert repository.delete_custom_schema(schema_id)
    assert field_id not in repository.evidence_for_paper("a" * 32)["values"]


def test_full_text_search_indexes_papers_notes_and_evidence(tmp_path: Path):
    repository = Repository(tmp_path / "litgraph.db")
    repository.initialize()
    item = record()
    item["text"] = "Memristive crossbars experience conductance variation."
    repository.upsert_paper(item)
    assert repository.search("conductance variation")[0]["path"] == "paper.pdf"
    repository.refresh_search_entry("a" * 32, "Calibration suppresses correlated noise.")
    assert repository.search("correlated noise")[0]["uuid"] == "a" * 32


def test_incremental_edge_replacement_preserves_unaffected_edges(tmp_path: Path):
    repository = Repository(tmp_path / "litgraph.db")
    repository.initialize()
    records = []
    for index, path in enumerate(["a.pdf", "b.pdf", "c.pdf"]):
        item = record(path)
        item["uuid"] = f"{index + 1:032x}"
        repository.upsert_paper(item)
        records.append(item)
    base = {
        "marker": "1", "contexts": "[]", "bibliography": "entry",
        "confidence": 0.9, "method": "test",
    }
    repository.replace_edges([
        {**base, "source": "a.pdf", "target": "b.pdf"},
        {**base, "source": "b.pdf", "target": "c.pdf"},
    ])
    repository.replace_edges_for_paths({"a.pdf"}, [
        {**base, "source": "a.pdf", "target": "c.pdf"},
    ])
    pairs = {(edge["source"], edge["target"]) for edge in repository.edges()}
    assert pairs == {("a.pdf", "c.pdf"), ("b.pdf", "c.pdf")}
