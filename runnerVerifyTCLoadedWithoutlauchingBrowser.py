
from pathlib import Path

from agents.playwright_agent import load_test_cases


PROJECT_ROOT = Path(__file__).resolve().parent
TEST_CASES_FILE = PROJECT_ROOT / "reports" / "generated_test_cases.json"


def main():
    test_cases = load_test_cases(TEST_CASES_FILE)

    # Start with TC01 only
    selected_test_cases = [
        tc for tc in test_cases if tc["id"] == "TC01"
    ]

    print(f"Loaded {len(test_cases)} test cases.")
    print(f"Selected {len(selected_test_cases)} test case(s).")

    for test_case in selected_test_cases:
        print(f'\n{test_case["id"]}: {test_case["title"]}')


if __name__ == "__main__":
    main()
