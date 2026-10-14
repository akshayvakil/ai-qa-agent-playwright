
import json


class PlaywrightAgent:

    # Constructor: receive the existing SauceDemo Page Object.
    def __init__(self, saucedemo_page):

        # Store the Page Object for reuse in all test workflows.
        self.saucedemo = saucedemo_page

    # Main method called by the runner for each test case.
    def execute_test_case(self, test_case):

        # Read the test case information from the JSON dictionary.
        test_id = test_case["id"]
        title = test_case["title"]
        test_type = test_case["type"]

        # Print test details to the terminal.
        print(f"\nExecuting: {test_id}")
        print(f"Title: {title}")
        print(f"Type: {test_type}")

        # This agent currently supports UI test cases only.
        if test_type != "UI":
            raise NotImplementedError(
                f"Unsupported test type: {test_type}"
            )

        # Start each test at the SauceDemo login page.
        self.saucedemo.open()

        # Select the workflow for the current test ID.
        if test_id == "TC01":
            self._test_successful_login_and_add_to_cart()

        elif test_id == "TC02":
            self._test_add_to_cart_from_product_details()

        elif test_id == "TC03":
            self._test_product_persists_in_cart()

        elif test_id == "TC04":
            self._test_invalid_login()

        elif test_id == "TC05":
            self._test_locked_out_user()

        else:
            # Unknown test cases must not silently pass.
            raise NotImplementedError(
                f"Test case {test_id} is not implemented."
            )

        # This message appears only if the workflow completes
        # without raising an exception.
        print(f"{test_id} PASSED")

    # TC01: Login successfully and add the backpack from inventory.
    def _test_successful_login_and_add_to_cart(self):

        self.saucedemo.login(
            "standard_user",
            "secret_sauce"
        )

        # Verify that the inventory page is displayed.
        assert self.saucedemo.page_title.inner_text() == "Products"

        # Add the backpack from inventory.
        self.saucedemo.add_backpack()

        # Verify the cart badge and Remove button.
        assert self.saucedemo.cart_badge.inner_text() == "1"
        assert self.saucedemo.backpack_remove_button.is_visible()

    # TC02: Add the backpack from its product details page.
    def _test_add_to_cart_from_product_details(self):

        self.saucedemo.login(
            "standard_user",
            "secret_sauce"
        )

        # Verify that login succeeded.
        assert self.saucedemo.page_title.inner_text() == "Products"

        # Open the backpack details page.
        self.saucedemo.open_backpack_details()

        # Verify that the correct product details are displayed.
        assert (
            self.saucedemo.product_details_name.inner_text()
            == "Sauce Labs Backpack"
        )

        # IMPORTANT: use the details-page button, not the inventory button.
        self.saucedemo.add_backpack_from_details()

        # Verify that the product was added successfully.
        assert self.saucedemo.details_remove_button.is_visible()
        assert self.saucedemo.cart_badge.inner_text() == "1"

    # TC03: Verify that the product appears in the shopping cart.
    def _test_product_persists_in_cart(self):

        self.saucedemo.login(
            "standard_user",
            "secret_sauce"
        )

        # Add the backpack while still on the inventory page.
        self.saucedemo.add_backpack()

        # Navigate to the shopping cart.
        self.saucedemo.open_cart()

        # Verify that the cart page is displayed.
        assert self.saucedemo.page_title.inner_text() == "Your Cart"

        # Verify the product name and quantity.
        assert (
            self.saucedemo.cart_item_name.inner_text()
            == "Sauce Labs Backpack"
        )
        assert self.saucedemo.cart_quantity.inner_text() == "1"

        # Verify that a product price is displayed.
        assert self.saucedemo.cart_item_price.is_visible()

    # TC04: Verify that invalid credentials are rejected.
    def _test_invalid_login(self):

        self.saucedemo.login(
            "invalid_user",
            "wrong_password"
        )

        # Verify that the login error is displayed.
        assert self.saucedemo.login_error.is_visible()

        # Verify the expected invalid-credentials message.
        assert (
            "Username and password do not match"
            in self.saucedemo.login_error.inner_text()
        )

        # Verify that the user remains on the login screen.
        assert self.saucedemo.login_button.is_visible()

    # TC05: Verify that a locked-out user cannot log in.
    def _test_locked_out_user(self):

        self.saucedemo.login(
            "locked_out_user",
            "secret_sauce"
        )

        # Verify that an error message appears.
        assert self.saucedemo.login_error.is_visible()

        # Verify the specific locked-out-user message.
        assert (
            "Sorry, this user has been locked out."
            in self.saucedemo.login_error.inner_text()
        )

        # Verify that the login screen remains visible.
        assert self.saucedemo.login_button.is_visible()


# Helper function to load test cases from a JSON file.
def load_test_cases(file_path):

    # Open the JSON file for reading.
    with open(file_path, "r", encoding="utf-8") as file:

        # Convert JSON into Python dictionaries and lists.
        data = json.load(file)

    # Return the test cases stored in the JSON object.
    return data["test_cases"]
