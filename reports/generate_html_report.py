
# Path builds file locations without hardcoding Windows paths.
from pathlib import Path

# json reads the execution results written by runner.py.
import json

# html.escape prevents error text from breaking the HTML page.
import html

# datetime stamps when this HTML report was generated.
from datetime import datetime

# argparse lets the script be run from the command line.
import argparse

# sys exits with a clear error when the JSON report is missing.
import sys


# Directory containing this file (the reports folder).
REPORTS_DIR = Path(__file__).resolve().parent

# Default JSON produced by runner.py.
DEFAULT_JSON_REPORT = REPORTS_DIR / "execution_report.json"

# Default HTML output path.
DEFAULT_HTML_REPORT = REPORTS_DIR / "execution_report.html"


def load_execution_results(json_path):
    """Read execution_report.json and return a list of result dictionaries."""

    # Stop with a helpful message if the runner has not been executed yet.
    if not json_path.exists():
        raise FileNotFoundError(
            f"Execution report not found: {json_path}\n"
            "Run runner.py first so execution_report.json is created."
        )

    # Open and parse the JSON file.
    with open(json_path, "r", encoding="utf-8") as report_file:
        data = json.load(report_file)

    # runner.py writes a list of results.
    # Accept a wrapped object as well, in case the format changes later.
    if isinstance(data, dict) and "results" in data:
        return data["results"]

    if isinstance(data, list):
        return data

    raise ValueError(
        "Unexpected execution report format. "
        "Expected a list of test results."
    )


def build_summary(results):
    """Calculate totals used in the report header."""

    total = len(results)
    passed = sum(1 for result in results if result.get("status") == "PASS")
    failed = sum(1 for result in results if result.get("status") == "FAIL")
    skipped = sum(1 for result in results if result.get("status") == "SKIP")
    other = total - passed - failed - skipped

    # Sum durations when present; missing values are treated as zero.
    total_duration = round(
        sum(float(result.get("duration_seconds") or 0) for result in results),
        2
    )

    pass_rate = round((passed / total) * 100, 1) if total else 0.0

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "other": other,
        "total_duration": total_duration,
        "pass_rate": pass_rate
    }


def status_class(status):
    """Map a test status to a CSS class name."""

    normalized = (status or "UNKNOWN").upper()

    if normalized == "PASS":
        return "pass"
    if normalized == "FAIL":
        return "fail"
    if normalized == "SKIP":
        return "skip"

    return "unknown"


def render_rows(results):
    """Build one HTML table row for each executed test case."""

    rows = []

    for result in results:
        test_id = html.escape(str(result.get("test_id", "")))
        title = html.escape(str(result.get("title", "")))
        status = str(result.get("status", "UNKNOWN")).upper()
        executed_at = html.escape(str(result.get("executed_at", "")))
        duration = result.get("duration_seconds", "")
        error = result.get("error")

        css = status_class(status)

        # Show the captured exception for failures; keep the cell empty on pass.
        if error:
            error_html = (
                f'<pre class="error">{html.escape(str(error))}</pre>'
            )
        else:
            error_html = '<span class="muted">—</span>'

        rows.append(
            f"""
            <tr class="row {css}" data-status="{html.escape(status)}">
                <td><code>{test_id}</code></td>
                <td>{title}</td>
                <td><span class="badge {css}">{html.escape(status)}</span></td>
                <td>{executed_at}</td>
                <td class="numeric">{duration}</td>
                <td>{error_html}</td>
            </tr>
            """
        )

    return "\n".join(rows)


def render_html(results, json_path):
    """Assemble a self-contained HTML report from execution results."""

    summary = build_summary(results)
    generated_at = datetime.now().isoformat(timespec="seconds")
    source_file = html.escape(str(json_path.name))

    # Overall banner color follows the run outcome.
    if summary["failed"] > 0:
        overall = "fail"
        overall_label = "Failed"
    elif summary["total"] == 0:
        overall = "unknown"
        overall_label = "No results"
    else:
        overall = "pass"
        overall_label = "Passed"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI QA Agent — Execution Report</title>
    <style>
        :root {{
            --bg: #0f1419;
            --panel: #1a2332;
            --line: #2b3a4f;
            --text: #e8eef6;
            --muted: #93a4b8;
            --pass: #3dd68c;
            --fail: #ff6b6b;
            --skip: #f5c542;
            --unknown: #8b9cb3;
            --accent: #5b9dff;
        }}

        * {{ box-sizing: border-box; }}

        body {{
            margin: 0;
            font-family: Segoe UI, Tahoma, sans-serif;
            background: radial-gradient(circle at top, #1c2940 0%, var(--bg) 45%);
            color: var(--text);
            min-height: 100vh;
        }}

        .wrap {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 32px 20px 48px;
        }}

        h1 {{
            margin: 0 0 8px;
            font-size: 28px;
        }}

        .subtitle {{
            color: var(--muted);
            margin: 0 0 24px;
            font-size: 14px;
        }}

        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
        }}

        .card {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 16px;
        }}

        .card .label {{
            color: var(--muted);
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        .card .value {{
            font-size: 28px;
            font-weight: 700;
            margin-top: 6px;
        }}

        .value.pass {{ color: var(--pass); }}
        .value.fail {{ color: var(--fail); }}
        .value.skip {{ color: var(--skip); }}

        .banner {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            background: var(--panel);
            border: 1px solid var(--line);
            border-left: 6px solid var(--unknown);
            border-radius: 12px;
            padding: 16px 18px;
            margin-bottom: 20px;
        }}

        .banner.pass {{ border-left-color: var(--pass); }}
        .banner.fail {{ border-left-color: var(--fail); }}
        .banner.unknown {{ border-left-color: var(--unknown); }}

        .bar {{
            height: 10px;
            background: #243044;
            border-radius: 999px;
            overflow: hidden;
            margin-top: 10px;
        }}

        .bar span {{
            display: block;
            height: 100%;
            background: linear-gradient(90deg, var(--pass), var(--accent));
        }}

        .filters {{
            display: flex;
            gap: 8px;
            margin: 0 0 14px;
            flex-wrap: wrap;
        }}

        button {{
            background: #223044;
            color: var(--text);
            border: 1px solid var(--line);
            border-radius: 999px;
            padding: 8px 14px;
            cursor: pointer;
        }}

        button.active {{
            background: var(--accent);
            color: #071018;
            border-color: var(--accent);
            font-weight: 600;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            overflow: hidden;
        }}

        th, td {{
            text-align: left;
            padding: 12px 14px;
            vertical-align: top;
            border-bottom: 1px solid var(--line);
        }}

        th {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: var(--muted);
            background: #162033;
        }}

        tr:last-child td {{ border-bottom: none; }}

        .numeric {{ text-align: right; }}

        code {{
            background: #0f1a28;
            padding: 2px 6px;
            border-radius: 6px;
            font-size: 13px;
        }}

        .badge {{
            display: inline-block;
            min-width: 64px;
            text-align: center;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 700;
        }}

        .badge.pass {{ background: rgba(61, 214, 140, 0.18); color: var(--pass); }}
        .badge.fail {{ background: rgba(255, 107, 107, 0.18); color: var(--fail); }}
        .badge.skip {{ background: rgba(245, 197, 66, 0.18); color: var(--skip); }}
        .badge.unknown {{ background: rgba(139, 156, 179, 0.18); color: var(--unknown); }}

        .error {{
            margin: 0;
            white-space: pre-wrap;
            color: #ffd1d1;
            font-size: 12px;
            background: #2a1518;
            padding: 8px 10px;
            border-radius: 8px;
        }}

        .muted {{ color: var(--muted); }}

        .empty {{
            text-align: center;
            padding: 28px;
            color: var(--muted);
        }}
    </style>
</head>
<body>
    <div class="wrap">
        <h1>AI QA Agent — Execution Report</h1>
        <p class="subtitle">
            Source: {source_file} · Generated: {html.escape(generated_at)}
        </p>

        <div class="banner {overall}">
            <div>
                <div class="label muted">Overall result</div>
                <strong>{overall_label}</strong>
            </div>
            <div>
                Pass rate: <strong>{summary["pass_rate"]}%</strong>
                <div class="bar">
                    <span style="width: {summary["pass_rate"]}%;"></span>
                </div>
            </div>
        </div>

        <div class="cards">
            <div class="card">
                <div class="label">Total</div>
                <div class="value">{summary["total"]}</div>
            </div>
            <div class="card">
                <div class="label">Passed</div>
                <div class="value pass">{summary["passed"]}</div>
            </div>
            <div class="card">
                <div class="label">Failed</div>
                <div class="value fail">{summary["failed"]}</div>
            </div>
            <div class="card">
                <div class="label">Duration (s)</div>
                <div class="value">{summary["total_duration"]}</div>
            </div>
        </div>

        <div class="filters">
            <button class="active" data-filter="ALL">All</button>
            <button data-filter="PASS">Pass</button>
            <button data-filter="FAIL">Fail</button>
        </div>

        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Executed at</th>
                    <th>Duration (s)</th>
                    <th>Error</th>
                </tr>
            </thead>
            <tbody>
                {render_rows(results) if results else '<tr><td class="empty" colspan="6">No test results found.</td></tr>'}
            </tbody>
        </table>
    </div>

    <script>
        const buttons = document.querySelectorAll("button[data-filter]");
        const rows = document.querySelectorAll("tr.row");

        buttons.forEach((button) => {{
            button.addEventListener("click", () => {{
                buttons.forEach((item) => item.classList.remove("active"));
                button.classList.add("active");

                const filter = button.dataset.filter;
                rows.forEach((row) => {{
                    const match = filter === "ALL" || row.dataset.status === filter;
                    row.style.display = match ? "" : "none";
                }});
            }});
        }});
    </script>
</body>
</html>
"""


def generate_html_report(json_path=None, html_path=None):
    """Load execution JSON and write a standalone HTML report."""

    json_report = Path(json_path) if json_path else DEFAULT_JSON_REPORT
    html_report = Path(html_path) if html_path else DEFAULT_HTML_REPORT

    results = load_execution_results(json_report)
    html_content = render_html(results, json_report)

    # Create the reports folder if a custom output path is used.
    html_report.parent.mkdir(parents=True, exist_ok=True)

    with open(html_report, "w", encoding="utf-8") as output_file:
        output_file.write(html_content)

    return html_report


def parse_args():
    """Read optional input and output paths from the command line."""

    parser = argparse.ArgumentParser(
        description="Generate an HTML report from execution_report.json"
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_JSON_REPORT),
        help="Path to execution_report.json"
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_HTML_REPORT),
        help="Path to write execution_report.html"
    )
    return parser.parse_args()


# Run as a script: python reports/generate_html_report.py
if __name__ == "__main__":
    args = parse_args()

    try:
        output_path = generate_html_report(args.input, args.output)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as error:
        print(error)
        sys.exit(1)

    print(f"HTML report saved to: {output_path}")
