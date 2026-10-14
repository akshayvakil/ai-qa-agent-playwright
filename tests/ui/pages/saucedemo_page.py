
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
        # Locator for the Add to Cart button on the inventory page.
        self.backpack_add_button = page.locator(
            "#add-to-cart-sauce-labs-backpack"
        )

        # Locator for the Remove button on the inventory page.
        self.backpack_remove_button = page.locator(
            "#remove-sauce-labs-backpack"
        )

        # Locator for the Add to Cart button on the product details page.
        # The parent container scopes the locator to that page section.
        self.details_add_button = page.locator(
            ".inventory_details_desc_container "
            "#add-to-cart-sauce-labs-backpack"
        )

        # Locator for the Remove button on the product details page.
        self.details_remove_button = page.locator(
            ".inventory_details_desc_container "
            "#remove-sauce-labs-backpack"
        )

        # Validation elements
        # Locator for the page title, such as "Products" or "Your Cart".
        self.page_title = page.locator(".title")

        # Locator for the shopping cart item count.
        self.cart_badge = page.locator(".shopping_cart_badge")

        # Locator for the login error message.
        self.login_error = page.locator("[data-test='error']")

        # Product details elements
        # Clicking the product title opens its details page.
        self.backpack_title_link = page.locator(
            "#item_4_title_link"
        )

        # Locator for the backpack name on the details page.
        self.product_details_name = page.locator(
            ".inventory_details_name"
        )

        # Shopping cart elements
        # Locator for the shopping cart icon/link in the header.
        self.cart_link = page.locator(".shopping_cart_link")

        # Locator for the product name displayed in the cart.
        self.cart_item_name = page.locator(".inventory_item_name")

        # Locator for the product quantity displayed in the cart.
        self.cart_quantity = page.locator(".cart_quantity")

        # Locator for the product price displayed in the cart.
        self.cart_item_price = page.locator(".inventory_item_price")

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

    # Define a reusable method to add the backpack from inventory.
    def add_backpack(self):

        # Click the Add to Cart button on the inventory page.
        self.backpack_add_button.click()

    # Define a reusable method to remove the backpack.
    def remove_backpack(self):

        # Click the Remove button on the inventory page.
        self.backpack_remove_button.click()

    # Open the backpack product details page.
    def open_backpack_details(self):

        # Click the backpack product title.
        self.backpack_title_link.click()

    # Add the backpack from the product details page.
    def add_backpack_from_details(self):

        # Use the locator scoped to the product details container.
        self.details_add_button.click()

    # Open the shopping cart.
    def open_cart(self):

        # Click the shopping cart icon in the page header.
        self.cart_link.click()
