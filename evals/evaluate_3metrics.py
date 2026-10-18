
"""
Standalone LLM evaluation for generated test cases.

Metrics:
1. Faithfulness: pass/fail gate.
2. Hallucination: pass/fail gate.
3. Contextual Relevancy: score and configurable threshold.

Read-only inputs:
    NewRequirment/saucedemo_requirements.md
    reports/generated_test_cases.json

Output:
    reports/faithfulness_evaluation_report.html

This script does not modify existing test cases, Page Objects,
test execution reports, or the existing evaluator.
"""

import html
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

# Establish project paths and load configuration before importing DeepEval.
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Preserve the existing project's timeout setting.
os.environ.setdefault("DEEPEVAL_DISABLE_TIMEOUTS", "1")

from deepeval.metrics import (
    FaithfulnessMetric,
    HallucinationMetric,
    ContextualRelevancyMetric,
)
from deepeval.models import GeminiModel
from deepeval.test_case import LLMTestCase


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

REQUIREMENTS_FILE = ROOT / "NewRequirment" / "saucedemo_requirements.md"
TEST_CASES_FILE = ROOT / "reports" / "generated_test_cases.json"
REPORT_FILE = ROOT / "reports" / "faithfulness_evaluation_report.html"

MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3.8-flash")

# Minimum passing scores. DeepEval 4.2.8 uses higher-is-better
# scoring for all three configured metrics.
FAITHFULNESS_THRESHOLD = 0.70
HALLUCINATION_THRESHOLD = 0.80
CONTEXTUAL_RELEVANCY_THRESHOLD = 0.70

# Minimum number of shared meaningful words for a confident match.
MINIMUM_KEYWORD_OVERLAP = 2

# Wait this long after one metric finishes before starting the next.
# Override in .env using GEMINI_REQUEST_DELAY_SECONDS=30.
GEMINI_REQUEST_DELAY_SECONDS = max(
    0.0,
    float(os.getenv("GEMINI_REQUEST_DELAY_SECONDS", "30")),
)

# Retry a temporary 503 at most once.
GEMINI_503_RETRY_DELAY_SECONDS = 30
MAX_503_RETRIES = 1

STOP_WORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for",
    "is", "are", "was", "were", "be", "by", "with", "from", "as",
    "it", "this", "that", "then", "when", "where", "should", "must",
    "verify", "check", "test", "user", "system", "expected", "actual",
    "given", "using", "ensure", "confirm", "page", "application",
}


# ---------------------------------------------------------
# File reading
# ---------------------------------------------------------

def read_json(path):
    """Read a JSON file without changing it."""
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_requirements(path):
    """
    Parse requirements from Markdown.

    Preferred format:
        ## REQ-001: Successful login
        Requirement details...

        ## REQ-002: Add product to cart
        Requirement details...

    Also accepts IDs such as REQ_001 and REQUIREMENT-001.
    """
    if not path.exists():
        raise FileNotFoundError(f"Requirements file not found: {path}")

    content = path.read_text(encoding="utf-8").strip()

    if not content:
        raise ValueError("The requirements file is empty.")

    heading_pattern = re.compile(
        r"(?m)^#{1,6}\s+"
        r"((?:REQ(?:UIREMENT)?)[-_ ]?\d+)"
        r"\s*[:.\-–]?\s*(.*)$",
        re.IGNORECASE,
    )

    matches = list(heading_pattern.finditer(content))
    requirements = []

    for index, match in enumerate(matches):
        start = match.end()
        end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(content)
        )

        requirement_id = match.group(1).upper()
        title = match.group(2).strip()
        body = content[start:end].strip()
        body = re.sub(r"(?m)^#{1,6}\s+", "", body)

        text = "\n".join(
            part for part in [title, body] if part
        ).strip()

        if text:
            requirements.append({
                "id": requirement_id,
                "title": title or requirement_id,
                "text": text,
            })

    if requirements:
        return requirements

    # Do not invent requirement IDs if the document has no ID headings.
    return [{
        "id": "FULL_DOCUMENT",
        "title": "Full requirements document",
        "text": content,
    }]


def load_test_cases(path):
    """Support the project's {'test_cases': [...]} structure."""
    data = read_json(path)

    if isinstance(data, dict):
        cases = data.get("test_cases", [])
    elif isinstance(data, list):
        cases = data
    else:
        cases = []

    if not cases:
        raise ValueError(
            "No test cases found. Expected a JSON list or "
            "{'test_cases': [...]}."
        )

    return cases


# ---------------------------------------------------------
# Requirement matching
# ---------------------------------------------------------

def meaningful_words(text):
    words = re.findall(r"[a-zA-Z0-9]+", str(text).lower())

    return {
        word for word in words
        if len(word) > 2 and word not in STOP_WORDS
    }


def test_case_text(test_case):
    """Create readable evaluation text from a generated test case."""
    return json.dumps(test_case, ensure_ascii=False, indent=2)


def get_explicit_requirement_ids(test_case):
    """Use explicit requirement references if supplied."""
    for key in ("requirement_id", "requirement_ids", "requirements"):
        value = test_case.get(key)

        if isinstance(value, str) and value.strip():
            return [value.strip().upper()]

        if isinstance(value, list):
            return [
                str(item).strip().upper()
                for item in value
                if str(item).strip()
            ]

    return []


def match_requirement(test_case, requirements):
    """
    Match a test case to its most relevant requirement.

    Explicit IDs take priority. Otherwise, use keyword overlap.
    Weak or ambiguous matches are marked UNMAPPED.
    """
    explicit_ids = get_explicit_requirement_ids(test_case)

    if explicit_ids:
        matches = [
            requirement
            for requirement in requirements
            if requirement["id"] in explicit_ids
        ]

        if matches:
            return matches, "EXPLICIT_ID"

        return [], "INVALID_REQUIREMENT_ID"

    case_words = meaningful_words(test_case_text(test_case))
    ranked = []

    for requirement in requirements:
        requirement_words = meaningful_words(requirement["text"])
        overlap = case_words & requirement_words

        ranked.append({
            "requirement": requirement,
            "overlap_count": len(overlap),
            "overlap_words": sorted(overlap),
        })

    ranked.sort(
        key=lambda item: item["overlap_count"],
        reverse=True,
    )

    if not ranked:
        return [], "UNMAPPED"

    best = ranked[0]

    if best["overlap_count"] < MINIMUM_KEYWORD_OVERLAP:
        return [], "UNMAPPED"

    tied = [
        item for item in ranked
        if item["overlap_count"] == best["overlap_count"]
    ]

    if len(tied) > 1:
        return [], "AMBIGUOUS_MATCH"

    return [best["requirement"]], "KEYWORD_MATCH"


# ---------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------

def score_value(metric):
    """Return a numeric score if DeepEval supplied one."""
    score = getattr(metric, "score", None)

    try:
        return float(score) if score is not None else None
    except (TypeError, ValueError):
        return None


def status_from_score(score, threshold):
    """All configured metrics use higher-is-better scoring."""
    if score is None:
        return "ERROR"

    return "PASS" if score >= threshold else "FAIL"


def metric_reason(metric):
    return str(
        getattr(metric, "reason", None) or "No reason returned."
    )


def is_quota_error(error):
    message = str(error).upper()

    return any(marker in message for marker in (
        "RESOURCE_EXHAUSTED",
        "QUOTA EXCEEDED",
        "QUOTA_EXCEEDED",
        "INSUFFICIENT QUOTA",
        "BILLING",
    ))


def is_service_unavailable(error):
    """Identify temporary Gemini service-unavailable errors."""
    message = str(error).upper()

    return (
        "503" in message
        or "UNAVAILABLE" in message
        or "SERVICE_UNAVAILABLE" in message
    )


def run_metric(metric, test_case, metric_name):
    """Run a metric and retry a temporary 503 at most once."""
    thresholds = {
        "Faithfulness": FAITHFULNESS_THRESHOLD,
        "Hallucination": HALLUCINATION_THRESHOLD,
        "Contextual Relevancy": CONTEXTUAL_RELEVANCY_THRESHOLD,
    }

    result = {
        "name": metric_name,
        "score": None,
        "status": "ERROR",
        "reason": "",
        "elapsed_seconds": 0.0,
        "error": None,
        "quota_error": False,
        "service_unavailable": False,
    }

    started = time.perf_counter()

    try:
        for attempt in range(MAX_503_RETRIES + 1):
            try:
                metric.measure(test_case)

                score = score_value(metric)
                threshold = thresholds[metric_name]

                result.update({
                    "score": score,
                    "status": status_from_score(score, threshold),
                    "reason": metric_reason(metric),
                    "error": None,
                    "quota_error": False,
                    "service_unavailable": False,
                })
                break

            except Exception as error:
                result["error"] = str(error)
                result["reason"] = (
                    f"Metric execution failed: {error}"
                )
                result["quota_error"] = is_quota_error(error)
                result["service_unavailable"] = (
                    is_service_unavailable(error)
                )

                # Never automatically retry quota errors.
                if result["quota_error"]:
                    break

                # Retry only a temporary 503, at most once.
                if (
                    result["service_unavailable"]
                    and attempt < MAX_503_RETRIES
                ):
                    print(
                        f"  {metric_name}: Gemini returned 503. "
                        f"Retrying once after "
                        f"{GEMINI_503_RETRY_DELAY_SECONDS}s."
                    )
                    time.sleep(GEMINI_503_RETRY_DELAY_SECONDS)
                    continue

                break

    finally:
        result["elapsed_seconds"] = round(
            time.perf_counter() - started, 2
        )

    return result


# ---------------------------------------------------------
# HTML report
# ---------------------------------------------------------

def score_display(score):
    return "N/A" if score is None else f"{score:.3f}"


def safe(value):
    return html.escape(
        str(value if value is not None else "")
    )


def badge(status):
    css_class = status.lower().replace(" ", "-")
    return (
        f'<span class="badge {css_class}">'
        f'{safe(status)}</span>'
    )


def write_html_report(
    results,
    started_at,
    elapsed_seconds,
    fatal_error=None,
):
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)

    total = len(results)
    passed = sum(
        item["overall_status"] == "PASS" for item in results
    )
    failed = sum(
        item["overall_status"] == "FAIL" for item in results
    )
    blocked = sum(
        item["overall_status"] in ("UNMAPPED", "ERROR")
        for item in results
    )

    rows = []

    for item in results:
        metrics = item.get("metrics", {})

        def metric_cell(name):
            metric = metrics.get(name)

            if not metric:
                return (
                    "<td>N/A</td><td>NOT_RUN</td><td>N/A</td>"
                )

            return (
                f"<td>{safe(score_display(metric['score']))}</td>"
                f"<td>{badge(metric['status'])}</td>"
                f"<td>{safe(metric['elapsed_seconds'])}</td>"
            )

        metric_reasons = []

        for name, metric in metrics.items():
            error_text = metric.get("error")
            reason_text = metric.get("reason", "")

            if error_text:
                reason_text = (
                    f"{reason_text}\nError: {error_text}"
                )

            metric_reasons.append(
                f"<details><summary>{safe(name)}: "
                f"{safe(metric['status'])}</summary>"
                f"<p>{safe(reason_text)}</p>"
                f"</details>"
            )

        rows.append(f"""
        <tr>
            <td>{safe(item['test_id'])}</td>
            <td>{safe(item['title'])}</td>
            <td>{safe(', '.join(item['requirement_ids']) or 'Not matched')}</td>
            <td>{badge(item['overall_status'])}</td>
            {metric_cell('Faithfulness')}
            {metric_cell('Hallucination')}
            {metric_cell('Contextual Relevancy')}
            <td>{''.join(metric_reasons)}</td>
        </tr>
        """)

    fatal_section = (
        f"<p class='error'><b>Run issue:</b> "
        f"{safe(fatal_error)}</p>"
        if fatal_error else ""
    )

    document = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLM Test Case Integrity Evaluation</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 28px; color: #222; }}
h1 {{ margin-bottom: 8px; }}
.summary {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 20px 0; }}
.card {{ border: 1px solid #ddd; border-radius: 8px; padding: 14px; min-width: 110px; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
th, td {{ border: 1px solid #ddd; padding: 9px; text-align: left; vertical-align: top; }}
th {{ background: #f2f2f2; }}
.badge {{ display: inline-block; border-radius: 4px; padding: 4px 7px; font-weight: bold; }}
.pass {{ background: #d9f2df; color: #14532d; }}
.fail {{ background: #ffe0e0; color: #8b1e1e; }}
.error, .unmapped, .ambiguous-match, .invalid-requirement-id {{ color: #9a3412; }}
.error {{ background: #fff1f0; padding: 10px; }}
details {{ min-width: 180px; margin-bottom: 6px; }}
small {{ color: #555; }}
</style>
</head>
<body>
<h1>LLM Test Case Integrity Evaluation</h1>
<p>Generated at: {safe(started_at)}</p>
<p>Model: {safe(MODEL_NAME)}</p>
<p>Total evaluation time: {safe(elapsed_seconds)} seconds</p>
{fatal_section}

<div class="summary">
<div class="card"><b>Total cases</b><h2>{total}</h2></div>
<div class="card"><b>Passed gates</b><h2>{passed}</h2></div>
<div class="card"><b>Failed gates</b><h2>{failed}</h2></div>
<div class="card"><b>Unmapped/errors</b><h2>{blocked}</h2></div>
</div>

<p><b>Gate policy:</b> Faithfulness and Hallucination must each
meet their minimum passing thresholds. Contextual Relevancy is
reported separately and does not replace the integrity gates.</p>

<p><small>LLM-as-a-judge results are estimates, not proof of correctness.
Review failures and borderline scores manually. Keyword-based requirement
matching can be ambiguous and is reported as unmapped when uncertain.</small></p>

<table>
<thead><tr>
<th>Test ID</th><th>Title</th><th>Requirement</th><th>Overall</th>
<th>Faithfulness score</th><th>Faithfulness status</th><th>Seconds</th>
<th>Hallucination score</th><th>Hallucination status</th><th>Seconds</th>
<th>Contextual Relevancy score</th><th>Relevancy status</th><th>Seconds</th>
<th>Metric reasons</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>

<h2>Thresholds</h2>
<ul>
<li>Faithfulness: score ≥ {FAITHFULNESS_THRESHOLD}</li>
<li>Hallucination: score ≥ {HALLUCINATION_THRESHOLD}</li>
<li>Contextual Relevancy: score ≥ {CONTEXTUAL_RELEVANCY_THRESHOLD}</li>
</ul>
<p><small>Request pacing: {GEMINI_REQUEST_DELAY_SECONDS} seconds
between metric runs, with a bounded retry for temporary 503 errors.</small></p>
</body>
</html>
"""

    REPORT_FILE.write_text(document, encoding="utf-8")


# ---------------------------------------------------------
# Main evaluation flow
# ---------------------------------------------------------

def main():
    # Load again so the configuration is available when main is called.
    load_dotenv(ROOT / ".env")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY was not found. Check the project's .env file."
        )

    if not REQUIREMENTS_FILE.exists():
        raise FileNotFoundError(
            f"Missing requirements: {REQUIREMENTS_FILE}"
        )

    if not TEST_CASES_FILE.exists():
        raise FileNotFoundError(
            f"Missing test cases: {TEST_CASES_FILE}"
        )

    requirements = load_requirements(REQUIREMENTS_FILE)
    cases = load_test_cases(TEST_CASES_FILE)

    judge = GeminiModel(
        model=MODEL_NAME,
        api_key=api_key,
    )

    results = []
    run_started = time.perf_counter()
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    fatal_error = None
    quota_exhausted = False
    stop_evaluation = False

    # Tracks when the preceding metric finished, across all test cases.
    last_metric_finished_at = None

    print(f"Loaded {len(requirements)} requirement section(s).")
    print(f"Loaded {len(cases)} test case(s).")
    print(f"Using model: {MODEL_NAME}")
    print(
        "Delay between metric runs: "
        f"{GEMINI_REQUEST_DELAY_SECONDS}s"
    )

    for index, case in enumerate(cases, start=1):
        test_id = str(case.get("id", f"TC{index:02d}"))
        title = str(case.get("title", "Untitled test case"))

        print(
            f"\n[{index}/{len(cases)}] "
            f"Evaluating {test_id}: {title}"
        )

        matched_requirements, match_status = match_requirement(
            case, requirements
        )

        item = {
            "test_id": test_id,
            "title": title,
            "requirement_ids": [
                requirement["id"]
                for requirement in matched_requirements
            ],
            "match_status": match_status,
            "overall_status": "UNMAPPED",
            "metrics": {},
        }

        if not matched_requirements:
            results.append(item)
            print(f"  Skipping metrics: {match_status}")
            continue

        # Use only the matched requirement(s) as evaluation context.
        requirement_context = [
            requirement["text"]
            for requirement in matched_requirements
        ]

        generated_output = test_case_text(case)

        evaluation_case = LLMTestCase(
            input=(
                "Evaluate whether this generated test case is supported "
                "by the source requirement, avoids unsupported claims, "
                "and is relevant to the requirement."
            ),
            actual_output=generated_output,
            retrieval_context=requirementdock_context,
            context=requirement_context,
        )

        metrics_to_run = [
            (
                "Faithfulness",
                FaithfulnessMetric(
                    threshold=FAITHFULNESS_THRESHOLD,
                    model=judge,
                    include_reason=True,
                ),
            ),
            (
                "Hallucination",
                HallucinationMetric(
                    threshold=HALLUCINATION_THRESHOLD,
                    model=judge,
                    include_reason=True,
                ),
            ),
            (
                "Contextual Relevancy",
                ContextualRelevancyMetric(
                    threshold=CONTEXTUAL_RELEVANCY_THRESHOLD,
                    model=judge,
                    include_reason=True,
                ),
            ),
        ]

        for metric_name, metric in metrics_to_run:
            # Enforce a minimum wait after the preceding metric finishes.
            if last_metric_finished_at is not None:
                elapsed_since_previous = (
                    time.monotonic() - last_metric_finished_at
                )
                remaining_delay = (
                    GEMINI_REQUEST_DELAY_SECONDS
                    - elapsed_since_previous
                )

                if remaining_delay > 0:
                    print(
                        f"  Waiting {remaining_delay:.1f}s before "
                        f"running {metric_name}..."
                    )
                    time.sleep(remaining_delay)

            print(f"  Running {metric_name}...")

            metric_result = run_metric(
                metric,
                evaluation_case,
                metric_name,
            )

            last_metric_finished_at = time.monotonic()
            item["metrics"][metric_name] = metric_result

            print(
                f"  {metric_name}: {metric_result['status']} "
                f"(score={score_display(metric_result['score'])}, "
                f"{metric_result['elapsed_seconds']}s)"
            )

            if metric_result["quota_error"]:
                quota_exhausted = True
                stop_evaluation = True
                fatal_error = (
                    "Gemini API quota was exceeded. Evaluation stopped "
                    "without further metric calls. Check the quota and "
                    "billing for the Google AI Studio project."
                )
                print(fatal_error)
                break

            if metric_result["service_unavailable"]:
                stop_evaluation = True
                fatal_error = (
                    "Gemini remained unavailable after a bounded retry. "
                    "Evaluation stopped to avoid further API calls."
                )
                print(fatal_error)
                break

        faithfulness = item["metrics"].get("Faithfulness", {})
        hallucination = item["metrics"].get("Hallucination", {})
        relevancy = item["metrics"].get("Contextual Relevancy", {})

        # Both integrity gates must pass for an overall PASS.
        if (
            faithfulness.get("status") == "PASS"
            and hallucination.get("status") == "PASS"
        ):
            item["overall_status"] = "PASS"
        elif (
            faithfulness.get("status") == "FAIL"
            or hallucination.get("status") == "FAIL"
        ):
            item["overall_status"] = "FAIL"
        else:
            item["overall_status"] = "ERROR"

        item["contextual_relevancy_status"] = relevancy.get(
            "status", "NOT_RUN"
        )

        results.append(item)

        if stop_evaluation:
            break

    elapsed_seconds = round(
        time.perf_counter() - run_started, 2
    )

    # Always write a report, including after a quota or service error.
    write_html_report(
        results,
        started_at,
        elapsed_seconds,
        fatal_error=fatal_error,
    )

    print("\nEvaluation finished.")
    print(f"HTML report: {REPORT_FILE}")
    print(f"Elapsed time: {elapsed_seconds}s")

    if fatal_error:
        print(f"Run issue: {fatal_error}")

    print("\nOverall gate results:")
    for item in results:
        print(f"  {item['test_id']}: {item['overall_status']}")

    if quota_exhausted:
        print("Run stopped because of API quota exhaustion.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Evaluation could not start: {error}")
        raise
