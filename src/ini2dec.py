import xml.etree.ElementTree as ET

def ini2dict(path: str, sections: list):
    """
    ini file to dictionary.

    Args:
        path : path of ini file
        section: list of section, which will add into dictionary.

    Returns:
        config dictionary which stores provided section list
    """

    # Parse the XML configuration
    tree = ET.parse(path)
    root = tree.getroot()
    
    # Initialize an empty dictionary to store the extracted information
    config_dict = {}
    
    # dictionaries used to capture these variable from sections
    precursor_mass_tolerance_right = {}
    precursor_mass_tolerance_left = {}
    fragment_mass_tolerance_right = {}
    fragment_mass_tolerance_left = {}
    precursor_mass_tolerance_unit = {}
    fragment_mass_tolerance_unit = {}
    
    # Iterate through sections and store information in the dictionary
    for section_name in sections:

        for node in root.findall(f".//ITEMLIST[@name='{section_name}']") or root.findall(f".//ITEM[@name='{section_name}']"):
            node_name = str(node.get("name"))
            node_default = str(node.get("value"))
            node_desc = str(node.get("description"))
            node_rest = str(node.get("restrictions"))

            print(node_desc)

            # change the string representation to list of strings
            restrictions_list = node_rest.split(',') if node_rest else []
                
            entry = {
                "name": node_name,
                "default": node_default,
                "description": node_desc,
                "restrictions": restrictions_list
            }

            # because the mass tolerance same section in ini file, so need to validate from descriptions
            
            if "Precursor mass tolerance +" in node_desc:  
                entry["name"] = "precursor_mass_tolerance_right"
                precursor_mass_tolerance_right = entry
                print("Reached")
                
            
            if "Precursor mass tolerance -" in node_desc:  
                entry["name"] = "precursor_mass_tolerance_left"
                precursor_mass_tolerance_left = entry
                
            if "Fragment mass tolerance +" in node_desc: 
                entry["name"] = "fragment_mass_tolerance_right"
                fragment_mass_tolerance_right = entry

            if "Fragment mass tolerance -" in node_desc: 
                entry["name"] = "fragment_mass_tolerance_left"
                fragment_mass_tolerance_left = entry

            if "Unit of precursor mass tolerance" in node_desc:  
                entry["name"] = "precursor_mass_tolerance_unit"
                precursor_mass_tolerance_unit = entry
                
            if "Unit of fragment mass tolerance" in node_desc: 
                entry["name"] = "fragment_mass_tolerance_unit"
                fragment_mass_tolerance_unit = entry
                
        # Store the entry in the section dictionary
        config_dict[section_name] = entry

        # add mass tolerance dictionaries to config
        if "mass_tolerance_right" in section_name:
            config_dict["precursor_mass_tolerance_right"] = precursor_mass_tolerance_right     
            config_dict["fragment_mass_tolerance_right"] = fragment_mass_tolerance_right
        
        if "mass_tolerance_left" in section_name:
            config_dict["precursor_mass_tolerance_left"] = precursor_mass_tolerance_left
            config_dict["fragment_mass_tolerance_left"] = fragment_mass_tolerance_left
            
        # add mass tolerance unit dictionaries to config
        if "mass_tolerance_unit" in section_name:
            config_dict["precursor_mass_tolerance_unit"] = precursor_mass_tolerance_unit
            config_dict["fragment_mass_tolerance_unit"] = fragment_mass_tolerance_unit
        
    return config_dict

