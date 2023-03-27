import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
from pyopenms import *

from pyopenms import MSExperiment, MzMLFile
       
#@st.cache_data
def get_mass_table(annotated, deconvolved):
    annotated_exp = MSExperiment()
    deconvolved_exp = MSExperiment()
    #MzMLFile().load(str(Path(st.session_state["mzML-files"], annotated)), annotated_exp)
    #MzMLFile().load(str(Path(st.session_state["mzML-files"], deconvolved)), deconvolved_exp)
    MzMLFile().load(annotated, annotated_exp)
    MzMLFile().load(deconvolved, deconvolved_exp)

    tolerance = .0
    massoffset = .0
    chargemass = .0

    df = deconvolved_exp.get_df()
    
    peakIndices = []
    minCharges=[]
    maxCharges=[]
    minIsotopes=[]
    maxIsotopes=[]

    for spec in deconvolved_exp:
        mstr = spec.getMetaValue('DeconvMassInfo')
        #tol=10;massoffset=0.000000;chargemass=1.007276;peaks=1:1,0:1;1:1,0:1;1:1,0:1;1:1,0:1;2:2,0:3;2:2,1:5;
        # Split the string into key-value pairs
        input_pairs = mstr.split(';')
      
        # Create a dictionary to store the parsed values
        parsed_dict = {}

        # Parse the key-value pairs and store them in the dictionary
        for pair in input_pairs:
            if '=' in pair:
                key, value = pair.split('=')
                if key == 'peaks':
                    peaks_values = []                    
                    peak_values = value.split(',')
                    peaks_values.append([tuple(map(int, p.split(':'))) for p in peak_values])
                    parsed_dict[key] = peaks_values
                else:
                    parsed_dict[key] = float(value)
            else:
                peaks_values = []                    
                peak_values = value.split(',')
                parsed_dict['peaks'].append([tuple(map(int, p.split(':'))) for p in peak_values])
            
        tolerance = parsed_dict['tol']
        massoffset= parsed_dict['massoffset']
        chargemass= parsed_dict['chargemass']
        peaks = parsed_dict['peaks']

        minCharge=[]
        maxCharge=[]
        minIso=[]
        maxIso=[]

        for peakinfo in peaks:
            minCharge.append(peakinfo[0][0])
            maxCharge.append(peakinfo[0][1])
            minIso.append(peakinfo[1][0])
            maxIso.append(peakinfo[1][1])

        minCharges.append(minCharge)
        maxCharges.append(maxCharge)
        minIsotopes.append(minIso)
        maxIsotopes.append(maxIso)

    df['MinCharges'] = minCharges
    df['MaxCharges'] = maxCharges
    df['MinIsotopes'] = minIsotopes
    df['MaxIsotopes'] = maxIsotopes

    for spec in annotated_exp:
        mstr = spec.getMetaValue('DeconvMassPeakIndices')
        # Split the string into peak items
        peak_items = mstr.split(';')

        # Create a list to store the parsed peaks
        parsed_peaks = []

        # Parse the peak items and store them in the list
        for item in peak_items:
            if len(item) == 0:
                continue
            peak_values = item.split(':')
            peak_mass = float(peak_values[0])
            peak_ions = list(map(int, peak_values[1].split(',')))
            parsed_peaks.append((peak_mass, peak_ions))
            
        #[(1679.850836, [682, 696, 697]), ...

        indices = []
        for peakInfo in parsed_peaks:
            indices.append(peakInfo[1])

        peakIndices.append(indices)
    
    df['PeakIndex'] = peakIndices

    return df, tolerance,  massoffset, chargemass
    
def main():
    annotated = '/Users/kyowonjeong/FLASHDeconvOut/OT_Myoglobin_MS2_HCD_annotated.mzML'
    deconvolved = '/Users/kyowonjeong/FLASHDeconvOut/OT_Myoglobin_MS2_HCD_deconv.mzML'
    tmp = get_mass_table(annotated, deconvolved)
    print(tmp[0]['PeakIndex'])
if __name__ == "__main__":
    main()

    


