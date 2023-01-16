import socket , sys
import time
from io import StringIO , TextIOWrapper

HOST = 'localhost' #'127.0.0.1' #'0.0.0.0'
PORT = 5000

def maestro_client(command):
    while True:
        attempts = 0 
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((HOST, PORT))
                #sock_pipe = s.makefile('rw')
                sock_pipe = s.makefile('rw',buffering=1) #TextIOWrapper(s.makefile('rwb',buffering=0), write_through=True)
                #sys.stdout = sock_pipe
                sock_pipe.write(command+"\n")
                sock_pipe.flush()
                try:
                    while True:
                        line = sock_pipe.readline()
                        if not line:
                            break
                        print(line.strip())
                except ConnectionResetError as cre:
                    #sock_pipe.readline()
                    #print(line.strip())
                    sock_pipe.flush()
                    sock_pipe.close()
                except Exception as e:
                    sock_pipe.flush()
                    sock_pipe.close()   
            break
        except ConnectionRefusedError as err:
            print("waiting on server ...")
            time.sleep(5)
            attempts += 1
            if attempts > 40:
                print("Error: can't connect to server ...")
                sys.exit(99)

def main():
    if len(sys.argv)<2:
        print("python3 -m katapult.maestroclient CMD [IP_ADDR]")
        sys.exit()

    #print(sys.argv)

    if len(sys.argv)>3:
        ip_addr = sys.argv[len(sys.argv)-1]
        command = sys.argv[len(sys.argv)-2]
        HOST    = ip_addr
    else:
        command = sys.argv[len(sys.argv)-1]
        ip_addr = None

    maestro_client(command)  
        
if __name__ == '__main__':
    main()