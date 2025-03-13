import io
import unittest
from workflow.MpegImagePlugin import BitStream  # Adjust the import based on the actual location

class TestBitStream(unittest.TestCase):
    def setUp(self):
        # Create a mock file-like object with some data
        self.mock_file = io.BytesIO(b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09')
        self.bitstream = BitStream(self.mock_file)

    def test_skip_with_eof(self):
        # Skip bits until EOF
        self.bitstream.skip(80)  # This should reach EOF
        with self.assertRaises(EOFError):
            self.bitstream.skip(1)  # Attempt to skip more bits should raise EOFError

    def test_read_after_eof(self):
        self.bitstream.skip(80)  # Skip to EOF
        with self.assertRaises(EOFError):
            self.bitstream.read(1)  # Attempt to read after EOF should raise EOFError

if __name__ == '__main__':
    unittest.main()
