# Take parameters values from tool config file (.ini)
# Define the sections you want to extract
# sections = ["missed_cleavages"]#let suppose we extract tool parameter: missed cleavages

# path of .ini file (# placed executable .ini file in assets)
# config_path = os.path.join(os.getcwd(), 'assets', 'exec.ini')

# take dictionary of parameters
# exec_config=ini2dict(config_path, sections)

# (will give every section as 1 entry:
# entry = {
# "name": node_name,
# "default": node_default,
# "description": node_desc,
# "restrictions": restrictions_list
# })

# take all variables settings from config dictionary
# by create form take parameter values
# for example missed_cleavages
# Missed_cleavages = str(st.number_input("Missed_cleavages",value=int(exec_config['missed_cleavages']['default']), help=exec_config['missed_cleavages']['description'] + " default: "+ exec_config['missed_cleavages']['default']))

import xml.etree.ElementTree as ET


def ini2dict(path: str, sections: list):
    """Converts a OpenMS ini file to dictionary."""
    # Parse the XML configuration
    tree = ET.parse(path)
    root = tree.getroot()

    # Initialize an empty dictionary to store the extracted information
    config_dict = {}

    # Iterate through sections and store information in the dictionary
    for section_name in sections:
        for node in root.findall(
            f".//ITEMLIST[@name='{section_name}']"
        ) or root.findall(f".//ITEM[@name='{section_name}']"):
            # can adapt depends on tool
            node_name = str(node.get("name"))
            node_default = str(node.get("value"))
            node_desc = str(node.get("description"))
            node_rest = str(node.get("restrictions"))

            # generate list
            restrictions_list = node_rest.split(",") if node_rest else []

            entry = {
                "name": node_name,
                "default": node_default,
                "description": node_desc,
                "restrictions": restrictions_list,
            }

        # Store the entry in the section dictionary
        config_dict[section_name] = entry

    return config_dict
