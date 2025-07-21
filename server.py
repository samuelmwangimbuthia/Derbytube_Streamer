import socket
import app

def handle_command(cmd):
    if cmd == "start":
        print("Start command received — Start GStreamer here")
        app.start_pipeline()
    elif cmd == "stop":
        print("Stop command received — Stop GStreamer here")
        #app.stop_pipeline()
    else:
        print(f"Unknown command: {cmd}")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind(('localhost', 5000))
server.listen(1)

print("Server is listening on port 5000...")

while True:
    client_socket, addr = server.accept()
    print(f"Connection from {addr} has been established.")
    
    # Handle the client connection
    try:
        while True:
            data = client_socket.recv(1024)
            if not data:
                break
            print(f"Received: {data}")
            command = data.decode().strip()
            print(f"Received: {command}")
            handle_command(command)
            client_socket.sendall(b"Message received")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client_socket.close()