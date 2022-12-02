from cloudrun import provider as cr
import asyncio , os , sys
from cloudrun.core import CloudRunProcessState
import traceback
import json
import socket
from io import StringIO , TextIOWrapper
from multiprocessing import Process, Queue
from threading import Thread

HOST = 'localhost' #'0.0.0.0' #127.0.0.1' 
PORT = 5000

def process_command(cr_client,command,args,conn):

    io_pipe    = conn.makefile('rw',buffering=1) 
    #io_pipe    = TextIOWrapper(conn.makefile('rw',buffering=1), write_through=True)
    sys.stdout = io_pipe
    sys.stderr = io_pipe
    try:

        if command == 'wakeup':

            cr_client.wakeup()

        elif command == 'start':
            reset = False
            if args:
                reset = args[0].strip().lower() == "true"
            cr_client.start(reset)

        elif command == 'allocate' or command == 'assign':

            cr_client.assign()

        elif command == 'deploy':

            cr_client.deploy()

        elif command == 'run':

            cr_client.run()
        
        elif command == 'watch':

            cr_client.watch(None,True) # daemon

        elif command == 'wait':

            cr_client.wait_for_jobs_state(CloudRunProcessState.DONE|CloudRunProcessState.ABORTED)

        elif command == 'get_states':

            cr_client.get_jobs_states()

        elif command == 'print_summary' or command == 'print':

            cr_client.print_jobs_summary()

        elif command == 'print_aborted':

            cr_client.print_aborted_logs()

        elif command == 'test':

            print("TEST")
        
        else:

            print("UNKNOWN COMMAND")
    
    except Exception as e:
        io_pipe.flush()
        io_pipe.close()
        raise e

    io_pipe.flush()
    io_pipe.close()

def client_handler(cr_client,conn):
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
                process_command(cr_client,cmd,args,conn)
                break # one-shot command
            except ConnectionResetError as cre:
                sys.stdout = old_stdout
                print(cre)
                print("DISCONNECTION")
                break    
            except Exception as e:
                sys.stdout = old_stdout
                print(e)
                break  
        conn_pipe.flush()
        conn_pipe.close()
    if kill_thread:
        sys.exit(99) #force exit thread 

async def mainloop(cr_client):

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print("listening to port",PORT)
        while True:
            conn, addr = s.accept()
            t = Thread(target=client_handler, args=(cr_client,conn,))
            t.start()  
            t.join()      
            # p = Process(target=client_handler, args=(cr_client,conn,))
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

    cr_client = cr.get_client(config)

    # may be we've just restarted a crashed maestro server process
    # let's test for WATCH state and reach it back again if thats needed
    cr_client.wakeup()

    asyncio.run( mainloop(cr_client) )

if __name__ == '__main__':
    main()    