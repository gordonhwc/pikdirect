"""Project-wide constants for the PikPak share URL resolver."""

API_BASE_URL = "https://api-drive.mypikpak.net"
USER_BASE_URL = "https://user.mypikpak.net"

DEFAULT_AUTH_FILE_NAME = ".pikpak-auth.json"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_PARENT_ID = "root"

DEFAULT_CLIENT_ID = "YUMx5nI8ZU8Ap8pm"
DEFAULT_CLIENT_SECRET = "dbw2OtmVEeuUvIptb1Coyg"
DEFAULT_CLIENT_VERSION = "2.0.0"
DEFAULT_PACKAGE_NAME = "mypikpak.com"
DEFAULT_SDK_VERSION = "8.0.3"
CAPTCHA_REDIRECT_URI = "xlaccsdk01://xbase.cloud/callback?state=harbor"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

ALLOWED_SHARE_HOSTS = {
    "mypikpak.com",
    "www.mypikpak.com",
    "mypikpak.net",
    "www.mypikpak.net",
}

WEB_CAPTCHA_ALGORITHMS = [
    "C9qPpZLN8ucRTaTiUMWYS9cQvWOE",
    "+r6CQVxjzJV6LCV",
    "F",
    "pFJRC",
    "9WXYIDGrwTCz2OiVlgZa90qpECPD6olt",
    "/750aCr4lm/Sly/c",
    "RB+DT/gZCrbV",
    "",
    "CyLsf7hdkIRxRm215hl",
    "7xHvLi2tOYP0Y92b",
    "ZGTXXxu8E/MIWaEDB+Sm/",
    "1UI3",
    "E7fP5Pfijd+7K+t6Tg/NhuLq0eEUVChpJSkrKxpO",
    "ihtqpG6FMt65+Xk+tWUH2",
    "NhXXU9rg4XXdzo7u5o",
]

ERROR_CODE_ACCESS_TOKEN_EXPIRED = 4122
ERROR_CODE_ACCESS_TOKEN_INVALID = 4121
ERROR_CODE_UNAUTHORIZED = 16
ERROR_CODE_CAPTCHA_TOKEN_EXPIRED = 9
ERROR_CODE_TOO_MANY_REQUESTS = 10
ERROR_CODE_REFRESH_TOKEN_INVALID = 4126
