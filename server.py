import sys
import json
import socket
import threading
import subprocess
from server_config import SERVER_IP, SERVER_PORT, CMD_TIMEOUT, CONN_TIMEOUT


class Server:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.cmd_timeout = CMD_TIMEOUT
        self.conn_timeout = CONN_TIMEOUT
    

    def request_parser(self, data):
        '''
        Parses json rpc request return response in json rpc format
        '''
        try:
            result = {"response": []}
            data = json.loads(data)["commands"]
            
            for cmd in data:
                result["response"].append(self.execute_cmd(cmd["method"]))
                result["response"][-1].update({
                        "id": cmd["id"]
                    }
                )
            
            return json.dumps(result)
        
        except json.JSONDecodeError:
            error_code = 1
        except KeyError:
            error_code = 2
        except Exception as e:
            error_code = 4

        return json.dumps({"response": {"status": False, "error_code": error_code}})


    def execute_cmd(self, cmd):
        '''
        Executes command and returns response in dict format
        '''
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=self.cmd_timeout)

        status = True if result.returncode == 0 else False

        error_code = 0
        if "not found" in result.stderr:
            error_code = 3

        return {"status": status, "stdout": result.stdout, "stderr": result.stderr, "error_code": error_code}


    def handle_client(self, conn, addr):
        '''
        Spawns a new client on a new thread
        Recieves data from connection
        Sends back response
        '''
        try:
            print(f"Connected by {addr}")
            conn.settimeout(self.conn_timeout) 
            
            data = conn.recv(1024)
            if data:
                print(f"Received: {data.decode('utf-8')}")
                result = self.request_parser(data)
                conn.sendall(result.encode())
            else:
                print(f"Empty data received from {addr}")

        except socket.timeout:
            print(f"Timeout occurred with {addr}")
        except Exception as e:
            print(f"Error with client {addr}: {e}")
        finally:
            conn.close()


    def start(self):
        '''
        Starts the socket server
        '''
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((self.host, self.port))
            server_socket.listen()
            print(f"Listening on {self.host}:{self.port} for connections")

            while True:
                conn, addr = server_socket.accept()
                thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                thread.start()


if __name__ == "__main__":
    try:
        server = Server(SERVER_IP, SERVER_PORT)

        server.start()
    except KeyboardInterrupt:
        print()
        sys.exit()
