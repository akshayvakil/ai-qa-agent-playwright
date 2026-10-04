import pytest
from playwright.sync_api import sync_playwright

from tests.ui.pages.saucedemo_page import SauceDemoPage

# read code explaination below 


@pytest.fixture
def saucedemo():
    # Start Playwright
    with sync_playwright() as p:

        # Launch installed Chrome
        browser = p.chromium.launch(
            channel="chrome",
            headless=False
        )

        # Create browser page actuall one tab in browser
        page = browser.new_page()

        # Create SauceDemo Page Object, New tabe created in page varaible is given to page objects 
        saucedemo_page = SauceDemoPage(page)

        # Open application open methods creted in page object saucedemo.py
        saucedemo_page.open() 

        yield saucedemo_page # gives the Page Object to the test; after test finishes, browser.close() closes Chrome.

        # Close browser
        browser.close()


def test_saucedemo_login_and_add_product(saucedemo):
    saucedemo.login("standard_user", "secret_sauce")

    # Verify Products page
    assert saucedemo.page_title.inner_text() == "Products"

    # Add product
    saucedemo.add_backpack()

    # Verify cart
    assert saucedemo.cart_badge.inner_text() == "1"


def test_saucedemo_invalid_login(saucedemo):
    saucedemo.login("invalid_user", "wrong_password")

    # Verify login error
    assert "Username and password do not match" in (
        saucedemo.login_error.inner_text()
    )


def test_saucedemo_add_and_remove_product(saucedemo):
    saucedemo.login("standard_user", "secret_sauce")

    # Add product
    saucedemo.add_backpack()

    # Verify product was added
    assert saucedemo.cart_badge.inner_text() == "1"

    # Remove product
    saucedemo.remove_backpack()

    # Verify cart is empty
    assert saucedemo.cart_badge.count() == 0


    # Think of a pytest fixture as a reusable @BeforeMethod + @AfterMethod in Java/TestNG.

# @pytest.fixture → tells pytest: “Run this setup before the test.”
# In our project, it starts Playwright, launches Chrome, creates the page, and opens SauceDemo.
# yield page → gives that ready-to-use page to our test.
# After the test, the fixture closes the browser — similar to @AfterMethod.
# So instead of repeating browser setup in every test, we write it once and reuse it.

# Java/TestNG comparison:

# @BeforeMethod → setup browser/page
# @Test         → test scenario
# @AfterMethod  → close browser

# Our Python:

# @pytest.fixture → setup + yield + cleanup
# def test_...    → test scenario

# How is browser managed 

# What each object means
#1.  p → Playwright object; it gives us access to Chromium, Firefox, WebKit, etc.
# 2. browser → actual Chrome browser launched using p.chromium.launch().
# 3. page → one browser tab created using browser.new_page().
# 4. SauceDemoPage(page) → Page Object receives page and uses it for locators/actions.
# 5. yield → gives the Page Object to the test; after test finishes, browser.close() closes Chrome.


# ============================================================
# REVISION NOTES
# ============================================================
#
# PYTHON:
# class, __init__, self, methods, import
#__init__.py
# PLAYWRIGHT:
# page, locator, fill(), click(), goto(), inner_text()
#
# POM:
# Page Object contains locators + UI actions
# Test file contains test scenarios + assertions
#
# PYTEST:
# Fixture creates and provides the Page Object to tests
#
# INTERVIEW:
# "I separate UI locators and actions from test scenarios
# using the Page Object Model."
# ============================================================