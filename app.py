import html
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import cgi

from main import OUTPUT_DIR, SUPPORTED_EXTENSIONS, process_file

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def render_page(results=None, error=""):
    results = results or []
    accepted = ", ".join(sorted(SUPPORTED_EXTENSIONS))

    error_html = f'<div class="alert alert--error">{html.escape(error)}</div>' if error else ""

    rows = ""
    if results:
        for result in results:
            status = html.escape(result.get("status", "error"))
            name = html.escape(result.get("name", ""))
            message = html.escape(result.get("message", ""))
            download = result.get("download")
            download_html = (
                f'<a href="/download/{html.escape(download)}" class="btn btn--small">Download</a>' if download else "-"
            )
            rows += (
                "<tr>"
                f"<td>{name}</td>"
                f'<td><span class="badge badge--{status}">{status}</span></td>'
                f"<td>{message}</td>"
                f"<td>{download_html}</td>"
                "</tr>"
            )

    results_html = (
        "<section class=\"card\"><h2>Processing Results</h2><table><thead><tr>"
        "<th>File</th><th>Status</th><th>Message</th><th>Download</th>"
        "</tr></thead><tbody>"
        f"{rows}</tbody></table></section>"
        if results
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>XL Data Automation</title>
  <link rel=\"stylesheet\" href=\"/static/styles.css\" />
</head>
<body>
  <header class=\"hero\">
    <div class=\"hero__content\">
      <h1>XL Data Automation</h1>
      <p>
        Upload Excel, PDF, or image files to clean contact data, normalize phone numbers,
        enrich pincode with district/state, and convert Hindi text into English.
      </p>
      <a href=\"#uploader\" class=\"btn btn--secondary\">Start Processing</a>
    </div>
  </header>

  <main class=\"container\">
    <section id=\"uploader\" class=\"card\">
      <h2>Upload Your Files</h2>
      <p class=\"muted\">Accepted formats: {html.escape(accepted)}</p>
      {error_html}
      <form action=\"/process\" method=\"post\" enctype=\"multipart/form-data\" id=\"uploadForm\">
        <label class=\"file-drop\" for=\"filesInput\">
          <input id=\"filesInput\" name=\"files\" type=\"file\" multiple required />
          <span id=\"fileDropLabel\">Choose files or drag them here</span>
        </label>
        <button class=\"btn\" type=\"submit\">Process Files</button>
      </form>
      <ul id=\"selectedFiles\" class=\"selected-files\"></ul>
    </section>

    <section class=\"card grid\">
      <article>
        <h3>Data Cleaning</h3>
        <p>Removes duplicates, standardizes phone numbers, and drops city column noise.</p>
      </article>
      <article>
        <h3>Pincode Enrichment</h3>
        <p>Maps valid 6-digit pincodes to district and state using the local master dataset.</p>
      </article>
      <article>
        <h3>Hindi Conversion</h3>
        <p>Uses translation with transliteration fallback for reliable Hindi-to-English outputs.</p>
      </article>
    </section>

    {results_html}
  </main>

  <script src=\"/static/app.js\"></script>
</body>
</html>"""


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = unquote(self.path)
        if path == "/":
            self._send_html(render_page())
            return

        if path.startswith("/download/"):
            self._serve_download(path.replace("/download/", "", 1))
            return

        if path.startswith("/static/"):
            self._serve_static(path.replace("/static/", "", 1))
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if self.path != "/process":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        ctype, _ = cgi.parse_header(self.headers.get("content-type"))
        if ctype != "multipart/form-data":
            self._send_html(render_page(error="Invalid form submission."), status=HTTPStatus.BAD_REQUEST)
            return

        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        fields = form["files"] if "files" in form else []
        if not isinstance(fields, list):
            fields = [fields]

        if not fields or not fields[0].filename:
            self._send_html(render_page(error="Please select at least one file to upload."), status=HTTPStatus.BAD_REQUEST)
            return

        results = []
        for item in fields:
            original_name = item.filename or ""
            safe_name = os.path.basename(original_name)
            suffix = Path(safe_name).suffix.lower()

            if suffix not in SUPPORTED_EXTENSIONS:
                results.append({"name": original_name, "status": "error", "message": "Unsupported format"})
                continue

            upload_path = UPLOAD_DIR / safe_name
            with open(upload_path, "wb") as f:
                f.write(item.file.read())

            try:
                output_path = process_file(upload_path, output_dir=OUTPUT_DIR)
                results.append(
                    {
                        "name": original_name,
                        "status": "success",
                        "message": "Processed successfully",
                        "download": Path(output_path).name,
                    }
                )
            except Exception as exc:
                results.append({"name": original_name, "status": "error", "message": str(exc)})

        self._send_html(render_page(results=results))

    def _serve_download(self, filename):
        safe_name = os.path.basename(filename)
        file_path = Path(OUTPUT_DIR) / safe_name
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _serve_static(self, rel_path):
        safe_rel = rel_path.lstrip("/")
        file_path = STATIC_DIR / safe_rel
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content = file_path.read_bytes()
        mime, _ = mimetypes.guess_type(str(file_path))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_html(self, body, status=HTTPStatus.OK):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run(host="0.0.0.0", port=5000):
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Server running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
