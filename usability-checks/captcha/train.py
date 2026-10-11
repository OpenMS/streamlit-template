"""Train the solver for the OpenMS web apps' login captcha.

The apps draw a 5-character captcha with the `captcha` package
(src/common/captcha_.py: ImageCaptcha(width=400, height=180), characters from
A-Z and 0-9 with "0" replaced by "A" and "O" by "B"). Labelled examples come
from that same package, so the training data is unlimited and exact.

usage: python train.py [OUT_MODEL] [N_TRAIN]
"""

import multiprocessing as mp
import random
import string
import sys

import numpy as np

from common import CHARSET, H, LENGTH, W, decode, preprocess

OUT = sys.argv[1] if len(sys.argv) > 1 else "captcha-solver.keras"
N_TRAIN = int(sys.argv[2]) if len(sys.argv) > 2 else 200_000


def make(seed_count):
    seed, count = seed_count
    from captcha.image import ImageCaptcha

    rnd = random.Random(seed)
    gen = ImageCaptcha(width=400, height=180)
    xs = np.empty((count, H, W), np.uint8)
    ys = np.empty((count, LENGTH), np.uint8)
    for i in range(count):
        # Same alphabet and substitutions as captcha_control().
        text = "".join(rnd.choices(string.ascii_uppercase + string.digits, k=LENGTH)).replace("0", "A").replace("O", "B")
        xs[i] = preprocess(gen.generate_image(text))
        ys[i] = [CHARSET.index(c) for c in text]
    return xs, ys


def dataset(n, seed):
    chunks = [(seed + i, 5000) for i in range(n // 5000)]
    with mp.Pool() as pool:
        parts = pool.map(make, chunks)
    return np.concatenate([p[0] for p in parts]), np.concatenate([p[1] for p in parts])


def ctc_loss(y_true, y_pred):
    import tensorflow as tf

    batch = tf.shape(y_pred)[0]
    return tf.nn.ctc_loss(
        labels=tf.cast(y_true, tf.int32),
        logits=y_pred,
        label_length=tf.fill([batch], LENGTH),
        logit_length=tf.fill([batch], tf.shape(y_pred)[1]),
        logits_time_major=False,
        blank_index=len(CHARSET),
    )


def build():
    """Small CRNN: convolutions down to one column per time step, a GRU, CTC."""
    import tensorflow as tf
    from tensorflow.keras import layers

    inp = layers.Input((H, W, 1))
    x = layers.Rescaling(1 / 255)(inp)
    for f, pool in ((32, (2, 2)), (64, (2, 2)), (96, (2, 1)), (128, (2, 1))):
        x = layers.Conv2D(f, 3, padding="same", use_bias=False)(x)
        x = layers.BatchNormalization()(x)
        x = layers.ReLU()(x)
        x = layers.MaxPooling2D(pool)(x)
    # (H/16, W/4, 128) -> one feature vector per column.
    x = layers.Permute((2, 1, 3))(x)
    x = layers.Reshape((W // 4, (H // 16) * 128))(x)
    x = layers.Dense(128, activation="relu")(x)
    x = layers.Bidirectional(layers.GRU(96, return_sequences=True))(x)
    out = layers.Dense(len(CHARSET) + 1, name="ctc")(x)  # logits; last class is blank
    model = tf.keras.Model(inp, out)
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3), loss=ctc_loss)
    return model


if __name__ == "__main__":
    import tensorflow as tf

    xtr, ytr = dataset(N_TRAIN, 1)
    xva, yva = dataset(10_000, 10_000_000)
    print("data", xtr.shape, flush=True)
    model = build()
    model.fit(
        xtr[..., None],
        ytr,
        validation_data=(xva[..., None], yva),
        batch_size=128,
        epochs=int(sys.argv[3]) if len(sys.argv) > 3 else 12,
        callbacks=[tf.keras.callbacks.ReduceLROnPlateau(patience=3, factor=0.3), tf.keras.callbacks.ModelCheckpoint(OUT)],
        verbose=2,
    )
    pred = [decode(p) for p in model.predict(xva[..., None], verbose=0)]
    truth = ["".join(CHARSET[k] for k in y) for y in yva]
    print(f"whole-captcha accuracy on held-out examples: {np.mean([p == t for p, t in zip(pred, truth)]):.3f}")
