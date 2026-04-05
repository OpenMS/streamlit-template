"""
Example workflow demonstrating the use of the same TOPP tool multiple times
with different configurations using tool_instance_name parameter.

This example shows how to use IDFilter twice in a DDA-TMT workflow:
1. First with strict filtering (PSM FDR 0.01)
2. Then with lenient filtering (PSM FDR 0.05)
"""

import streamlit as st
from src.workflow.WorkflowManager import WorkflowManager
from pathlib import Path


class MultipleToolInstancesExample(WorkflowManager):
    """Example workflow showing how to use the same tool multiple times."""
    
    def __init__(self) -> None:
        super().__init__("Multiple Tool Instances Example", st.session_state["workspace"])

    def upload(self) -> None:
        """Upload idXML files for filtering."""
        self.ui.upload_widget(
            key="idXML-files",
            name="Identification files",
            file_types="idXML",
        )

    @st.fragment
    def configure(self) -> None:
        """Configure parameters for two IDFilter instances."""
        # Select input files
        self.ui.select_input_file("idXML-files", multiple=True)
        
        # Create tabs for two different filtering stages
        t = st.tabs(["**Strict Filtering**", "**Lenient Filtering**"])
        
        with t[0]:
            st.info("First filtering stage with strict FDR threshold")
            # First instance of IDFilter with custom defaults for strict filtering
            self.ui.input_TOPP(
                "IDFilter",
                tool_instance_name="IDFilter-strict",
                custom_defaults={"score:pep": 0.01},  # Strict FDR threshold
            )
        
        with t[1]:
            st.info("Second filtering stage with lenient FDR threshold")
            # Second instance of IDFilter with custom defaults for lenient filtering
            self.ui.input_TOPP(
                "IDFilter",
                tool_instance_name="IDFilter-lenient",
                custom_defaults={"score:pep": 0.05},  # Lenient FDR threshold
            )

    def execution(self) -> None:
        """Execute workflow with two different IDFilter instances."""
        # Check if files are selected
        if not self.params["idXML-files"]:
            self.logger.log("ERROR: No idXML files selected.")
            return
        
        # Get input files
        in_files = self.file_manager.get_files(self.params["idXML-files"])
        self.logger.log(f"Processing {len(in_files)} identification files")
        
        # First filtering stage: Strict filtering
        self.logger.log("Running strict filtering (FDR 0.01)...")
        out_strict = self.file_manager.get_files(
            in_files, "idXML", "strict-filtering"
        )
        self.executor.run_topp(
            "IDFilter",
            input_output={"in": in_files, "out": out_strict},
            tool_instance_name="IDFilter-strict"  # Use strict instance parameters
        )
        
        # Second filtering stage: Lenient filtering
        self.logger.log("Running lenient filtering (FDR 0.05)...")
        out_lenient = self.file_manager.get_files(
            in_files, "idXML", "lenient-filtering"
        )
        self.executor.run_topp(
            "IDFilter",
            input_output={"in": in_files, "out": out_lenient},
            tool_instance_name="IDFilter-lenient"  # Use lenient instance parameters
        )
        
        self.logger.log("Filtering completed!")

    @st.fragment
    def results(self) -> None:
        """Display results."""
        strict_dir = Path(self.workflow_dir, "results", "strict-filtering")
        lenient_dir = Path(self.workflow_dir, "results", "lenient-filtering")
        
        if strict_dir.exists() and lenient_dir.exists():
            st.success("Both filtering stages completed successfully!")
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Strict Filtering Results")
                strict_files = list(strict_dir.glob("*.idXML"))
                st.info(f"Files created: {len(strict_files)}")
                for f in strict_files:
                    st.write(f"- {f.name}")
            
            with col2:
                st.subheader("Lenient Filtering Results")
                lenient_files = list(lenient_dir.glob("*.idXML"))
                st.info(f"Files created: {len(lenient_files)}")
                for f in lenient_files:
                    st.write(f"- {f.name}")
        else:
            st.warning("No results yet. Please run the workflow first.")
