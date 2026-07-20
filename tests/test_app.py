import socket
import unittest

from homesteader.app import LOCAL_HOST, find_available_port


class AppTests(unittest.TestCase):
    def test_port_finder_uses_loopback(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind((LOCAL_HOST, 0))
            candidate = find_available_port(occupied.getsockname()[1])
            self.assertNotEqual(candidate, occupied.getsockname()[1])


if __name__ == "__main__":
    unittest.main()
