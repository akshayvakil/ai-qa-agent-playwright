import json


class PlaywrightAgent:

    def __init__(self, saucedemo_page):
        """
        Receive the existing SauceDemo Page Object.
        """
        self.saucedemo = saucedemo_page

    def execute_test_case(self, test_case):
        """
        Execute one AI-generated UI test case.
        """

        test_id = test_case["id"]
        title = test_case["title"]
        test_type = test_case["type"]

        print(f"\nExecuting: {test_id}")
        print(f"Title: {title}")
        print(f"Type: {test_type}")

        # Only UI test cases should be handled
        # by the Playwright Agent.
        if test_type != "UI":
            print("Skipping because this is not a UI test case.")
            return

        # Execute the known SauceDemo scenario.
        #
        # The AI generated the test case,
        # but our Page Object performs the actual UI actions.
        self.saucedemo.login(
            "standard_user",
            "secret_sauce"
        )

        self.saucedemo.add_backpack()

        # Validate expected result
        assert self.saucedemo.page_title.inner_text() == "Products"
        assert self.saucedemo.cart_badge.inner_text() == "1"

        print(f"{test_id} PASSED")


def load_test_cases(file_path):
    """
    Read AI-generated test cases from JSON.
    """

    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)