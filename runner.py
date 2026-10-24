
# Path helps us build file paths without hardcoding
# the full Windows directory everywhere.
from pathlib import Path

# json reads the test cases and writes the execution report.
import json

# datetime records when each test starts and finishes.
from datetime import datetime

# Playwright provides browser automation capabilities.
from playwright.sync_api import sync_playwright

# Allure model classes create individual test-result files.
from allure_commons.model2 import Label, Status, StatusDetails, TestResult
from allure_commons.utils import uuid4

# attr.asdict converts Allure model objects into JSON-serializable dicts.
from attr import asdict

# Import the agent and the helper function that reads test cases.
from agents.playwright_agent import PlaywrightAgent, load_test_cases

# Import the Page Object containing SauceDemo locators and actions.
from tests.ui.pages.saucedemo_page import SauceDemoPage

# Convert the JSON execution results into a readable HTML report.
from reports.generate_html_report import generate_html_report


# Resolve the directory containing runner.py.
PROJECT_ROOT = Path(__file__).resolve().parent

# Input JSON containing the generated test cases.
TEST_CASES_FILE = PROJECT_ROOT / "reports" / "generated_test_cases.json"

# Output JSON containing execution results.
REPORT_FILE = PROJECT_ROOT / "reports" / "execution_report.json"

# Allure stores raw test-result files in this directory.
ALLURE_RESULTS_DIR = PROJECT_ROOT / "allure-results"


def record_allure_result(
    test_case,
    status,
    start_time,
    end_time,
    error_message=None
):
    """Write one Allure-compatible result JSON file."""

    # Generate a unique identifier for this test result.
    result_uuid = str(uuid4())

    # Map the runner's status to the Allure status.
    allure_status = (
        Status.PASSED if status == "PASS" else Status.FAILED
    )

    # Build the test-result object.
    result = TestResult(
        uuid=result_uuid,
        name=str(
            test_case.get("title", test_case.get("id", "Unnamed test"))
        ),
        fullName=str(test_case.get("id", "UNKNOWN")),
        historyId=str(test_case.get("id", "UNKNOWN")),
        status=allure_status,
        start=int(start_time.timestamp() * 1000),
        stop=int(end_time.timestamp() * 1000),
        labels=[
            Label(name="framework", value="Playwright"),
            Label(name="language", value="Python"),
        ],
    )

    # Attach failure details when the test fails.
    if error_message:
        result.statusDetails = StatusDetails(
            message=str(error_message),
            trace=str(error_message),
            known=False,
            flaky=False,
        )

    # Convert the Allure attrs model into a dictionary.
    # Keep False values so status flags are not dropped.
    result_data = asdict(result, filter=lambda _, value: value or value is False)

    # Save one result file for this test case.
    result_file = ALLURE_RESULTS_DIR / f"{result_uuid}-result.json"

    with open(result_file, "w", encoding="utf-8") as output_file:
        json.dump(result_data, output_file, indent=4)


# Main function: coordinates test loading, execution and reporting.
def main():

    # Read all test cases from the input JSON file.
    test_cases = load_test_cases(TEST_CASES_FILE)

    # Select all loaded test cases for execution.
    selected_test_cases = test_cases

    # Create an empty list to store each test's execution result.
    execution_results = []

    # Create the Allure results directory.
    ALLURE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove old result JSON files so previous executions
    # are not mixed with this run.
    for old_result in ALLURE_RESULTS_DIR.glob("*-result.json"):
        old_result.unlink()

    # Display the number of test cases loaded and selected.
    print(f"Loaded {len(test_cases)} test cases.")
    print(f"Selected {len(selected_test_cases)} test case(s).")

    # Start the Playwright runtime.
    with sync_playwright() as p:

        # Launch the installed Google Chrome browser.
        # headless=False makes the browser window visible.
        browser = p.chromium.launch(
            channel="chrome",
            headless=True
        )

        try:
            # Create a new browser tab.
            page = browser.new_page()

            # Create the Page Object and provide the browser page.
            saucedemo_page = SauceDemoPage(page)

            # Create the agent and provide the Page Object.
            agent = PlaywrightAgent(saucedemo_page)

            # Execute each selected test case one at a time.
            for test_case in selected_test_cases:

                # Record the time before executing this test.
                start_time = datetime.now()

                try:
                    # Ask the agent to execute the appropriate workflow.
                    agent.execute_test_case(test_case)

                    # If no exception occurs, mark the test as passed.
                    status = "PASS"
                    error_message = None

                except Exception as error:
                    # Capture assertion failures and other execution errors.
                    # The loop continues to the next test case.
                    status = "FAIL"
                    error_message = str(error)

                    print(f'{test_case["id"]} FAILED: {error}')

                # Record the end time after the test completes or fails.
                end_time = datetime.now()

                # Calculate elapsed time in seconds.
                duration_seconds = round(
                    (end_time - start_time).total_seconds(),
                    2
                )

                # Record the test result in Allure.
                record_allure_result(
                    test_case=test_case,
                    status=status,
                    start_time=start_time,
                    end_time=end_time,
                    error_message=error_message,
                )

                # Add this test's result to the custom JSON report.
                execution_results.append({
                    "test_id": test_case["id"],
                    "title": test_case["title"],
                    "status": status,
                    "executed_at": start_time.isoformat(
                        timespec="seconds"
                    ),
                    "duration_seconds": duration_seconds,
                    "error": error_message
                })

        finally:
            # Always close Chrome, including when execution fails.
            browser.close()

    # Save all collected results to the output JSON file.
    with open(REPORT_FILE, "w", encoding="utf-8") as report_file:
        json.dump(execution_results, report_file, indent=4)

    # Count how many test results have PASS status.
    passed = sum(
        1 for result in execution_results
        if result["status"] == "PASS"
    )

    # Count how many test results have FAIL status.
    failed = sum(
        1 for result in execution_results
        if result["status"] == "FAIL"
    )

    # Display the final execution summary.
    print("\nExecution Summary")
    print("-----------------")
    print(f"Total: {len(execution_results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    # Display the location of the generated JSON report.
    print(f"\nExecution report saved to: {REPORT_FILE}")

    # Build the standalone custom HTML report.
    html_report = generate_html_report(REPORT_FILE)
    print(f"HTML report saved to: {html_report}")

    # Display the Allure results directory.
    print(f"Allure results saved to: {ALLURE_RESULTS_DIR}")


# Run main() only when this file is executed directly.
if __name__ == "__main__":
    main()
