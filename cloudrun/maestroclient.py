import socket , sys
from io import StringIO , TextIOWrapper


HOST = '127.0.0.1'
PORT = 5000

if len(sys.argv)<2:
    print("python3 -m cloudrun.maestroclient CMD")
    sys.exit()

command = sys.argv[1]

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    #sock_pipe = s.makefile('rw')
    sock_pipe = s.makefile('rw',buffering=1) #TextIOWrapper(s.makefile('rwb',buffering=0), write_through=True)
    #sys.stdout = sock_pipe
    sock_pipe.write(command+"\n")
    sock_pipe.flush()
    while True:
        line = sock_pipe.readline()
        if not line:
            break
        print(line.strip())