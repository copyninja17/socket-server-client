import sys
import uuid
import json
from client_config import SERVER_IP, SERVER_PORT
import socket

class Client():
    def __init__(self, host, port):
        self.host = host
        self.port = port
    

    def get_cmd(self, file_path=None):
        cmd = []
        try:
            with open (file_path, 'r') as f:
                lines = f.readlines()
                if not lines:
                    raise TypeError
                lines = [line.strip() for line in lines]
                cmd += lines

        except FileNotFoundError:
            return False, "Unable to locate file!"
        except TypeError:
            cmd.append(input("Enter linux command >> "))
            
        
        return True, cmd


    def generate_request(self, file_path):
        status, data = self.get_cmd(file_path)
        
        if status:
            request = {
                "commands": []
                }
            
            for cmd in data:
                request["commands"].append(
                    {
                    'id': str(uuid.uuid4()),
                    'method': cmd
                    }
                )
            return True, json.dumps(request)
        
        else:
            return False, data
        

    def send_request(self, file_path=None):    
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client_socket:
            client_socket.connect((self.host, self.port))

            status, request = self.generate_request(file_path)
            if status:
                client_socket.sendall(request.encode())

            data = client_socket.recv(1024)
            
            return data.decode('utf-8')



if __name__ == "__main__":
    client = Client(SERVER_IP, SERVER_PORT)
   
    while True:
        try:
            if len(sys.argv) > 1:
                file_path = sys.argv[1]
            else:
                file_path = None

            response = client.send_request(file_path)
            print(f"Response from server >> {response}")
            
            if file_path:
                break

        except KeyboardInterrupt:
            print()
            sys.exit()