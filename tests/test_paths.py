from pathlib import Path

import pytest

from litgraph.config import paths_overlap, resolved_child


def test_resolved_child_accepts_nested_path(tmp_path: Path):
    assert resolved_child(tmp_path, "project/paper.pdf") == (tmp_path / "project/paper.pdf").resolve()


@pytest.mark.parametrize("path", ["../outside", "folder/../../outside", "/tmp/outside"])
def test_resolved_child_rejects_escape(tmp_path: Path, path: str):
    with pytest.raises(ValueError):
        resolved_child(tmp_path, path)


def test_resolved_child_rejects_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        resolved_child(tmp_path, "link/paper.pdf")


def test_paths_overlap_in_both_directions(tmp_path: Path):
    library = tmp_path / "library"
    papers = library / "LitGraph" / "papers"
    papers.mkdir(parents=True)
    assert paths_overlap(library, papers)
    assert paths_overlap(papers, library)
    assert not paths_overlap(tmp_path / "unrelated", papers)

