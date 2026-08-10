# LitGraph 🕸️📚

LitGraph is a privacy-first, local web application designed for researchers and academics. It automatically visualizes your collection of scientific PDFs as an interactive network graph, allowing you to seamlessly explore citation relationships and read the exact contextual sentences where one paper cites another.

Everything runs locally on your machine—no cloud subscriptions, no data harvesting, and no mandatory internet connection for core features.

## ✨ Core Functionalities

* **Interactive Citation Network:** Visualizes papers as floating nodes. Edges represent citations, generated automatically by scanning the text of your PDFs.
* **Contextual Citation Extraction:** Clicking an edge opens a sliding glass panel that displays the exact sentences where the source paper mentions the target paper.
* **Smart Metadata Heuristics:** Automatically extracts titles from PDF metadata. If metadata is missing or corrupted (e.g., a file named verbatim `3476999.pdf`), the engine intelligently falls back to extracting the first substantial text block from the document's first page to generate the title.


* **Integrated Paper Downloader:** Paste a direct PDF link, arXiv URL, or plain text citation. LitGraph connects to Semantic Scholar and arXiv APIs to find Open Access PDFs, download them directly to your local folder, and immediately update the graph.
* **Modern Glassmorphic UI:** Features a sleek, distraction-free interface with a built-in search autocomplete system, interactive hover highlighting, and full Light/Dark mode support.
* **Privacy-First & Local:** Your library never leaves your hard drive.

---

## 🚀 Setup & Installation

This project relies on [uv](https://github.com/astral-sh/uv), an extremely fast Python package installer and resolver.

### Prerequisites

* Python 3.8+ installed on your system.
* `uv` installed (install via `curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh` on macOS/Linux or `powershell -c "irm [https://astral.sh/uv/install.ps1](https://astral.sh/uv/install.ps1) | iex"` on Windows).

### Step-by-Step Guide

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/LitGraph.git
cd LitGraph

```


2. **Create a virtual environment using `uv**`
```bash
uv venv

```


3. **Activate the virtual environment**
* On macOS and Linux:
```bash
source .venv/bin/activate

```


* On Windows:
```bash
.venv\Scripts\activate

```




4. **Install dependencies**
```bash
uv pip install Flask PyMuPDF requests

```


5. **Run the application**
```bash
python app.py

```


*LitGraph will automatically create a `papers/` folder in your directory and pop open your default web browser.*

---

## 📖 How to Use

1. **Populating your Library:** Drag and drop any scientific PDF into the newly created `papers/` folder. Refresh the browser page to see the updated graph.
2. **Reading Papers:** Click on any node (pill) in the graph to instantly open that PDF in a new browser tab.
3. **Exploring Citations:** Hover over a node to highlight its immediate neighborhood. Click on a connecting edge to open the right-side panel, which will reveal the exact in-text citation context.
4. **Finding New Papers:** Paste a citation or title into the left sidebar's "Download & Add" input. LitGraph will query academic databases and present a download menu.

---

## ⚠️ Limitations & Known Behaviors

* **Heuristic Extraction Limits:** The citation extraction relies on RegEx heuristics to match reference lists and in-text markers (e.g., `[10]`, `(Smith, 2024)`). While highly effective for standard academic formats (IEEE, ACM, APA), highly unconventional formatting or heavily customized LaTeX styles might occasionally be missed.
* **Publisher Firewalls (403 Errors):** LitGraph cannot bypass strict publisher firewalls (e.g., specific ACM or IEEE locked portals). If you attempt to download a paywalled URL via the app, you will receive a `403 Forbidden` error. You must download these manually via your browser (using institutional access) and drop them into the `papers/` folder.
* **Requires Text-Layer PDFs:** The application cannot read scanned images of papers. The PDFs must contain a readable text layer (OCR).
* **Performance on Massive Libraries:** LitGraph reads and builds the graph dynamically on load. While highly optimized, dropping hundreds of massive PDFs into the folder at once may cause slightly longer initial load times.

---

## 🛡️ Security Notice

**LitGraph is designed strictly as a local desktop tool.**

By default, the Flask server binds to `127.0.0.1` (localhost), meaning it is only accessible from your own machine. **Do not modify the host configuration to `0.0.0.0**` unless you are on a highly secure, private home network. Doing so on a public Wi-Fi network (like a university or coffee shop) will expose your personal computer's `papers/` folder and LitGraph's download endpoints to anyone on that same network.

The backend includes active mitigations against Cross-Site Scripting (XSS) and Magic Byte validation to ensure downloaded files are genuine PDFs, but maintaining local network hygiene is your responsibility.

---

## Change Log
- Aug 10, 26: Fixed paper naming issue. Verify name with semantic scholar. Give user the option to change paper name. 
- Aug 8, 26: Added folder support. Read, prioritize options to paper. Implemented local cache for faster initial load.

## 🤝 Contributing

Contributions, issues, and feature requests are highly welcome! Feel free to check the [issues page](https://www.google.com/search?q=https://github.com/yourusername/LitGraph/issues) if you want to contribute to the heuristic extraction engine or UI enhancements.

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.
