import requests

# use commands pytest -v and pytest

BASE_URL = "https://jsonplaceholder.typicode.com"


def test_get_post():
    # Hit GET request to retrieve a post
    response = requests.get(f"{BASE_URL}/posts/1") 

    # f means f-string (formatted string) — it lets you insert variables directly inside a string inside " " using {}.
    # name = "Akshay" 
    # message = f"Hello {name}"
    # # Result: "Hello Akshay"

    # Validate HTTP status code
    assert response.status_code == 200 # refer  to use response variable in bottom

    # Convert JSON response into Python dictionary
    data = response.json()

    # Validate response data
    assert data["id"] == 1
    assert "title" in data
    assert "body" in data


def test_create_post():
    # Python dictionary used as JSON request payload
    payload = {
        "title": "AI QA Agent Test",
        "body": "Testing API automation with Python",
        "userId": 1
    }

    # POST request to create a new resource
    response = requests.post(
        f"{BASE_URL}/posts",
        json=payload
    )

    # 201 = resource created successfully
    assert response.status_code == 201

    # Convert JSON response into Python dictionary
    data = response.json()

    # Validate returned response against request payload
    assert data["title"] == payload["title"]
    assert data["body"] == payload["body"]
    assert data["userId"] == payload["userId"]


# ============================================================
# REVISION NOTES
# ============================================================
#
# PYTHON:
# import, variables, constants, def/function, dictionary,
# methods, f-string, keyword arguments, assert
#
# PYTEST:
# test_ prefix, test discovery, assertions, test execution
#
# API:
# GET, POST, HTTP status codes, JSON request/response,
# request payload, response validation
#
# INTERVIEW:
# "I use pytest + requests for REST API automation.
# I validate both HTTP status codes and response data."
# ============================================================


# How to use response variable 
# response.status_code     # HTTP status, e.g. 200
# response.json()          # JSON response as Python dictionary/list
# response.text            # Response body as text
# response.headers         # Response headers
# response.url             # Actual URL called
# response.cookies         # Cookies returned by server
# response.content         # Response body as bytes
# response.ok              # True if status is generally successful
# response.reason          # Status reason, e.g. "OK"

# coparison with java 
# Response response = given()
#     .when()
#     .get("/posts/1");

# Assert.assertEquals(response.getStatusCode(), 200);

# What is pytest 
# Pytest will automatically:

# Find test files such as test_*.py
# Find functions such as test_*()
# Execute them
# Report PASSED / FAILED