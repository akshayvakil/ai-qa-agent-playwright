
# Path helps us build file paths without hardcoding
# the full Windows directory everywhere.
from pathlib import Path

# json reads the test cases and writes the execution report.
import json

# datetime records when each test starts and finishes.
from datetime import datetime

# Playwright provides browser automation capabilities.
from playwright.sync_api import sync_playwright

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


# Main function: coordinates test loading, execution and reporting.
def main():

    # Read all test cases from the input JSON file.
    test_cases = load_test_cases(TEST_CASES_FILE)

    # Select all loaded test cases for execution.
    # Previously, this filtered the list to TC01 only.
    selected_test_cases = test_cases

    # Create an empty list to store each test's execution result.
    execution_results = []

    # Display the number of test cases loaded and selected.
    print(f"Loaded {len(test_cases)} test cases.")
    print(f"Selected {len(selected_test_cases)} test case(s).")

    # Start the Playwright runtime.
    with sync_playwright() as p:

        # Launch the installed Google Chrome browser.
        # headless=False makes the browser window visible.
        browser = p.chromium.launch(
            channel="chrome",
            headless=False
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

                    print(
                        f'{test_case["id"]} FAILED: {error}'
                    )

                # Record the end time after this test completes or fails.
                end_time = datetime.now()

                # Calculate elapsed time in seconds.
                # Round the value to two decimal places.
                duration_seconds = round(
                    (end_time - start_time).total_seconds(),
                    2
                )

                # Add this test's result to the report data.
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
            # Always close Chrome, including when execution encounters
            # an unexpected error outside an individual test case.
            browser.close()

    # Save all collected results to the output JSON file.
    # The file is created if it does not exist.
    # If it exists, its previous contents are overwritten.
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

    # Display the location of the generated report.
    print(f"\nExecution report saved to: {REPORT_FILE}")

    # Build a standalone HTML report from the JSON results.
    html_report = generate_html_report(REPORT_FILE)
    print(f"HTML report saved to: {html_report}")


# Run main() only when this file is executed directly.
# Importing runner.py from another Python module will not
# automatically start test execution.
if __name__ == "__main__":
    main()
