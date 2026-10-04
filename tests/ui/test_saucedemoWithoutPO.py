from playwright.sync_api import sync_playwright


def test_saucedemo_login_and_add_product():
    with sync_playwright() as p: 

       #  with sync_playwright() as p: MEANS
    # Start Playwright and store the Playwright object in variable p
    # p is used to access browsers such as Chromium, Firefox and WebKit

        # Launch installed Chrome
        browser = p.chromium.launch(
            channel="chrome",
            headless=False
        )

        page = browser.new_page()

        # Open SauceDemo
        page.goto("https://www.saucedemo.com/")

        # Login
        page.locator("#user-name").fill("standard_user")
        page.locator("#password").fill("secret_sauce")
        page.locator("#login-button").click()

        # Verify Products page
        assert page.locator(".title").inner_text() == "Products"

        # Add product to cart
        page.locator("#add-to-cart-sauce-labs-backpack").click()

        # Verify cart contains one product
        assert page.locator(".shopping_cart_badge").inner_text() == "1"

        browser.close()


def test_saucedemo_invalid_login():
    with sync_playwright() as p:

        # Launch installed Chrome
        browser = p.chromium.launch(
            channel="chrome",
            headless=False
        )

        page = browser.new_page()

        # Open SauceDemo
        page.goto("https://www.saucedemo.com/")

        # Enter invalid credentials
        page.locator("#user-name").fill("invalid_user")
        page.locator("#password").fill("wrong_password")
        page.locator("#login-button").click()

        # Verify login error
        error_message = page.locator("[data-test='error']").inner_text()

        assert "Username and password do not match" in error_message

        browser.close()


def test_saucedemo_add_and_remove_product():
    with sync_playwright() as p:

        # Launch installed Chrome
        browser = p.chromium.launch(
            channel="chrome",
            headless=False
        )

        page = browser.new_page()

        # Open SauceDemo
        page.goto("https://www.saucedemo.com/")

        # Login
        page.locator("#user-name").fill("standard_user")
        page.locator("#password").fill("secret_sauce")
        page.locator("#login-button").click()

        # Add product
        page.locator("#add-to-cart-sauce-labs-backpack").click()

        # Verify product was added
        assert page.locator(".shopping_cart_badge").inner_text() == "1"

        # Remove product
        page.locator("#remove-sauce-labs-backpack").click()

        # Verify cart is empty
        assert page.locator(".shopping_cart_badge").count() == 0

        browser.close()


# ============================================================
# REVISION NOTES
# ============================================================
#
# PYTHON:
# import, def, with, variables, methods, indentation
#
# PLAYWRIGHT:
# browser, page, locator, goto(), fill(), click(), inner_text()
#
# QA:
# Positive login, negative login, add/remove product
#
# INTERVIEW:
# "I created positive and negative UI scenarios using
# Playwright with Python and validated user actions and
# business outcomes."
# ============================================================