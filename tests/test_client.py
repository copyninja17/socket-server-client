import unittest
from unittest.mock import patch, mock_open, MagicMock
import json
import uuid
import socket
from client.client import Client


class TestClient(unittest.TestCase):
    def setUp(self):
        """
        Set up test fixtures before each test method
        """
        self.host = "127.0.0.1"
        self.port = 8080
        self.client = Client(self.host, self.port)
        self.test_file_path = "test_commands.txt"

    def test_init(self):
        """
        Test Client initialization
        """
        self.assertEqual(self.client.host, self.host)
        self.assertEqual(self.client.port, self.port)

    def test_get_cmd_with_valid_file(self):
        """
        Test get_cmd with a valid file containing commands
        """
        mock_file_content = "ls -la\npwd\necho hello\n"

        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            status, cmd = self.client.get_cmd(self.test_file_path)

            self.assertTrue(status)
            self.assertEqual(cmd, ["ls -la", "pwd", "echo hello"])

    def test_get_cmd_with_empty_file_and_user_input(self):
        """
        Test get_cmd with empty file falls back to user input
        """
        mock_file_content = ""
        user_input = "whoami"

        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            with patch("builtins.input", return_value=user_input):
                status, cmd = self.client.get_cmd(self.test_file_path)

                self.assertTrue(status)
                self.assertEqual(cmd, [user_input])

    def test_get_cmd_with_nonexistent_file(self):
        """
        Test get_cmd with a file that doesn't exist
        """
        with patch("builtins.open", side_effect=FileNotFoundError()):
            status, message = self.client.get_cmd("nonexistent.txt")

            self.assertFalse(status)
            self.assertEqual(message, "Unable to locate file!")

    def test_get_cmd_with_whitespace_stripping(self):
        """
        Test that get_cmd strips whitespace from commands
        """
        mock_file_content = "  ls -la  \n\tpwd\t\n  echo test  \n"

        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            status, cmd = self.client.get_cmd(self.test_file_path)

            self.assertTrue(status)
            self.assertEqual(cmd, ["ls -la", "pwd", "echo test"])

    def test_generate_request_with_valid_commands(self):
        """
        Test generate_request creates proper JSON structure
        """
        mock_commands = ["ls", "pwd"]

        with patch.object(self.client, 'get_cmd', return_value=(True, mock_commands)):
            status, request_json = self.client.generate_request(self.test_file_path)

            self.assertTrue(status)
            request = json.loads(request_json)

            self.assertIn("commands", request)
            self.assertEqual(len(request["commands"]), 2)

            for i, cmd_obj in enumerate(request["commands"]):
                self.assertIn("id", cmd_obj)
                self.assertIn("method", cmd_obj)
                self.assertEqual(cmd_obj["method"], mock_commands[i])
                # Verify UUID format
                uuid.UUID(cmd_obj["id"])

    def test_generate_request_with_failed_get_cmd(self):
        """
        Test generate_request when get_cmd fails
        """
        error_message = "Unable to locate file!"

        with patch.object(self.client, 'get_cmd', return_value=(False, error_message)):
            status, message = self.client.generate_request(self.test_file_path)

            self.assertFalse(status)
            self.assertEqual(message, error_message)

    def test_generate_request_uuid_uniqueness(self):
        """
        Test that each command gets a unique UUID
        """
        mock_commands = ["cmd1", "cmd2", "cmd3"]

        with patch.object(self.client, 'get_cmd', return_value=(True, mock_commands)):
            status, request_json = self.client.generate_request(self.test_file_path)

            request = json.loads(request_json)
            uuids = [cmd["id"] for cmd in request["commands"]]

            # Check all UUIDs are unique
            self.assertEqual(len(uuids), len(set(uuids)))

    @patch('socket.socket')
    def test_send_request_successful(self, mock_socket_class):
        """
        Test send_request with successful server communication
        """
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        mock_response = json.dumps({"status": "success"})
        mock_socket.recv.return_value = mock_response.encode('utf-8')

        mock_request = json.dumps({"commands": [{"id": "123", "method": "ls"}]})

        with patch.object(self.client, 'generate_request', return_value=(True, mock_request)):
            response = self.client.send_request(self.test_file_path)

            mock_socket.connect.assert_called_once_with((self.host, self.port))
            mock_socket.sendall.assert_called_once_with(mock_request.encode())
            mock_socket.recv.assert_called_once_with(1024)
            self.assertEqual(response, mock_response)

    @patch('socket.socket')
    def test_send_request_with_failed_generate_request(self, mock_socket_class):
        """
        Test send_request when generate_request fails
        """
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        error_message = "Unable to locate file!"
        mock_socket.recv.return_value = b"response"

        with patch.object(self.client, 'generate_request', return_value=(False, error_message)):
            response = self.client.send_request(self.test_file_path)

            # sendall should not be called when generate_request fails
            mock_socket.sendall.assert_not_called()
            # but recv is still called
            mock_socket.recv.assert_called_once()

    @patch('socket.socket')
    def test_send_request_socket_connection(self, mock_socket_class):
        """
        Test that send_request properly establishes socket connection
        """
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket
        mock_socket.recv.return_value = b"test response"

        mock_request = json.dumps({"commands": []})

        with patch.object(self.client, 'generate_request', return_value=(True, mock_request)):
            self.client.send_request(self.test_file_path)

            # verify socket was created with correct parameters
            mock_socket_class.assert_called_once_with(
                socket.AF_INET,
                socket.SOCK_STREAM
            )
            mock_socket.connect.assert_called_once_with((self.host, self.port))

    @patch('socket.socket')
    def test_send_request_response_decoding(self, mock_socket_class):
        """
        Test that send_request properly decodes server response
        """
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        expected_response = "Server response with special chars: åäö"
        mock_socket.recv.return_value = expected_response.encode('utf-8')

        with patch.object(self.client, 'generate_request', return_value=(True, "{}")):
            response = self.client.send_request()

            self.assertEqual(response, expected_response)

    def test_get_cmd_with_none_file_path_requires_input(self):
        """
        Test get_cmd with None file_path requires user input
        """
        user_input = "date"

        with patch("builtins.input", return_value=user_input):
            status, cmd = self.client.get_cmd(None)

            self.assertTrue(status)
            self.assertEqual(cmd, [user_input])


class TestClientIntegration(unittest.TestCase):
    """
    Integration tests that test multiple methods together
    """

    def setUp(self):
        self.client = Client("localhost", 9999)
        self.test_file_path = "commands.txt"

    def test_full_request_generation_flow(self):
        """
        Test the complete flow from file reading to JSON generation
        """
        mock_file_content = "ls\npwd\n"

        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            status, request_json = self.client.generate_request(self.test_file_path)

            self.assertTrue(status)
            request = json.loads(request_json)

            self.assertEqual(len(request["commands"]), 2)
            self.assertEqual(request["commands"][0]["method"], "ls")
            self.assertEqual(request["commands"][1]["method"], "pwd")

    @patch('socket.socket')
    def test_end_to_end_request_with_file(self, mock_socket_class):
        """
        Test complete end-to-end flow with file input
        """
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        mock_file_content = "echo test\n"
        server_response = json.dumps({"result": "test"})
        mock_socket.recv.return_value = server_response.encode('utf-8')

        with patch("builtins.open", mock_open(read_data=mock_file_content)):
            response = self.client.send_request(self.test_file_path)

            self.assertEqual(response, server_response)
            mock_socket.connect.assert_called_once()
            mock_socket.sendall.assert_called_once()

            sent_data = json.loads(mock_socket.sendall.call_args[0][0].decode('utf-8'))
            self.assertEqual(len(sent_data["commands"]), 1)
            self.assertEqual(sent_data["commands"][0]["method"], "echo test")


if __name__ == '__main__':
    unittest.main()