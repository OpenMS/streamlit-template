# test_my_math.py
import unittest
from urllib.request import urlretrieve

from src.simpleworkflow import generate_random_table
from src.mzmlfileworkflow import mzML_file_get_num_spectra

from pathlib import Path

class TestSimpleWorkflow(unittest.TestCase):
    def test_workflow(self):
        result = generate_random_table(2, 3).shape
        self.assertEqual(result, (2,3), "Expected dataframe shape.")

class TestComplexWorkflow(unittest.TestCase):
    def test_workflow(self):
        # load data from url
        urlretrieve("https://raw.githubusercontent.com/OpenMS/streamlit-template/main/example-data/mzML/Treatment.mzML", "testfile.mzML")
        result = mzML_file_get_num_spectra("testfile.mzML")
        Path("testfile.mzML").unlink()
        self.assertEqual(result, 786, "Expected dataframe shape.")

if __name__ == '__main__':
    unittest.main()
