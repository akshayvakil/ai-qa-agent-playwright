class SauceDemoPage:

    # __init__ is a special Python method called automatically
    # when we create a SauceDemoPage object.
    # Similar to a constructor in Java.
    def __init__(self, page):

        # self represents the current SauceDemoPage object.
        # Similar to "this" in Java.
        #
        # Store the Playwright Page object inside this Page Object.
        self.page = page

        # Login elements
        # page.locator() finds a UI element using a CSS selector.
        # Store each locator so we can reuse it in our methods.
        self.username = page.locator("#user-name")
        self.password = page.locator("#password")
        self.login_button = page.locator("#login-button")

        # Product elements
        # Locator for the Add to Cart button of the backpack.
        self.backpack_add_button = page.locator(
            "#add-to-cart-sauce-labs-backpack"
        )

        # Locator for the Remove button of the backpack.
        self.backpack_remove_button = page.locator(
            "#remove-sauce-labs-backpack"
        )

        # Validation elements
        # Locator for the "Products" page title.
        self.page_title = page.locator(".title")

        # Locator for the shopping cart item count.
        self.cart_badge = page.locator(".shopping_cart_badge")

        # Locator for the login error message.
        self.login_error = page.locator("[data-test='error']")

    # Define a Page Object method to open SauceDemo.
    # Similar to a public method in a Java Page Object.
    def open(self):

        # self.page refers to the Playwright Page object.
        # goto() navigates the browser to the given URL.
        self.page.goto("https://www.saucedemo.com/")

    # Define a reusable login method.
    # username and password are input parameters.
    def login(self, username, password):

        # Fill the username field with the supplied username.
        self.username.fill(username)

        # Fill the password field with the supplied password.
        self.password.fill(password)

        # Click the Login button.
        self.login_button.click()

    # Define a reusable method to add the backpack to the cart.
    def add_backpack(self):

        # Click the Add to Cart button.
        self.backpack_add_button.click()

    # Define a reusable method to remove the backpack from the cart.
    def remove_backpack(self):

        # Click the Remove button.
        self.backpack_remove_button.click()


        