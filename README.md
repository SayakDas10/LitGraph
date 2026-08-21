# LitGraph

LitGraph is a local research-paper library that turns a collection of text-layer PDFs into an interactive citation graph. It is intended for researchers who want to browse relationships between papers, inspect the evidence behind inferred citations, organize reading, and keep notes beside the source material.

The Flask server binds to `127.0.0.1`, PDFs and notes remain on the local filesystem, and structured state is stored in a local SQLite database. Online metadata lookup is disabled by default.

## Features

### Paper library

- Import one PDF by absolute path, either by copying it or moving it into LitGraph.
- Import a directory recursively while preserving its folder structure.
- Reject invalid PDF signatures, unsafe destination paths, recursive imports, and duplicate filenames.
- Browse the complete library or filter the graph by project folder.
- Open a paper in a separate browser tab.
- Rename an extracted title; manual titles persist across later PDF updates.
- Mark papers as **Read** or **Prioritize**.
- Delete a paper together with its text note and attachments.

### Citation graph

- Extract text and local title candidates with PyMuPDF.
- Detect a paper's References, Bibliography, or Works Cited section.
- Match normalized title tokens so punctuation and common hyphenation differences do not prevent a match.
- Resolve numbered and basic author-year markers.
- Store the matched bibliography entry, in-text contexts, extraction method, and confidence score for every edge.
- Show citation direction, evidence, method, and confidence when an edge is selected.
- Search papers by title or path and highlight graph neighborhoods interactively.
- Search full paper text, notes, citation evidence, and structured evidence through SQLite FTS5.
- Explore the complete project or restrict the view to one-hop/two-hop neighborhoods and reading-status filters.
- Switch between cluster, citation-flow, grid, and circle layouts.
- Preserve node positions, pinned nodes, zoom, and graph context while project data changes.
- Use semantic zoom: distant views reduce papers to compact marks, normal views show short titles, and close views show full titles.
- Compare selected papers using their populated evidence fields.
- Export a high-resolution PNG of the current graph.

Citation edges are inferred evidence, not ground truth. See [Citation-extraction limitations](#citation-extraction-limitations).

### Notes and attachments

- Save a UTF-8 text note for each paper.
- Attach `.ppt`, `.pptx`, `.docx`, `.txt`, `.pdf`, and `.md` files.
- Validate attachment extensions, common container signatures, and a configurable upload-size limit.
- Download saved attachments from the paper detail panel.

### Evidence Templates

- Characterize papers with structured, typed evidence without tying LitGraph to one discipline.
- Start with the globally enabled **Generic Research** template covering questions, methods, datasets, metrics, findings, limitations, validity, future work, and artifacts.
- Compose optional built-in templates for **Machine Learning**, **Hardware Accelerators**, and **Clinical Studies**.
- Enable templates for an entire project folder or override them for an individual paper.
- Create, edit, and delete custom templates through the UI.
- Define text, numeric, Boolean, date, choice, citation, URL, range, and table fields with units and selectable options.
- Store every value with its source excerpt, page, table/figure location, extraction method, confidence, and verification state.
- Distinguish manual, imported, and automatically suggested evidence, as well as confirmed, suggested, and rejected values.

Hardware-specific fields are never part of the universal paper model. They appear only when the optional Hardware Accelerators template is enabled. The same extension mechanism supports any academic discipline or interdisciplinary combination.

### Local state and privacy

- SQLite transactions replace the previous shared JSON cache and prevent lost read-modify-write updates.
- Unchanged PDFs reuse cached extracted text; only new or modified PDFs are parsed again.
- Citation edges are updated incrementally: a paper change recomputes only relationships where that paper is a source or target.
- Library synchronization runs in a cancellable background job with per-paper progress and error reporting.
- Legacy `.litgraph.json` paper metadata is migrated automatically on the first database initialization. Existing titles are conservatively retained as manual overrides.
- All mutation endpoints require a session-bound request token.
- Paper paths, folder names, titles, and attachment names are transported as raw JSON and rendered with safe DOM operations.
- Debug mode is disabled, security headers are enabled, and the server listens only on localhost.

## Requirements

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- A modern browser
- Internet access for the current Cytoscape, Font Awesome, and Google Fonts web assets

PDF ingestion and citation extraction work without an external API. The current browser UI still loads the three assets above from pinned CDN URLs, so completely disconnected use requires vendoring those assets locally.

## Installation

```bash
git clone https://github.com/SayakDas10/LitGraph.git
cd LitGraph
uv sync
```

Run LitGraph with:

```bash
uv run python app.py
```

The application opens `http://127.0.0.1:5001` in the default browser. If a browser does not open automatically, visit that address manually.

## First use

1. Select **Single** to copy or move one PDF into the library, or select **Import Library** to ingest a directory tree.
2. Wait for synchronization. New or changed PDFs are parsed and the citation graph is rebuilt.
3. Select a project folder to filter the visible graph.
4. Click a node to open the PDF, correct its title, set reading status, write notes, attach files, or delete it.
5. Add or remove Evidence Templates for the paper, then record structured values and their provenance.
6. Use **Project Evidence Templates** to apply a template to every paper under the selected folder.
7. Click an edge to inspect its bibliography match, in-text evidence, method, and confidence.
8. Use either search bar to center the first matching paper.

The graph toolbar provides fit/zoom controls, four layouts, reading-status and neighborhood filters, label/edge visibility, focus mode, view reset, and image export. Right-click or long-press a paper for neighborhood, pin, comparison, priority, and hide actions. Focus the graph and use Left/Right followed by Enter for keyboard paper navigation.

Files can also be placed directly under `papers/`. Preserve any desired project structure with subdirectories. LitGraph detects additions, modifications, and removals when the page loads or the library is refreshed through the UI.

## Optional DOI metadata lookup

Online lookup is disabled by default. Enable it for a run with:

```bash
LITGRAPH_ONLINE_METADATA=1 uv run python app.py
```

When enabled, LitGraph extracts a DOI locally and sends only that DOI to the Semantic Scholar Graph API to request a title. It does **not** send first-page text or complete PDF content. If no DOI is found, the request fails, or the returned title is implausible, LitGraph keeps the locally extracted title.

Semantic Scholar availability and rate limits are outside LitGraph's control. Corrected titles can always be entered manually.

## Configuration

| Environment variable | Default | Purpose |
|---|---:|---|
| `LITGRAPH_ONLINE_METADATA` | `0` | Enable DOI-only Semantic Scholar title lookup |
| `LITGRAPH_MAX_ATTACHMENT_MB` | `50` | Maximum size of one uploaded attachment |
| `LITGRAPH_SECRET_KEY` | Random per launch | Stable Flask session secret, useful if persistent browser sessions are required |

Do not bind the application to `0.0.0.0` without adding authentication, TLS, and a deliberate network-access policy. The import API can read from local paths available to the LitGraph process, so this application must be treated as a local desktop service.

## Local data layout

```text
LitGraph/
├── papers/              # PDFs and project folders
├── notes/               # Per-paper text notes and attachments
├── .litgraph.db         # SQLite paper, text-cache, and edge state
├── app.py               # Flask routes and application entry point
├── litgraph/
│   ├── config.py        # Paths, limits, and safe path resolution
│   ├── evidence.py      # Built-in templates and evidence validation
│   ├── services.py      # PDF, metadata, and citation processing
│   └── storage.py       # SQLite repository
├── static/              # Browser logic and styles
├── templates/           # HTML application shell
└── tests/               # Security, extraction, and persistence tests
```

`papers/`, `notes/`, the SQLite database, and the legacy JSON cache are ignored by Git. Back up the first three if the library is important. SQLite may temporarily create `-wal` and `-shm` companion files while LitGraph is running; stop the application before copying the database for a simple consistent backup.

## Citation-extraction limitations

The current extractor is intentionally conservative:

- The PDF must contain a readable text layer; scanned PDFs require OCR before import.
- A recognizable References, Bibliography, or Works Cited heading is required.
- Matching uses normalized title tokens, so titles with severe OCR errors or substantially different published/preprint names can be missed.
- Numbered references and simple author-year references are supported. Superscript markers and unusual publisher-specific formats may not be resolved.
- Confidence indicates the available extraction evidence; it is not a calibrated probability that the citation is correct.
- Extraction currently rebuilds the edge set from cached texts after a library or title change. This avoids reparsing unchanged PDFs, but pairwise title matching still scales approximately quadratically with library size.

For bibliometric or publication-quality analysis, validate inferred edges manually. A future production-grade pipeline could integrate GROBID and DOI/arXiv resolution, but those external services and models are not bundled with this local release.

## Development and tests

Install the development dependency group and run the test suite:

```bash
uv sync --extra dev
uv run pytest
```

The tests cover canonical path containment, symlink escape prevention, recursive import detection, file signatures, numeric and incremental citation evidence, manual-title persistence, status persistence, full-text indexing, incremental edge replacement, template composition, typed evidence, provenance persistence, and cascading deletion.

Useful next development targets are calibrated edge evaluation on a labeled PDF corpus, local vendoring of browser assets, attachment deletion, automatic evidence suggestions, and server-side community aggregation for extremely large libraries.

## Security notes

- PDF and Office files are untrusted inputs. Signature checks reject obvious extension spoofing but are not malware scanning or sandboxing.
- Attachments are served as downloads with MIME sniffing disabled.
- The app uses a strict descendant-path policy for managed destinations and verifies UUID ownership before accessing notes.
- Copy is safer than move because moving removes the original after a successful filesystem operation.
- Deleting a paper is intentionally destructive and cannot be undone from LitGraph.

Please report security issues privately before publishing exploit details.

## License

LitGraph is released under the [MIT License](LICENSE).
