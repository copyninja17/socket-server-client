import unittest
from unittest.mock import patch, MagicMock
import json
import socket
from server.server import Server


class TestServer(unittest.TestCase):
    def setUp(self):
        """
        Set up test fixtures before each test method
        """
        self.host = "127.0.0.1"
        self.port = 8080
        self.server = Server(self.host, self.port)

    def test_init(self):
        """
        Test Server initialization
        """
        self.assertEqual(self.server.host, self.host)
        self.assertEqual(self.server.port, self.port)
        self.assertIsNotNone(self.server.cmd_timeout)
        self.assertIsNotNone(self.server.conn_timeout)

    def test_execute_cmd_successful(self):
        """
        Test execute_cmd with a successful command
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "command output"
        mock_result.stderr = ""

        with patch('subprocess.run', return_value=mock_result) as mock_run:
            result = self.server.execute_cmd("echo test")

            mock_run.assert_called_once_with(
                "echo test",
                shell=True,
                text=True,
                capture_output=True,
                timeout=self.server.cmd_timeout
            )

            self.assertTrue(result["status"])
            self.assertEqual(result["stdout"], "command output")
            self.assertEqual(result["stderr"], "")
            self.assertEqual(result["error_code"], 0)

    def test_execute_cmd_failed(self):
        """
        Test execute_cmd with a failed command
        """
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message"

        with patch('subprocess.run', return_value=mock_result):
            result = self.server.execute_cmd("invalid_command")

            self.assertFalse(result["status"])
            self.assertEqual(result["stdout"], "")
            self.assertEqual(result["stderr"], "error message")
            self.assertEqual(result["error_code"], 0)

    def test_execute_cmd_not_found(self):
        """
        Test execute_cmd with command not found error
        """
        mock_result = MagicMock()
        mock_result.returncode = 127
        mock_result.stdout = ""
        mock_result.stderr = "command not found"

        with patch('subprocess.run', return_value=mock_result):
            result = self.server.execute_cmd("nonexistent_cmd")

            self.assertFalse(result["status"])
            self.assertEqual(result["error_code"], 3)
            self.assertIn("not found", result["stderr"])

    def test_execute_cmd_timeout(self):
        """
        Test execute_cmd respects timeout parameter
        """
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            self.server.execute_cmd("sleep 10")

            # Verify timeout was passed
            self.assertEqual(
                mock_run.call_args[1]['timeout'],
                self.server.cmd_timeout
            )

    def test_request_parser_valid_single_command(self):
        """
        Test request_parser with valid single command
        """
        request_data = json.dumps({
            "commands": [
                {"id": "123", "method": "ls"}
            ]
        })

        mock_execute_result = {
            "status": True,
            "stdout": "file.txt",
            "stderr": "",
            "error_code": 0
        }

        with patch.object(self.server, 'execute_cmd', return_value=mock_execute_result):
            response = self.server.request_parser(request_data)
            response_dict = json.loads(response)

            self.assertIn("response", response_dict)
            self.assertEqual(len(response_dict["response"]), 1)
            self.assertEqual(response_dict["response"][0]["id"], "123")
            self.assertTrue(response_dict["response"][0]["status"])
            self.assertEqual(response_dict["response"][0]["stdout"], "file.txt")

    def test_request_parser_valid_multiple_commands(self):
        """
        Test request_parser with multiple commands
        """
        request_data = json.dumps({
            "commands": [
                {"id": "001", "method": "ls"},
                {"id": "002", "method": "pwd"},
                {"id": "003", "method": "date"}
            ]
        })

        mock_results = [
            {"status": True, "stdout": "file1", "stderr": "", "error_code": 0},
            {"status": True, "stdout": "/home/user", "stderr": "", "error_code": 0},
            {"status": True, "stdout": "Mon Nov 4", "stderr": "", "error_code": 0}
        ]

        with patch.object(self.server, 'execute_cmd', side_effect=mock_results):
            response = self.server.request_parser(request_data)
            response_dict = json.loads(response)

            self.assertEqual(len(response_dict["response"]), 3)
            self.assertEqual(response_dict["response"][0]["id"], "001")
            self.assertEqual(response_dict["response"][1]["id"], "002")
            self.assertEqual(response_dict["response"][2]["id"], "003")
            self.assertEqual(response_dict["response"][0]["stdout"], "file1")
            self.assertEqual(response_dict["response"][1]["stdout"], "/home/user")

    def test_request_parser_invalid_json(self):
        """
        Test request_parser with invalid JSON
        """
        invalid_json = "this is not json"

        response = self.server.request_parser(invalid_json)
        response_dict = json.loads(response)

        self.assertIn("response", response_dict)
        self.assertFalse(response_dict["response"]["status"])
        self.assertEqual(response_dict["response"]["error_code"], 1)

    def test_request_parser_missing_commands_key(self):
        """
        Test request_parser with missing 'commands' key
        """
        invalid_data = json.dumps({"wrong_key": []})

        response = self.server.request_parser(invalid_data)
        response_dict = json.loads(response)

        self.assertFalse(response_dict["response"]["status"])
        self.assertEqual(response_dict["response"]["error_code"], 2)

    def test_request_parser_missing_method_key(self):
        """
        Test request_parser with missing 'method' key in command
        """
        invalid_data = json.dumps({
            "commands": [
                {"id": "123", "wrong_key": "ls"}
            ]
        })

        response = self.server.request_parser(invalid_data)
        response_dict = json.loads(response)

        self.assertFalse(response_dict["response"]["status"])
        self.assertEqual(response_dict["response"]["error_code"], 2)

    def test_request_parser_missing_id_key(self):
        """
        Test request_parser with missing 'id' key in command
        """
        invalid_data = json.dumps({
            "commands": [
                {"method": "ls"}
            ]
        })

        response = self.server.request_parser(invalid_data)
        response_dict = json.loads(response)

        self.assertFalse(response_dict["response"]["status"])
        self.assertEqual(response_dict["response"]["error_code"], 2)

    def test_request_parser_exception_handling(self):
        """
        Test request_parser handles unexpected exceptions
        """
        valid_data = json.dumps({
            "commands": [{"id": "123", "method": "ls"}]
        })

        with patch.object(self.server, 'execute_cmd', side_effect=Exception("Unexpected error")):
            response = self.server.request_parser(valid_data)
            response_dict = json.loads(response)

            self.assertFalse(response_dict["response"]["status"])
            self.assertEqual(response_dict["response"]["error_code"], 4)

    def test_handle_client_successful(self):
        """
        Test handle_client with successful data exchange
        """
        mock_conn = MagicMock()
        mock_addr = ("127.0.0.1", 12345)

        request_data = json.dumps({
            "commands": [{"id": "123", "method": "ls"}]
        })
        mock_conn.recv.return_value = request_data.encode()

        expected_response = json.dumps({
            "response": [{
                "status": True,
                "stdout": "files",
                "stderr": "",
                "error_code": 0,
                "id": "123"
            }]
        })

        with patch.object(self.server, 'request_parser', return_value=expected_response):
            self.server.handle_client(mock_conn, mock_addr)

            mock_conn.settimeout.assert_called_once_with(self.server.conn_timeout)
            mock_conn.recv.assert_called_once_with(1024)
            mock_conn.sendall.assert_called_once_with(expected_response.encode())
            mock_conn.close.assert_called_once()

    def test_handle_client_empty_data(self):
        """
        Test handle_client with empty data received
        """
        mock_conn = MagicMock()
        mock_addr = ("127.0.0.1", 12345)
        mock_conn.recv.return_value = b""

        with patch('builtins.print') as mock_print:
            self.server.handle_client(mock_conn, mock_addr)

            mock_conn.sendall.assert_not_called()
            mock_conn.close.assert_called_once()
            # Verify empty data message was printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            self.assertTrue(any("Empty data" in str(call) for call in print_calls))

    def test_handle_client_timeout(self):
        """
        Test handle_client handles socket timeout
        """
        mock_conn = MagicMock()
        mock_addr = ("127.0.0.1", 12345)
        mock_conn.recv.side_effect = socket.timeout()

        with patch('builtins.print') as mock_print:
            self.server.handle_client(mock_conn, mock_addr)

            mock_conn.close.assert_called_once()
            # Verify timeout message was printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            self.assertTrue(any("Timeout" in str(call) for call in print_calls))

    def test_handle_client_exception(self):
        """
        Test handle_client handles general exceptions
        """
        mock_conn = MagicMock()
        mock_addr = ("127.0.0.1", 12345)
        mock_conn.recv.side_effect = Exception("Connection error")

        with patch('builtins.print') as mock_print:
            self.server.handle_client(mock_conn, mock_addr)

            mock_conn.close.assert_called_once()
            # Verify error message was printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            self.assertTrue(any("Error" in str(call) for call in print_calls))

    def test_handle_client_sets_timeout(self):
        """
        Test that handle_client sets connection timeout
        """
        mock_conn = MagicMock()
        mock_addr = ("127.0.0.1", 12345)
        mock_conn.recv.return_value = b""

        self.server.handle_client(mock_conn, mock_addr)

        mock_conn.settimeout.assert_called_once_with(self.server.conn_timeout)

    @patch('socket.socket')
    @patch('threading.Thread')
    def test_start_server_setup(self, mock_thread, mock_socket_class):
        """
        Test start method sets up socket correctly
        """
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        # Mock accept to raise exception after first call to exit loop
        mock_socket.accept.side_effect = KeyboardInterrupt()

        try:
            self.server.start()
        except KeyboardInterrupt:
            pass

        # Verify socket setup
        mock_socket.setsockopt.assert_called_once_with(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )
        mock_socket.bind.assert_called_once_with((self.host, self.port))
        mock_socket.listen.assert_called_once()

    @patch('socket.socket')
    @patch('threading.Thread')
    def test_start_accepts_connections(self, mock_thread_class, mock_socket_class):
        """
        Test start method accepts and handles connections
        """
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        mock_conn = MagicMock()
        mock_addr = ("127.0.0.1", 12345)

        # Accept one connection then raise exception to exit
        mock_socket.accept.side_effect = [(mock_conn, mock_addr), KeyboardInterrupt()]

        mock_thread = MagicMock()
        mock_thread_class.return_value = mock_thread

        try:
            self.server.start()
        except KeyboardInterrupt:
            pass

        # Verify thread was created with correct arguments
        mock_thread_class.assert_called_once_with(
            target=self.server.handle_client,
            args=(mock_conn, mock_addr)
        )
        mock_thread.start.assert_called_once()

    @patch('socket.socket')
    @patch('threading.Thread')
    def test_start_handles_multiple_connections(self, mock_thread_class, mock_socket_class):
        """
        Test start method handles multiple connections
        """
        mock_socket = MagicMock()
        mock_socket_class.return_value.__enter__.return_value = mock_socket

        mock_conn1 = MagicMock()
        mock_addr1 = ("127.0.0.1", 12345)
        mock_conn2 = MagicMock()
        mock_addr2 = ("127.0.0.1", 12346)

        # Accept two connections then raise exception
        mock_socket.accept.side_effect = [
            (mock_conn1, mock_addr1),
            (mock_conn2, mock_addr2),
            KeyboardInterrupt()
        ]

        try:
            self.server.start()
        except KeyboardInterrupt:
            pass

        # Verify two threads were created
        self.assertEqual(mock_thread_class.call_count, 2)


class TestServerIntegration(unittest.TestCase):
    """
    Integration tests that test multiple methods together
    """

    def setUp(self):
        self.server = Server("localhost", 9999)

    def test_full_request_processing_flow(self):
        """Test complete flow from request parsing to command execution."""
        request_data = json.dumps({
            "commands": [
                {"id": "001", "method": "echo hello"},
                {"id": "002", "method": "echo world"}
            ]
        })

        mock_result1 = MagicMock()
        mock_result1.returncode = 0
        mock_result1.stdout = "hello\n"
        mock_result1.stderr = ""

        mock_result2 = MagicMock()
        mock_result2.returncode = 0
        mock_result2.stdout = "world\n"
        mock_result2.stderr = ""

        with patch('subprocess.run', side_effect=[mock_result1, mock_result2]):
            response = self.server.request_parser(request_data)
            response_dict = json.loads(response)

            self.assertEqual(len(response_dict["response"]), 2)
            self.assertEqual(response_dict["response"][0]["stdout"], "hello\n")
            self.assertEqual(response_dict["response"][1]["stdout"], "world\n")
            self.assertEqual(response_dict["response"][0]["id"], "001")
            self.assertEqual(response_dict["response"][1]["id"], "002")

    def test_end_to_end_client_handling(self):
        """
        Test complete end-to-end client request handling
        """
        mock_conn = MagicMock()
        mock_addr = ("192.168.1.100", 54321)

        request = json.dumps({
            "commands": [{"id": "test-123", "method": "pwd"}]
        })
        mock_conn.recv.return_value = request.encode()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "/home/user\n"
        mock_result.stderr = ""

        with patch('subprocess.run', return_value=mock_result):
            self.server.handle_client(mock_conn, mock_addr)

            # Verify the complete flow
            mock_conn.settimeout.assert_called_once()
            mock_conn.recv.assert_called_once()

            # Check the response sent
            sent_data = mock_conn.sendall.call_args[0][0].decode()
            response = json.loads(sent_data)

            self.assertEqual(len(response["response"]), 1)
            self.assertEqual(response["response"][0]["id"], "test-123")
            self.assertEqual(response["response"][0]["stdout"], "/home/user\n")
            self.assertTrue(response["response"][0]["status"])

            mock_conn.close.assert_called_once()

    def test_error_recovery_in_batch_commands(self):
        """
        Test that one failed command doesn't stop others from executing
        """
        request_data = json.dumps({
            "commands": [
                {"id": "001", "method": "echo success"},
                {"id": "002", "method": "invalid_command_xyz"},
                {"id": "003", "method": "echo another"}
            ]
        })

        mock_result1 = MagicMock(returncode=0, stdout="success\n", stderr="")
        mock_result2 = MagicMock(returncode=127, stdout="", stderr="command not found")
        mock_result3 = MagicMock(returncode=0, stdout="another\n", stderr="")

        with patch('subprocess.run', side_effect=[mock_result1, mock_result2, mock_result3]):
            response = self.server.request_parser(request_data)
            response_dict = json.loads(response)

            # All commands should execute
            self.assertEqual(len(response_dict["response"]), 3)

            # First command succeeds
            self.assertTrue(response_dict["response"][0]["status"])
            self.assertEqual(response_dict["response"][0]["stdout"], "success\n")

            # Second command fails
            self.assertFalse(response_dict["response"][1]["status"])
            self.assertEqual(response_dict["response"][1]["error_code"], 3)

            # Third command succeeds
            self.assertTrue(response_dict["response"][2]["status"])
            self.assertEqual(response_dict["response"][2]["stdout"], "another\n")


if __name__ == '__main__':
    unittest.main()