import unittest
from src.simpleworkflow import generate_random_table

class TestSimpleWorkflow(unittest.TestCase):
    def test_generate_random_table(self):
        """Test if generate_random_table creates a table with correct dimensions."""
        rows, cols = 3, 4  
        df = generate_random_table(rows, cols)  

        self.assertEqual(df.shape, (rows, cols), f"Expected ({rows},{cols}), but got {df.shape}")

    def test_generate_random_table_values(self):
        """Ensure generated table contains numerical values."""
        df = generate_random_table(2, 3)  

        self.assertTrue(df.map(lambda x: isinstance(x, (int, float))).all().all(), "Table contains non-numeric values")


if __name__ == '__main__':
    unittest.main()
