import socket
s = socket.socket()
s.connect(("127.0.0.1", 4444))
s.send(b"\x02\xFF")