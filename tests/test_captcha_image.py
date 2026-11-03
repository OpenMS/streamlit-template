"""The captcha image is embedded in the page, not served from /media."""

import base64
import re

from src.common.captcha_ import captcha_image_html, height, width


def test_captcha_image_is_an_inline_png():
    html = captcha_image_html("AB12C")
    match = re.fullmatch(
        r'<img src="data:image/png;base64,([A-Za-z0-9+/=]+)" width="(\d+)" '
        r'height="(\d+)" alt="Captcha" style="[^"]*">',
        html,
    )
    assert match, html
    png = base64.b64decode(match.group(1))
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert (int(match.group(2)), int(match.group(3))) == (width, height)


def test_each_text_gets_its_own_image():
    assert captcha_image_html("AB12C") != captcha_image_html("XY34Z")
