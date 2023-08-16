import streamlit as st
from pyopenms import Residue, AASequence


def getFragmentMassesWithSeq(protein_seq, res_type):
    protein_length = protein_seq.size()
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
        prefix_mass = protein_seq.getPrefix(aa_index+1).getMonoWeight(prefix_ion_type, 1)  # charge 1 // + added_ptm_masses
        prefix_mass_list[aa_index] = prefix_mass

    # process suffix
    for aa_index in reversed(range(protein_length)):
        suffix_mass = protein_seq.getSuffix(aa_index+1).getMonoWeight(suffix_ion_type, 1)  # charge 1 // + added_ptm_masses
        suffix_mass_list[aa_index] = suffix_mass

    return prefix_mass_list, suffix_mass_list


@st.cache_data
def getFragmentDataFromSeq(sequence, modification_dict):
    protein = AASequence.fromString(sequence)

    # TODO: handling modifications
    # ox = ModificationsDB().getModification("Oxidation")
    # protein.setModification(43, ox)
    # print(protein)
    # print(protein.toUnmodifiedString())

    # calculating proteoform mass from sequence
    protein_mass = protein.getMonoWeight()

    out_object = {'sequence': list(sequence),
                  'theoretical_mass': protein_mass} #, 'fixed_modifications': modification_dict}
    # per ion type, calculate the possible fragment masses and save them in dictionary
    for ion_type in ['ax', 'by', 'cz']:
        # calculate fragment ion masses
        prefix_ions, suffix_ions = getFragmentMassesWithSeq(protein, ion_type)
        out_object['fragment_masses_%s' % ion_type[0]] = prefix_ions
        out_object['fragment_masses_%s' % ion_type[1]] = suffix_ions

    return out_object
