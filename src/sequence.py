import streamlit as st
from pyopenms import Residue, AASequence, ModificationsDB


fixed_mod_cysteine = {'No modification': 0,
                      'Carbamidomethyl (+57)': 57.021464,
                      'Carboxymethyl (+58)': 58.005479,
                      'Xlink:Disulfide (-1 per C)': -1.007825,
                      }
fixed_mod_methionine = {'No modification': 0,
                        'L-methionine sulfoxide (+16)': 15.994915,
                        'L-methionine sulfone (+32)': 31.989829
                        }


def getFragmentMassesWithSeq(protein, res_type):
    protein_length = protein.size()
    prefix_mass_list = [.0] * protein_length
    suffix_mass_list = [.0] * protein_length

    # get type for fragments
    prefix_ion_type, suffix_ion_type = None, None
    if res_type == 'ax':
        prefix_ion_type = Residue.ResidueType.AIon
        suffix_ion_type = Residue.ResidueType.XIon
    elif res_type == 'by':
        prefix_ion_type = Residue.ResidueType.BIon
        suffix_ion_type = Residue.ResidueType.YIon
    elif res_type == 'cz':
        prefix_ion_type = Residue.ResidueType.CIon
        suffix_ion_type = Residue.ResidueType.ZIon

    # process prefix
    for aa_index in range(protein_length):
        prefix_mass = protein.getPrefix(aa_index+1).getMonoWeight(prefix_ion_type, 0)  # + added_ptm_masses
        prefix_mass_list[aa_index] = prefix_mass

    # process suffix
    for aa_index in reversed(range(protein_length)):
        suffix_mass = protein.getSuffix(aa_index+1).getMonoWeight(suffix_ion_type, 0)  # + added_ptm_masses
        suffix_mass_list[aa_index] = suffix_mass

    return prefix_mass_list, suffix_mass_list


def setFixedModification(protein):
    fixed_mod_dict = {}

    # fixed modification on cysteine
    if 'fixed_mod_cysteine' in st.session_state and st.session_state['fixed_mod_cysteine']:
        mod_mass = fixed_mod_cysteine[st.session_state['fixed_mod_cysteine']]
        mod_indices = []
        for index, aa in enumerate(protein.toString()):
            if aa != 'C':
                continue
            # to remove warning, setModificationByDiffMonoMass was not used.
            mod = ModificationsDB().getBestModificationByDiffMonoMass(mod_mass, 0.001, 'C', 0)
            protein.setModification(index, mod)
            mod_indices.append(index)
        if mod_indices:
            fixed_mod_dict['C'] = mod_indices

    # fixed modification on methionine
    if 'fixed_mod_methionine' in st.session_state and st.session_state['fixed_mod_methionine']:
        mod_mass = fixed_mod_methionine[st.session_state['fixed_mod_methionine']]
        mod_indices = []
        for index, aa in enumerate(protein.toUnmodifiedString()):
            if aa != 'M':
                continue
                # to remove warning, setModificationByDiffMonoMass was not used.
            mod = ModificationsDB().getBestModificationByDiffMonoMass(mod_mass, 0.001, 'M', 0)
            protein.setModification(index, mod)
            mod_indices.append(index)
        if mod_indices:
            fixed_mod_dict['M'] = mod_indices

    return protein, fixed_mod_dict


@st.cache_data
def getFragmentDataFromSeq(sequence):
    protein = AASequence.fromString(sequence)
    protein, fixed_mod_dict = setFixedModification(protein)  # handling fixed modifications

    # calculating proteoform mass from sequence
    protein_mass = protein.getMonoWeight()

    out_object = {'sequence': list(sequence),
                  'theoretical_mass': protein_mass, 'fixed_modifications': fixed_mod_dict}
    # per ion type, calculate the possible fragment masses and save them in dictionary
    for ion_type in ['ax', 'by', 'cz']:
        # calculate fragment ion masses
        prefix_ions, suffix_ions = getFragmentMassesWithSeq(protein, ion_type)
        out_object['fragment_masses_%s' % ion_type[0]] = prefix_ions
        out_object['fragment_masses_%s' % ion_type[1]] = suffix_ions

    return out_object
