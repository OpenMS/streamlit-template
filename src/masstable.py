import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go
import plotly.express as px
from pyopenms import *
from pyopenms import MSExperiment, MzMLFile
from pyopenms import Constants
import time
@st.cache_data
def parseFLASHDeconvOutput(annotated, deconvolved):
    annotated_exp = MSExperiment()
    deconvolved_exp = MSExperiment()
    MzMLFile().load(str(Path(st.session_state["anno-mzMLs"], annotated)), annotated_exp)
    MzMLFile().load(str(deconvolved), deconvolved_exp)
    #MzMLFile().load(annotated, annotated_exp)
    #MzMLFile().load(deconvolved, deconvolved_exp)
    tolerance = .0
    massoffset = .0
    chargemass = .0

    df = deconvolved_exp.get_df()
    annotateddf = annotated_exp.get_df()
    allPeaks = []
    signalPeaks = []
    noisyPeaks = []
    minCharges=[]
    maxCharges=[]
    minIsotopes=[]
    maxIsotopes=[]
    msLevels=[]
    precursorMasses=[]
    scans=[]

    for sindex, spec in enumerate(deconvolved_exp):
        aspec = annotated_exp[sindex]
        spec.sortByPosition()
        aspec.sortByPosition()
        
        mstr = spec.getMetaValue('DeconvMassInfo')
        #tol=10;massoffset=0.000000;chargemass=1.007276;peaks=1:1,0:1;1:1,0:1;1:1,0:1;1:1,0:1;2:2,0:3;2:2,1:5;
        # Split the string into key-value pairs
        input_pairs = mstr.split(';')
      
        # Create a dictionary to store the parsed values
        parsed_dict = {}

        # Parse the key-value pairs and store them in the dictionary
        for pair in input_pairs:
            if len(pair) == 0:
                continue
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
                peak_values = pair.split(',')
                parsed_dict['peaks'].append([tuple(map(int, p.split(':'))) for p in peak_values])
            
        tolerance = parsed_dict['tol']
        massoffset= parsed_dict['massoffset']
        chargemass= parsed_dict['chargemass']
        peaks = parsed_dict['peaks']

        minCharge=[]
        maxCharge=[]
        minIso=[]
        maxIso=[]

        allSpecPeaks = []
        for index, peakinfo in enumerate(peaks):
            minCharge.append(peakinfo[0][0])
            maxCharge.append(peakinfo[0][1])
            minIso.append(peakinfo[1][0])
            maxIso.append(peakinfo[1][1])
            mass = spec[index].getMZ()

            masspeaks = []
            for z in range(minCharge[-1], maxCharge[-1] + 1):
                minmz = (mass - 10.0)/z
                maxmz = (mass + 10.0 + maxIso[-1] * Constants.C13C12_MASSDIFF_U)/z
                minIndex = aspec.findNearest(minmz)
                for i in range(minIndex, aspec.size()):
                    if aspec[i].getMZ() > maxmz:
                        break
                    masspeaks.append([i, aspec[i].getMZ(), aspec[i].getIntensity()])
            allSpecPeaks.append(masspeaks)
        
        allPeaks.append(allSpecPeaks)
        minCharges.append(minCharge)
        maxCharges.append(maxCharge)
        minIsotopes.append(minIso)
        maxIsotopes.append(maxIso)

    df['MinCharges'] = minCharges
    df['MaxCharges'] = maxCharges
    df['MinIsotopes'] = minIsotopes
    df['MaxIsotopes'] = maxIsotopes

    for sindex, spec in enumerate(annotated_exp):
        mstr = spec.getMetaValue('DeconvMassPeakIndices')
        # Split the string into peak items
        peak_items = mstr.split(';')
        sourcefiles = annotated_exp.getSourceFiles();
        scan_number = SpectrumLookup().extractScanNumber(spec.getNativeID(), sourcefiles[0].getNativeIDTypeAccession()) if sourcefiles else -1
        scans.append(scan_number)
        # Create a list to store the parsed peaks
        parsed_peaks = []
        
        # Parse the peak items and store them in the list
        for item in peak_items:
            if len(item) == 0:
                continue
            peak_values = item.split(':')
            peak_mass = float(peak_values[0])
            peak_infos = list(map(int, peak_values[1].split(',')))
            parsed_peaks.append([peak_mass, peak_infos])
            
        specPeaks = allPeaks[sindex]        
        specnpeaks=[]
        specspeaks=[]
        for index, parsed_peak in enumerate(parsed_peaks): # for each mass
            massPeaks = specPeaks[index]
            sigindices = parsed_peak[1] # intersect this with massPeaks[0]s
            sigindicesset = set(sigindices)
            npeaks=[]
            speaks=[]
            for massPeak in massPeaks:
                pindex = massPeak[0]
                if pindex in sigindicesset:
                    massPeak.append(round(parsed_peak[0]/massPeak[1]))    
                    speaks.append(massPeak)                    
                else:
                    massPeak.append(round(parsed_peak[0]/massPeak[1]))
                    npeaks.append(massPeak)
                    
            
            if len(sigindices) != len(speaks):
                print("*")
                print(sigindices)
                for si in sigindices:
                    print(si, spec[si].getMZ())
                print(speaks)
                print(npeaks)
            specspeaks.append(speaks)
            specnpeaks.append(npeaks)
        signalPeaks.append(specspeaks)
        noisyPeaks.append(specnpeaks)
        msLevels.append(spec.getMSLevel())

    df['SignalPeaks'] = signalPeaks
    df['NoisyPeaks'] = noisyPeaks
    df['MSLevel'] = msLevels
    df['Scan'] = scans
    return df, annotateddf, tolerance,  massoffset, chargemass

@st.cache_data
def getSpectraTableDF(deconv_df: pd.DataFrame):
    out_df = deconv_df[['Scan', 'MSLevel', 'RT']]
    out_df['#Masses'] = [len(ele) for ele in deconv_df['MinCharges']]
    out_df.reset_index(inplace=True)
    return out_df

@st.cache_data
def getMassTableDF(spec: pd.Series):
    mass_df = pd.DataFrame({'Mono mass': spec['mzarray'],
                            'Sum intensity': spec['intarray'],
                            'Min charge': spec['MinCharges'],
                            'Max charge': spec['MaxCharges'],
                            'Min isotope': spec['MinIsotopes'],
                            'Max isotope': spec['MaxIsotopes'],
                            })
    mass_df.reset_index(inplace=True)
    return mass_df

@st.cache_data
def getMassSignalDF(spec: pd.Series):
    mass_signal_df = pd.DataFrame({'Mono mass': spec['mzarray'],
                                   'Signal peaks': spec['SignalPeaks'],
                                   'Noisy peaks': spec['NoisyPeaks'],
                                   })
    return mass_signal_df

@st.cache_data
def getMSSignalDF(anno_df: pd.DataFrame, point_num_cutoff=1000000):
    ints = np.concatenate([anno_df.loc[index, "intarray"] for index in anno_df.index])
    mzs = np.concatenate([anno_df.loc[index, "mzarray"] for index in anno_df.index])
    rts = np.concatenate(
        [
            np.full(len(anno_df.loc[index, "mzarray"]), anno_df.loc[index, "RT"])
            for index in anno_df.index
        ]
    )

    ms_df = pd.DataFrame({'mass': mzs, 'rt': rts, 'intensity': ints})
    ms_df.dropna(subset=['intensity'], inplace=True) # remove Nan
    ms_df = ms_df[ms_df['intensity']>0]
    if len(ms_df) > point_num_cutoff:
        ms_df.sort_values(by='intensity', inplace=True, ascending=False)
        ms_df = ms_df.iloc[:point_num_cutoff]
    ms_df.sort_values(by='intensity', inplace=True)
    return ms_df
