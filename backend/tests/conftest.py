import os

# Never let a test reach real AWS.
os.environ.update({
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
    "AWS_SESSION_TOKEN": "testing",
    "AWS_DEFAULT_REGION": "us-east-1",
    "ALLOW_USER_HEADER": "true",  # tests act as seeded users without logging in
})
