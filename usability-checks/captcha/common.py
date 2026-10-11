"""Shared constants and preprocessing for the captcha solver."""

import string

import numpy as np

LENGTH = 5
# captcha_control() replaces "0" with "A" and "O" with "B", so neither appears.
CHARSET = "".join(c for c in string.ascii_uppercase + string.digits if c not in "0O")
H, W = 64, 144


def preprocess(image):
    """Grey, small, and inverted with full contrast so the glyphs are bright."""
    from PIL import ImageOps

    return np.asarray(ImageOps.invert(ImageOps.autocontrast(image.convert("L").resize((W, H)))), np.uint8)


def decode(probs):
    """Greedy CTC decoding: best class per column, repeats merged, blanks dropped."""
    out, prev = [], None
    for k in probs.argmax(-1):
        if k != prev and k < len(CHARSET):
            out.append(CHARSET[k])
        prev = k
    return "".join(out)
