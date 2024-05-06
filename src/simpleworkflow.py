import time

import numpy as np
import pandas as pd
import streamlit as st


@st.cache_data
def generate_random_table(x, y):
    """Example for a cached table"""
    df = pd.DataFrame(np.random.randn(x, y))
    time.sleep(2)
    return df
