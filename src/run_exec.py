# Example of running subprocess/executable e-g NuXL
import os
import streamlit as st
import subprocess
import threading
from ini2dec import *

######################## Take parameters values from tool config file (.ini) #################################

# Define the sections you want to extract
sections = [
    "missed_cleavages" #let suppose tool parameter missed cleavages
]

# path of .ini file (# placed in assets)
config_path = os.path.join(os.getcwd(), 'assets', 'exec.ini')

# take dictionary of parameters
exec_config=ini2dict(config_path, sections)

# (will give every section as 1 entry: 
# entry = {
           #"name": node_name,
           #"default": node_default,
           #"description": node_desc,
           #"restrictions": restrictions_list
           # })

# take all variables settings from config dictionary
# by create form take parameter values
# for example missed_cleavages
Missed_cleavages = str(st.number_input("Missed_cleavages",value=int(exec_config['missed_cleavages']['default']), help=exec_config['missed_cleavages']['description'] + " default: "+ exec_config['missed_cleavages']['default']))

##################################### Run subprocess ############################

#result dictionary to capture output of subprocess
result_dict = {}
result_dict["success"] = False
result_dict["log"] = " "

def run_subprocess(args, variables, result_dict):
    """
    run subprocess 

    Args:
        args: command with args
        variables: variable if any
        result_dict: contain success (success flag) and log (capture long log)
                     should contain result_dict["success"], result_dict["log"]

    Returns:
        None
    """
 
    # run subprocess and get every line of executable log in same time
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    stdout_ = []
    stderr_ = []

    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            #print every line of exec on page
            st.text(output.strip())
            #append line to store log
            stdout_.append(output.strip())

    while True:
        error = process.stderr.readline()
        if error == '' and process.poll() is not None:
            break
        if error:
            #print every line of exec on page even error
            st.error(error.strip())
            #append line to store log of error
            stderr_.append(error.strip())

    #check if process run successfully
    if process.returncode == 0:
        result_dict["success"] = True
        #save in to log all lines
        result_dict["log"] = " ".join(stdout_)
    else:
        result_dict["success"] = False
        #save in to log all lines even process cause error
        result_dict["log"] = " ".join(stderr_)

#create terminate flag from even function
terminate_flag = threading.Event()
terminate_flag.set()

#terminate subprocess by terminate flag
def terminate_subprocess():
    global terminate_flag
    terminate_flag.set()

# run analysis 
if st.button("Run-analysis"):

    # To terminate subprocess and clear form
    if st.button("Terminate/Clear"):
        #terminate subprocess
        terminate_subprocess()
        st.warning("Process terminated. The analysis may not be complete.")
        #reset page
        st.experimental_rerun() 

    #with st.spinner("Running analysis... Please wait until analysis done 😑"): #without status/ just spinner button
    with st.status("Running analysis... Please wait until analysis done 😑"):

        #If session state is local
        if st.session_state.location == "local":

            #If local executable path e-g bin 
            exec_command = os.path.join(os.getcwd(),'bin', "exec_name")

            #example of command, take variable e-g Missed_cleavages
            args = [exec_command, "-missed_cleavages", Missed_cleavages]

        #If session state is online/docker
        else:     

            #executable on path, example of command
            args = ["exec_name", "-missed_cleavages", Missed_cleavages]
      
        # Add any additional variables needed for the subprocess (if any)
        variables = []  

        #want to see the command values and argues
        message = f"Running '{' '.join(args)}'"
        st.code(message)

        #run subprocess command
        run_subprocess(args, variables, result_dict)

    #if run_subprocess success (no need if not success because error will show/display in run_subprocess command)
    if result_dict["success"]:

        # Save the log to a text file in the result_dir
        #log_file_path = result_dir / f"{protocol_name}_log.txt"
        #with open(log_file_path, "w") as log_file:
            #log_file.write(result_dict["log"])
        
        #do something probably display results etc
        pass