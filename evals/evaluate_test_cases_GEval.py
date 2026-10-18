"""AI QA Test Case Evaluator - documented learning version.

Inputs (read only):
  NewRequirment/saucedemo_requirements.md
  reports/generated_test_cases.json

Outputs:
  reports/llm_evaluation_report.html
  evals/requirement_mapping_cache.json

The script does not change UI tests, Page Objects, runner.py, execution reports,
Allure files, or generated_test_cases.json.

TIMEOUT NOTE:
  DeepEval's own timeout machinery is disabled below. No custom request timeout
  is set by this script, and temporary service failures are retried indefinitely.
  A Python script cannot guarantee the absence of every timeout: SDK defaults,
  proxies, operating systems, network equipment, or the remote provider may still
  terminate a request. A 503 is a server availability error, not a timeout.
"""

# Set before importing DeepEval because its configuration is read at import time.
import os
# The os module provides access to environment variables and operating-system features.
os.environ["DEEPEVAL_DISABLE_TIMEOUTS"] = "1"

# Import standard Python libraries used for hashing, HTML generation, JSON,
# random retry delays, regular expressions, and measuring elapsed time.
import hashlib  # Creates fingerprints of input files to detect changes.
import html  # Escapes special characters before displaying values in HTML.
import json  # Reads and writes JSON data.
import random  # Adds randomness to retry delays to reduce simultaneous retries.
import re  # Finds requirement headings and cleans model responses.
import time  # Measures execution duration and waits between retries.
from collections import Counter  # Counts duplicate test IDs and titles.
from datetime import datetime  # Creates readable timestamps.
from pathlib import Path  # Builds platform-independent filesystem paths.

# Load environment variables from .env without hardcoding API keys in source code.
from dotenv import load_dotenv

# Gemini SDK: sends the requirement-mapping request to the selected Gemini model.
from google import genai

# DeepEval components used to assess semantic alignment between test cases and requirements.
from deepeval.metrics import GEval
from deepeval.models import GeminiModel
from deepeval.test_case import LLMTestCase, SingleTurnParams
from deepeval.metrics import GEval, FaithfulnessMetric

# Load API keys from the project's .env file without printing secrets.
load_dotenv()

# Resolve the project root relative to this script, rather than relying on the
# terminal's current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Define input and output locations centrally so they can be updated in one place.
REQUIREMENTS_FILE = PROJECT_ROOT / "NewRequirment" / "saucedemo_requirements.md"
TEST_CASES_FILE = PROJECT_ROOT / "reports" / "generated_test_cases.json"
HTML_REPORT_FILE = PROJECT_ROOT / "reports" / "llm_evaluation_report.html"
CACHE_FILE = PROJECT_ROOT / "evals" / "requirement_mapping_cache.json"

# Read the model name from an environment variable, using a default if it is absent.
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3.8-flash")

# G-Eval scores are compared with this threshold to determine PASS or FAIL.
PASS_THRESHOLD = 0.70


def log(message):
    """Print timestamped progress and flush it immediately to the terminal."""
    # datetime.now() supplies the current local time.
    # flush=True makes progress visible immediately rather than waiting for output buffering.
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def elapsed(start):
    """Return seconds elapsed using a monotonic clock (not affected by clock changes)."""
    # perf_counter() is useful for duration measurement because it is monotonic.
    # Subtracting the start value gives elapsed seconds; round() limits decimal places.
    return round(time.perf_counter() - start, 2)


def safe_html(value):
    """Escape untrusted strings before placing them into HTML report markup."""
    # Convert the value to text and replace HTML-sensitive characters.
    # This helps prevent test data or model output from being interpreted as HTML markup.
    return html.escape(str(value if value is not None else ""))


def display_number(value):
    """Show N/A for unknown usage instead of misleadingly treating it as zero."""
    # Format numbers with thousands separators.
    # If usage was not reported by the SDK, show N/A rather than claiming it was zero.
    return f"{value:,}" if isinstance(value, (int, float)) else "N/A"


def format_score(value):
    """Format a numeric evaluation score, or show N/A if no score was returned."""
    # Display scores to two decimal places for consistent reporting.
    return f"{value:.2f}" if isinstance(value, (int, float)) else "N/A"


def read_json(path):
    """Read JSON from disk and convert it into Python dictionaries/lists."""
    # The with statement closes the file automatically after reading.
    # json.load() converts JSON text into Python objects such as dictionaries and lists.
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, value):
    """Write JSON, creating its parent folder if necessary."""
    # Create missing parent directories without raising an error if they already exist.
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write readable JSON. ensure_ascii=False preserves non-English characters.
    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, indent=2, ensure_ascii=False)


def parse_json_response(text):
    """Parse model output as JSON, tolerating optional Markdown code fences."""
    # An empty response cannot be parsed into a valid mapping.
    if not text:
        raise ValueError("The model returned an empty response.")

    # Remove leading/trailing whitespace.
    text = text.strip()

    # Some models wrap JSON in Markdown code fences; remove those if present.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Convert the cleaned JSON string into Python dictionaries/lists.
    # Invalid JSON raises an exception for the caller to handle.
    return json.loads(text)


def call_with_retry(operation_name, operation):
    """Retry recognized transient API failures without a time/attempt cutoff.

    This deliberately has no five-minute or maximum-attempt limit. Wait time
    grows exponentially up to 60 seconds, plus small random jitter. Permanent
    errors (for example, invalid credentials) are raised instead of looping.
    """
    # attempt counts how many times this particular operation has been attempted.
    attempt = 0

    # Initial retry delay in seconds.
    delay = 5

    # Text markers used to recognize errors that may be temporary.
    # The check is based on the exception message, not a structured HTTP status field.
    transient_markers = (
        "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "500", "502",
        "504", "INTERNAL SERVER ERROR", "SERVICE UNAVAILABLE", "TIMED OUT",
        "TIMEOUT", "CONNECTION RESET", "CONNECTION ERROR", "TEMPORARILY",
    )

    # Keep attempting until the operation succeeds or a non-transient error occurs.
    while True:
        attempt += 1
        try:
            log(f"{operation_name}: attempt {attempt}")

            # operation is a callable: a function supplied to this retry helper.
            # Return its result immediately when it succeeds.
            return operation()

        except Exception as error:
            # Convert the exception text to uppercase so matching is case-insensitive.
            message = str(error).upper()

            # If no known transient marker appears, re-raise the original exception.
            # This prevents endless retries for errors classified as permanent.
            if not any(marker in message for marker in transient_markers):
                raise

            # Add 0–2 seconds of random jitter to avoid all clients retrying together.
            # The overall delay is capped at 60 seconds.
            wait_seconds = min(delay + random.uniform(0, 2), 60)

            # Log the exception and next retry delay for troubleshooting.
            log(f"{operation_name}: temporary error ({type(error).__name__}: {error})")
            log(f"Waiting {wait_seconds:.1f} seconds, then retrying. Press Ctrl+C to stop manually.")

            # Pause before the next attempt. This is a retry delay, not a request timeout.
            time.sleep(wait_seconds)

            # Exponential backoff: 5, 10, 20, 40 seconds, then a maximum of 60.
            delay = min(delay * 2, 60)


def load_requirements():
    """Parse headings like '## REQ-001: Successful Login' and retain each body."""
    # Report which requirements file is being read.
    log(f"Reading requirements: {REQUIREMENTS_FILE}")

    # Fail early with a useful message if the input file does not exist.
    if not REQUIREMENTS_FILE.exists():
        raise FileNotFoundError(f"Requirements file not found: {REQUIREMENTS_FILE}")

    # Read the complete Markdown document as text.
    text = REQUIREMENTS_FILE.read_text(encoding="utf-8")

    # Find headings such as '## REQ-001: Successful Login'.
    # Capturing groups extract the requirement ID and title separately.
    # MULTILINE makes ^ match the beginning of each line.
    pattern = re.compile(r"^##\s+(REQ-\d+)\s*:\s*(.+?)\s*$", re.MULTILINE)
    headings = list(pattern.finditer(text))

    # Build one dictionary per requirement.
    requirements = []
    for index, match in enumerate(headings):
        # The body starts after the current heading and ends before the next heading.
        # The last requirement extends to the end of the file.
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        requirements.append({
            "id": match.group(1).strip(),
            "title": match.group(2).strip(),
            "text": text[match.end():end].strip(),
        })

    # A malformed or differently formatted document should not silently produce no requirements.
    if not requirements:
        raise ValueError("No requirements found. Expected headings like ## REQ-001: Successful Login")

    log(f"Found {len(requirements)} requirements.")
    return requirements


def load_test_cases():
    """Read test cases without writing back to their original JSON file."""
    # Display the input path for traceability.
    log(f"Reading generated test cases: {TEST_CASES_FILE}")

    # Check that the test case source exists.
    if not TEST_CASES_FILE.exists():
        raise FileNotFoundError(f"Test cases file not found: {TEST_CASES_FILE}")

    # Load JSON into a Python dictionary or list.
    data = read_json(TEST_CASES_FILE)

    # Support either {"test_cases": [...]} or a JSON array containing cases directly.
    cases = data.get("test_cases", []) if isinstance(data, dict) else data

    # Validate the overall container type before processing individual cases.
    if not isinstance(cases, list):
        raise ValueError("Expected a JSON list or an object containing a test_cases list.")

    log(f"Found {len(cases)} generated test cases.")
    return cases


def source_hash():
    """Fingerprint both source files so changed input invalidates the mapping cache."""
    # Hash the raw bytes of each source file.
    # A content change produces a different SHA-256 fingerprint.
    combined = hashlib.sha256(REQUIREMENTS_FILE.read_bytes()).hexdigest()
    combined += hashlib.sha256(TEST_CASES_FILE.read_bytes()).hexdigest()

    # Hash the combined fingerprints to produce one cache-validation key.
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def read_cache():
    """Return a valid cache dictionary, or None when the cache is absent/unreadable."""
    # A missing cache is normal on the first run.
    if not CACHE_FILE.exists():
        return None

    try:
        # Read and return the cached mapping.
        return read_json(CACHE_FILE)
    except (OSError, json.JSONDecodeError):
        # If the cache cannot be read, continue by rebuilding it.
        log("Cache is unreadable; creating a fresh mapping.")
        return None


def map_requirements(requirements, cases, api_key):
    """Map test IDs to requirement IDs, reusing cache only when both inputs match."""
    # Generate a fingerprint for the current versions of both source files.
    current_hash = source_hash()

    # Load the previous mapping, if one exists.
    cache = read_cache()

    # Reuse the cache only when its source fingerprint matches the current inputs.
    if cache and cache.get("source_hash") == current_hash and isinstance(cache.get("mapping"), dict):
        log("Source files unchanged; reusing cached requirement mappings.")

        # No mapping API request happened on this run, so usage is N/A, not zero.
        return cache["mapping"], {
            "input_tokens": None, "output_tokens": None, "total_tokens": None,
            "cost": None, "status": "Cached mapping; no mapping API call this run",
        }, "CACHE HIT"

    # If the cache is absent or stale, ask Gemini to map the cases again.
    log("Mapping cache missing/stale; calling Gemini for requirement mapping.")

    # Send only the fields needed to describe each requirement to the model.
    requirement_payload = [{"id": r["id"], "title": r["title"], "text": r["text"]} for r in requirements]

    # Include each test case ID, title and full case data in the mapping prompt.
    case_payload = [{"id": c.get("id", "MISSING_ID"), "title": c.get("title", "Untitled"), "test_case": c} for c in cases]

    # The prompt defines the mapping task, restricts valid IDs, and specifies JSON output.
    # json.dumps serializes Python objects into text that can be sent to the model.
    prompt = f"""
Map each test case only to requirements it directly verifies. Use only IDs from
REQUIREMENTS. If none applies, return an empty list. Do not invent IDs.
Return ONLY JSON in this form: {{"mappings": {{"TC01": ["REQ-001", "REQ-004"]}}}}
REQUIREMENTS:
{json.dumps(requirement_payload, indent=2, ensure_ascii=False)}
TEST CASES:
{json.dumps(case_payload, indent=2, ensure_ascii=False)}
"""

    # Create a Gemini API client using the supplied key.
    client = genai.Client(api_key=api_key)

    # Wrap the external API call in retry handling so recognized transient failures retry.
    response = call_with_retry(
        "Gemini requirement mapping",
        lambda: client.models.generate_content(model=MODEL_NAME, contents=prompt),
    )

    # Parse the model response into Python data.
    parsed = parse_json_response(response.text)

    # Extract the mapping object. An absent field defaults to an empty dictionary.
    raw_mapping = parsed.get("mappings", {})

    # Create the allowed set of requirement IDs from the source requirements.
    valid_ids = {r["id"] for r in requirements}

    # Keep only mapping entries with lists of valid requirement IDs.
    # dict.fromkeys removes repeated IDs while preserving their original order.
    mapping = {}
    if isinstance(raw_mapping, dict):
        for test_id, ids in raw_mapping.items():
            if isinstance(ids, list):
                mapping[str(test_id)] = list(dict.fromkeys(
                    rid for rid in ids if isinstance(rid, str) and rid in valid_ids
                ))

    # Gemini's usage metadata may include token counts for this API request.
    # getattr safely returns None if a field is unavailable.
    metadata = getattr(response, "usage_metadata", None)
    usage = {
        "input_tokens": getattr(metadata, "prompt_token_count", None),
        "output_tokens": getattr(metadata, "candidates_token_count", None),
        "total_tokens": getattr(metadata, "total_token_count", None),
        "cost": None,
        "status": "Gemini SDK usage metadata when available",
    }

    # Persist the mapping and source fingerprint for reuse on future runs.
    # This writes only the cache file, not the requirements or test case inputs.
    write_json(CACHE_FILE, {
        "source_hash": current_hash,
        "mapping": mapping,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })

    log(f"Requirement mapping cache saved: {CACHE_FILE}")
    return mapping, usage, "CACHE MISS"


def deterministic_validation(requirements, cases, mapping):
    """Use ordinary Python rules for structure, duplicates, mapping and coverage."""
    # Store findings as human-readable messages for the final report.
    findings = []

    # Sets make it efficient to check whether an ID is known or already covered.
    requirement_ids = {r["id"] for r in requirements}
    ids, titles = [], []

    # Validate each test case independently.
    for case in cases:
        test_id = str(case.get("id", "")).strip()
        title = str(case.get("title", "")).strip()

        # An ID is required for reliable traceability.
        if not test_id:
            findings.append("A test case is missing its ID.")
        else:
            ids.append(test_id)

        # A title helps users identify the case in the report.
        if not title:
            findings.append(f"{test_id or '(no ID)'} is missing a title.")
        else:
            titles.append(title.casefold())

        # Source projects sometimes use expected_result, expected_results,
        # expected, or assertions. This check warns rather than modifying data.
        # The any() expression checks whether at least one supported field has a value.
        if not any(case.get(key) for key in ("expected_result", "expected_results", "expected", "assertions")):
            findings.append(f"{test_id or '(no ID)'} may be missing an explicit expected result.")

    # Counter reports how often each value occurs, allowing duplicate detection.
    for duplicate in (x for x, count in Counter(ids).items() if count > 1):
        findings.append(f"Duplicate test case ID: {duplicate}")

    # casefold() earlier makes title comparison case-insensitive.
    for duplicate in (x for x, count in Counter(titles).items() if count > 1):
        findings.append(f"Duplicate test case title: {duplicate}")

    # Identify test cases that have no entry in the requirement mapping.
    source_test_ids = {str(c.get("id", "")).strip() for c in cases if str(c.get("id", "")).strip()}
    unmapped = sorted(source_test_ids - set(mapping.keys()))
    for test_id in unmapped:
        findings.append(f"{test_id} has no requirement mapping.")

    # Collect every valid requirement that at least one test case maps to.
    covered = set()
    for test_id, mapped_ids in mapping.items():
        for requirement_id in mapped_ids:
            if requirement_id in requirement_ids:
                covered.add(requirement_id)
            else:
                findings.append(f"{test_id} references unknown requirement {requirement_id}.")

    # Requirements absent from the covered set are traceability gaps.
    uncovered = sorted(requirement_ids - covered)
    for requirement_id in uncovered:
        findings.append(f"{requirement_id} is not covered by mapped test cases.")

    # Return the findings and summary data for the HTML report.
    return {
        "findings": findings,
        "covered_requirements": sorted(covered),
        "uncovered_requirements": uncovered,
        "unmapped_cases": unmapped,
        "coverage_percent": round(100 * len(covered) / len(requirement_ids), 2) if requirement_ids else 0,
    }


def read_deepeval_usage(metric):
    """Read only usage/cost fields that this installed metric actually exposes."""
    # These fields are optional because exposure depends on the installed DeepEval version/model.
    input_tokens = getattr(metric, "input_tokens", None)
    output_tokens = getattr(metric, "output_tokens", None)
    cost = getattr(metric, "evaluation_cost", None)

    # Some versions may use a different attribute name for the reported cost.
    if cost is None:
        cost = getattr(metric, "cost", None)

    # Calculate a total only if both input and output token counts are numeric.
    total = input_tokens + output_tokens if isinstance(input_tokens, (int, float)) and isinstance(output_tokens, (int, float)) else None

    # Determine whether the metric exposes at least one usage/cost field.
    has_any = any(v is not None for v in (input_tokens, output_tokens, cost))
    return {
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "total_tokens": total, "cost": cost,
        "status": "DeepEval fields exposed" if has_any else "DeepEval usage fields unavailable",
    }


def evaluate_cases(requirements, cases, mapping, api_key):
    """Evaluate requirement alignment per case; record errors without losing other results."""
    log("Starting DeepEval semantic evaluation.")

    # Configure the Gemini model used by DeepEval as its LLM judge.
    # temperature=0 aims to reduce randomness, although it cannot guarantee identical judgments.
    judge = GeminiModel(model=MODEL_NAME, api_key=api_key, temperature=0)

    # Dictionary lookup lets us retrieve a requirement quickly using its ID.
    req_by_id = {r["id"]: r for r in requirements}

    # Keep evaluation results and usage information in separate lists.
    results, usage_rows = [], []

    # enumerate(..., start=1) provides a readable one-based progress counter.
    for index, case in enumerate(cases, start=1):
        # Start a timer for this specific case.
        started = time.perf_counter()
        test_id = str(case.get("id", f"CASE-{index}"))
        title = str(case.get("title", "Untitled test case"))
        log(f"Evaluating {index}/{len(cases)}: {test_id} - {title}")

        # Resolve mapped requirement IDs into full requirement descriptions.
        mapped = []
        for rid in mapping.get(test_id, []):
            if rid in req_by_id:
                req = req_by_id[rid]
                mapped.append(f"{rid}: {req['title']}\n{req['text']}")

        # Without a mapped requirement, semantic alignment cannot be evaluated meaningfully.
        if not mapped:
            results.append({"id": test_id, "title": title, "status": "SKIPPED", "score": None,
                            "reason": "No mapped requirement; semantic alignment could not be assessed.",
                            "elapsed_seconds": elapsed(started)})

            # Usage is unknown/not applicable because no LLM evaluation was performed.
            usage_rows.append({"operation": f"DeepEval {test_id}", "input_tokens": None,
                               "output_tokens": None, "total_tokens": None, "cost": None,
                               "status": "Skipped; no mapped requirement"})
            continue

        # Create the DeepEval test-case object.
        # expected_output represents the requirement baseline.
        # actual_output represents the generated test case being assessed.
        # input explains the task to the evaluator.
        llm_case = LLMTestCase(
            input="Assess whether this generated QA test case verifies the stated requirement.",
            expected_output="\n\n".join(mapped),
            actual_output=json.dumps(case, indent=2, ensure_ascii=False),
        )

        # Configure G-Eval, an LLM-as-a-judge metric that scores semantic alignment.
        metric = GEval(
            name="Requirement Alignment",
            criteria=(
                "Assess whether the test case directly verifies the supplied requirement. "
                "Consider intent, actions, and expected results. Lower the score for partial, "
                "weak, or unrelated alignment. Do not assume a test is correct merely because "
                "it uses similar words."
            ),

            # SingleTurnParams identifies which parts of the test case are sent to the judge.
            evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.EXPECTED_OUTPUT, SingleTurnParams.ACTUAL_OUTPUT],

            # Scores at or above this threshold are classified as PASS.
            threshold=PASS_THRESHOLD,

            # Use the Gemini judge configured above.
            model=judge,
        )

        try:
            # The retry wrapper handles transient failures without a retry cutoff.
            # metric.measure() performs the semantic evaluation.
            call_with_retry(f"DeepEval evaluation for {test_id}", lambda: metric.measure(llm_case))

            # Read the score and explanation produced by the metric.
            score = getattr(metric, "score", None)
            reason = getattr(metric, "reason", None) or "No explanation returned."

            # A missing score is an ERROR; otherwise compare it with the configured threshold.
            status = "ERROR" if score is None else ("PASS" if score >= PASS_THRESHOLD else "FAIL")

            # Store the result and elapsed time for this test case.
            results.append({"id": test_id, "title": title, "status": status, "score": score,
                            "reason": reason, "elapsed_seconds": elapsed(started)})

            # Record token/cost fields only when DeepEval exposes them.
            usage_rows.append({"operation": f"DeepEval {test_id}", **read_deepeval_usage(metric)})
            log(f"{test_id}: {status}; score={score}; elapsed={elapsed(started)} sec")

        except Exception as error:
            # A permanent error is recorded for this case; later cases can still run.
            message = f"{type(error).__name__}: {error}"
            results.append({"id": test_id, "title": title, "status": "ERROR", "score": None,
                            "reason": message, "elapsed_seconds": elapsed(started)})

            # If the evaluation failed, its usage may not be available.
            usage_rows.append({"operation": f"DeepEval {test_id}", "input_tokens": None,
                               "output_tokens": None, "total_tokens": None, "cost": None,
                               "status": "Usage unavailable because evaluation errored"})
            log(f"{test_id}: ERROR - {message}")

    # Return both the semantic outcomes and their usage records.
    return results, usage_rows


def aggregate_usage(mapping_usage, deepeval_rows):
    """Aggregate known usage only and flag totals as partial when values are missing."""
    # Combine the direct Gemini mapping request with the individual DeepEval usage rows.
    rows = [{"operation": "Gemini requirement mapping", **mapping_usage}] + deepeval_rows

    # These are the numeric fields to summarize across all operations.
    fields = ("input_tokens", "output_tokens", "total_tokens", "cost")
    summary = {}

    for field in fields:
        # Include only numeric values. Unknown values remain excluded from the sum.
        known = [row.get(field) for row in rows if isinstance(row.get(field), (int, float))]
        summary[field] = sum(known) if known else None

    # Mark token totals as partial if any operation lacks one of the token measurements.
    summary["partial"] = any(row.get(field) is None for row in rows for field in fields[:3])
    return rows, summary


def write_html_report(requirements, cases, mapping, validation, results, usage_rows,
                      usage_summary, cache_status, run_start, fatal_error=None):
    """Write a self-contained HTML report that can be opened directly in a browser."""
    # Ensure the reports directory exists before writing the report.
    HTML_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Build the requirement table, marking each requirement as covered or a gap.
    # safe_html() protects text values from being interpreted as HTML.
    covered = set(validation["covered_requirements"])
    req_rows = "".join(
        f"<tr><td>{safe_html(r['id'])}</td><td>{safe_html(r['title'])}</td>"
        f"<td>{'Covered' if r['id'] in covered else 'Gap'}</td></tr>" for r in requirements
    )

    # Build the traceability table linking test cases to requirement IDs.
    map_rows = "".join(
        f"<tr><td>{safe_html(c.get('id', 'MISSING_ID'))}</td>"
        f"<td>{safe_html(c.get('title', 'Untitled'))}</td>"
        f"<td>{safe_html(', '.join(mapping.get(str(c.get('id', '')), [])) or 'None')}</td></tr>"
        for c in cases
    )

    # Build the DeepEval results table with score, status, timing and reason.
    result_rows = "".join(
        "<tr>"
        f"<td>{safe_html(r.get('id'))}</td><td>{safe_html(r.get('title'))}</td>"
        f"<td>{safe_html(r.get('status'))}</td>"
        f"<td>{safe_html(format_score(r.get('score')))}</td>"
        f"<td>{safe_html(r.get('elapsed_seconds', 'N/A'))}</td><td>{safe_html(r.get('reason', ''))}</td>"
        "</tr>" for r in results
    )

    # Build the API usage table, showing N/A for unknown measurements.
    usage_table_rows = "".join(
        "<tr>"
        f"<td>{safe_html(r.get('operation'))}</td>"
        f"<td>{safe_html(display_number(r.get('input_tokens')))}</td>"
        f"<td>{safe_html(display_number(r.get('output_tokens')))}</td>"
        f"<td>{safe_html(display_number(r.get('total_tokens')))}</td>"
        f"<td>{safe_html(r.get('cost') if r.get('cost') is not None else 'N/A')}</td>"
        f"<td>{safe_html(r.get('status', ''))}</td></tr>" for r in usage_rows
    )

    # Convert validation findings into HTML list items.
    # If there are no findings, display a default message instead.
    findings = "".join(f"<li>{safe_html(x)}</li>" for x in validation["findings"]) or "<li>No deterministic findings.</li>"

    # Count each evaluation status for the summary cards.
    passed = sum(r["status"] == "PASS" for r in results)
    failed = sum(r["status"] == "FAIL" for r in results)
    errors = sum(r["status"] == "ERROR" for r in results)
    skipped = sum(r["status"] == "SKIPPED" for r in results)

    # Calculate the average of available numeric scores; exclude missing scores.
    scores = [r["score"] for r in results if isinstance(r.get("score"), (int, float))]
    average = f"{sum(scores) / len(scores):.2f}" if scores else "N/A"

    # Explain whether usage totals are complete or partial.
    note = "Partial total: one or more operations did not expose token counts." if usage_summary["partial"] else "All listed operations exposed token counts."

    # Include run-level errors in the report if an error occurred outside an individual case.
    fatal = f"<p class='error'><b>Run-level error:</b> {safe_html(fatal_error)}</p>" if fatal_error else ""

    # Construct the complete standalone HTML document.
    # CSS inside <style> controls presentation; the tables and cards display evaluation data.
    # Double braces are used where necessary because this is an f-string.
    html_doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AI QA Test Case Evaluation</title>
<style>body{{font-family:Arial,sans-serif;margin:28px;color:#202124}}h1,h2{{color:#243447}}table{{border-collapse:collapse;width:100%;margin:12px 0 26px}}th,td{{border:1px solid #ddd;padding:9px;text-align:left;vertical-align:top}}th{{background:#eef2f6}}tr:nth-child(even){{background:#fafafa}}.cards{{display:flex;flex-wrap:wrap;gap:12px}}.card{{border:1px solid #ddd;border-radius:8px;padding:12px;min-width:125px}}.card b{{display:block;font-size:22px;margin-top:6px}}.note{{background:#f5f7f9;padding:12px}}.error{{color:#9b1c1c}}.small{{color:#555}}</style></head><body>
<h1>AI QA Test Case Evaluation</h1><p class="small">Generated: {safe_html(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</p>
<p><b>Model:</b> {safe_html(MODEL_NAME)} | <b>Mapping cache:</b> {safe_html(cache_status)}</p>{fatal}
<div class="cards">
<div class="card">Test cases<b>{len(cases)}</b></div><div class="card">Requirements<b>{len(requirements)}</b></div>
<div class="card">Requirements covered<b>{len(covered)}</b></div><div class="card">Coverage<b>{validation['coverage_percent']}%</b></div>
<div class="card">PASS<b>{passed}</b></div><div class="card">FAIL<b>{failed}</b></div><div class="card">ERROR / SKIPPED<b>{errors} / {skipped}</b></div>
<div class="card">Average score<b>{safe_html(average)}</b></div><div class="card">Elapsed seconds<b>{elapsed(run_start)}</b></div></div>
<h2>1. Requirement coverage</h2><p>Coverage is traceability coverage, not proof that a requirement is fully tested.</p>
<table><thead><tr><th>ID</th><th>Requirement</th><th>Status</th></tr></thead><tbody>{req_rows}</tbody></table>
<h2>2. AI-generated requirement mappings</h2><p>Review these suggestions before treating them as an approved traceability matrix.</p>
<table><thead><tr><th>Test ID</th><th>Test case</th><th>Mapped requirements</th></tr></thead><tbody>{map_rows}</tbody></table>
<h2>3. DeepEval semantic evaluation</h2><p>G-Eval threshold: {PASS_THRESHOLD:.2f}. A score is a model-generated judgment, not proof of correctness or execution.</p>
<table><thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Score</th><th>Seconds</th><th>Reason / error</th></tr></thead><tbody>{result_rows}</tbody></table>
<h2>4. Token usage and cost</h2><p class="note">{safe_html(note)} N/A means unavailable, not zero. Cached mappings make no new mapping call. Costs appear only when a library reports them; this script does not guess prices.</p>
<table><thead><tr><th>Operation</th><th>Input</th><th>Output</th><th>Total</th><th>Cost</th><th>Measurement status</th></tr></thead>
<tbody>{usage_table_rows}</tbody><tfoot><tr><th>Known totals</th><td>{safe_html(display_number(usage_summary['input_tokens']))}</td>
<td>{safe_html(display_number(usage_summary['output_tokens']))}</td><td>{safe_html(display_number(usage_summary['total_tokens']))}</td>
<td>{safe_html(usage_summary['cost'] if usage_summary['cost'] is not None else 'N/A')}</td><td>{'Partial' if usage_summary['partial'] else 'Reported'}</td></tr></tfoot></table>
<h2>5. Deterministic validation findings</h2><ul>{findings}</ul>
<h2>6. Interpretation notes</h2><ul><li>Requirement mapping is AI-suggested traceability and needs review.</li><li>G-Eval scores may vary; they are not proof of test correctness.</li><li>API errors/timeouts are distinct from a test case failing against the application.</li><li>Coverage gaps indicate requirements without a mapped test, not necessarily missing tests in every repository.</li></ul>
</body></html>"""

    # Save the completed HTML string as a standalone report.
    # It can be opened in a browser without running the test suite or a web server.
    HTML_REPORT_FILE.write_text(html_doc, encoding="utf-8")
    log(f"HTML report written: {HTML_REPORT_FILE}")


def main():
    """Orchestrate the workflow and try to write a report even after a run-level error."""
    # Record the start of the full pipeline for total execution-time reporting.
    started = time.perf_counter()

    # Initialize variables so the final report can still be attempted if an early step fails.
    requirements, cases, mapping, results, deepeval_usage = [], [], {}, [], []

    # Default usage and validation structures are used until real results are available.
    mapping_usage = {"input_tokens": None, "output_tokens": None, "total_tokens": None,
                     "cost": None, "status": "Not started"}
    validation = {"findings": [], "covered_requirements": [], "uncovered_requirements": [],
                  "unmapped_cases": [], "coverage_percent": 0}

    # Track the mapping cache state and any error that prevents the full run from completing.
    cache_status, fatal_error = "Not started", None

    try:
        # Read the API key from environment variables.
        # Prefer GEMINI_API_KEY; use GOOGLE_API_KEY as a fallback.
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError("Gemini API key not found. Set GEMINI_API_KEY in your .env file.")

        # Load source inputs.
        requirements = load_requirements()
        cases = load_test_cases()

        # Stop early if the test case input is empty.
        if not cases:
            raise ValueError("No test cases were found in the generated test case JSON.")

        # Map cases to requirements, using the cache when the input fingerprint matches.
        mapping, mapping_usage, cache_status = map_requirements(requirements, cases, api_key)

        # Run objective checks before invoking semantic evaluation.
        log("Running deterministic validation.")
        validation = deterministic_validation(requirements, cases, mapping)

        # Ask DeepEval to assess each mapped test case's semantic alignment.
        log("Running DeepEval semantic checks.")
        results, deepeval_usage = evaluate_cases(requirements, cases, mapping, api_key)

    except KeyboardInterrupt:
        # This is the user's manual stop (Ctrl+C), not a timeout configured here.
        fatal_error = "Stopped manually by user (KeyboardInterrupt)."
        log(fatal_error)

    except Exception as error:
        # Record a run-level exception, such as missing input files or invalid credentials.
        fatal_error = f"{type(error).__name__}: {error}"
        log(f"Run-level ERROR: {fatal_error}")

    finally:
        # Prepare usage totals even if the workflow stopped early.
        usage_rows, usage_summary = aggregate_usage(mapping_usage, deepeval_usage)

        try:
            # Attempt to generate a report with all information collected so far.
            write_html_report(requirements, cases, mapping, validation, results,
                              usage_rows, usage_summary, cache_status, started, fatal_error)
        except Exception as error:
            # Report-generation errors are logged separately because the HTML may not be available.
            log(f"Could not write HTML report: {type(error).__name__}: {error}")

    # Display the full script runtime, including input loading, API calls, retries, and report writing.
    log(f"Finished. Total elapsed time: {elapsed(started)} seconds.")

    # Show the exact location of the generated HTML report.
    log(f"Report location: {HTML_REPORT_FILE}")


# This condition ensures main() runs only when this file is executed directly.
# Importing the file from another Python module will not automatically start the evaluation.
if __name__ == "__main__":
    main()