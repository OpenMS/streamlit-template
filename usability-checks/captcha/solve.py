"""Read captcha PNGs (base64, one per stdin line) and print their text, one per line.

usage: python solve.py MODEL < images.b64
"""

import base64
import io
import os
import sys

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import numpy as np
import tensorflow as tf
from PIL import Image

from common import decode, preprocess

model = tf.keras.models.load_model(sys.argv[1], compile=False, safe_mode=False)
for line in sys.stdin:
    if not line.strip():
        continue
    x = preprocess(Image.open(io.BytesIO(base64.b64decode(line.strip()))))[None, ..., None]
    print(decode(model.predict(x, verbose=0)[0]), flush=True)
