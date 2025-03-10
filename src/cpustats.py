import psutil
import time
from streamlit.delta_generator import DeltaGenerator
import streamlit as st

def monitor_cpu_ram_stats(cpu_ram_stats_placeholder: DeltaGenerator):
    with cpu_ram_stats_placeholder:
        ram_progress = 1 - psutil.virtual_memory().available / psutil.virtual_memory().total
        cpu_progress = psutil.cpu_percent() / 100
        ram_stats_column, cpu_stats_column = st.columns(2)

        ram_stats_column.text(f"Ram ({int(ram_progress * 100)}%)")
        ram_stats_column.progress(ram_progress)
        
        cpu_stats_column.text(f"CPU ({int(cpu_progress * 100)}%)")
        cpu_stats_column.progress(cpu_progress)
        
        time.sleep(1)