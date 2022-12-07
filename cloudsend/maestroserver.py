from cloudsend import provider as cr
import asyncio , os , sys , time
from cloudsend.core import CloudSendProcessState
import traceback
import json
import socket
from io import StringIO , TextIOWrapper
from multiprocessing import Process, Queue
from threading import Thread

HOST = 'localhost' #'0.0.0.0' #127.0.0.1' 
PORT = 5000

def process_command(cs_client,command,args,conn):

    io_pipe    = conn.makefile('rw',buffering=1) 
    #io_pipe    = TextIOWrapper(conn.makefile('rw',buffering=1), write_through=True)
    sys.stdout = io_pipe
    sys.stderr = io_pipe
    try:

        if command == 'wakeup':

            cs_client.wakeup()

        elif command == 'start':
            reset = False
            if args:
                reset = args[0].strip().lower() == "true"
            cs_client.start(reset)

        elif command == 'allocate' or command == 'assign':

            cs_client.assign()

        elif command == 'deploy':

            cs_client.deploy()

        elif command == 'run':

            cs_client.run()
        
        elif command == 'watch':

            daemon = True
            if args:
                daemon = args[0].strip().lower() == "true"
            cs_client.watch(None,daemon)

        elif command == 'wait':

            cs_client.wait_for_jobs_state(CloudSendProcessState.DONE|CloudSendProcessState.ABORTED)

        elif command == 'get_states':

            cs_client.get_jobs_states()

        elif command == 'print_summary' or command == 'print':

            cs_client.print_jobs_summary()

        elif command == 'print_aborted':

            cs_client.print_aborted_logs()

        elif command == 'fetch_results':

            if args:
                directory = args[0].strip()
                cs_client.fetch_results(directory)

        elif command == 'test':

            print("TEST")
        
        else:

            print("UNKNOWN COMMAND")
    
    except Exception as e:
        io_pipe.flush()
        io_pipe.close()
        raise e

    io_pipe.flush()
    # to let time for the buffer to be flushed before killing thread and connection
    time.sleep(1)
    io_pipe.close()

def client_handler(cs_client,conn):
    kill_thread = True
    with conn:
        old_stdout = sys.stdout
        conn_pipe = conn.makefile(mode='rw')
        while True:
            try:
                cmd_line = conn_pipe.readline()
                if not cmd_line:
                    break
                cmd_line = cmd_line.strip()
                cmd_args = cmd_line.split(':')
                if len(cmd_args)>=2:
                    cmd  = cmd_args[0].strip()
                    args = cmd_args[1].split(',')
                else:
                    cmd  = cmd_line
                    args = None

                if cmd == 'watch': # we want to start running the command for ever
                    kill_thread = False
                process_command(cs_client,cmd,args,conn)
                break # one-shot command
            except ConnectionResetError as cre:
                try:
                    sys.stdout = old_stdout
                    print(cre)
                    print("DISCONNECTION")
                except:
                    pass
                break    
            except Exception as e:
                try:
                    sys.stdout = old_stdout
                    print(e)
                except:
                    pass
                break  
        try:
            conn_pipe.flush()
        except:
            pass
        try:
            conn_pipe.close()
        except:
            pass
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except:
            pass
        try:
            conn.close()
        except:
            pass
    if kill_thread:
        pass
        #sys.exit(99) #force exit thread 

async def mainloop(cs_client):

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print("listening to port",PORT)
        while True:
            conn, addr = s.accept()
            t = Thread(target=client_handler, args=(cs_client,conn,))
            t.start()  
            #t.join()      

            # p = Process(target=client_handler, args=(cs_client,conn,))
            # p.start()
            # p.join()
            # p.terminate()

# run main loop
def main():

    if os.path.exists('config.json'):
        with open('config.json','r') as config_file:
            config = json.loads(config_file.read())
        print("loaded config from json file")
    else:
        try:
            sys.path.append(os.path.abspath(os.getcwd()))    
            configModule = __import__("config",globals(),locals())
            config = configModule.config
        except ModuleNotFoundError as mfe:
            print("\n\033[91mYou need to create a config.py file (see 'example/config.example.py')\033[0m\n")
            print("\n\033[91m(you can also create a config.json file instead)\033[0m\n")
            raise mfe

    cs_client = cr.get_client(config)

    # may be we've just restarted a crashed maestro server process
    # let's test for WATCH state and reach it back again if thats needed
    cs_client.wakeup()

    asyncio.run( mainloop(cs_client) )

if __name__ == '__main__':
    main()    