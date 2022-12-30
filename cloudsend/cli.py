import cloudsend
import asyncio
import sys 
import psutil
import subprocess
import multiprocessing 
import time
import copy
from cloudsend.maestroserver import main as server_main
from cloudsend.maestroclient import maestro_client
from cloudsend.provider import make_client_command , stream_dump  

# if [[ $(ps aux | grep "cloudsend.maestroserver" | grep -v 'grep') ]] ; then
#     echo "CloudSend server already running"
# else
#     if [[ $(ps -ef | awk '/[m]aestroserver/{print $2}') ]] ; then
#         ps -ef | awk '/[m]aestroserver/{print $2}' | xargs kill 
#     fi
#     echo "Starting CloudSend server ..."
#     python3 -u -m cloudsend.maestroserver
# fi

def cloudsend_kill(p):
    try:
        p.kill()
    except:
        pass
    try:
        p.terminate()
    except:
        pass

def is_cloudsend_process(p,name='maestroserver'):
    try:
        if name in p.name():
            return True
        for arg in p.cmdline():
            if name in arg:
                return True
        return False
    except psutil.AccessDenied:
        return False
    except psutil.NoSuchProcess:
        return False

def cli(command):
    #start_server() # locally we use python to start the server. maximizes the chance to be Windows complatible
    maestro_client(command)

def start_server():
    server_started = False
    for pid in psutil.pids():
        try:
            p = psutil.Process(pid)
            if is_cloudsend_process(p,"cloudsend.maestroserver"):
                print("[CloudSend server already started]")
                server_started = True
                break
        except psutil.NoSuchProcess:
            pass
    if not server_started:
        # make sure we kill any rogue processes
        for pid in psutil.pids():
            try:
                p = psutil.Process(pid)
                for pp in p.children(recursive=True):
                    if is_cloudsend_process(pp):
                        cloudsend_kill(pp)
                if is_cloudsend_process(p):
                    cloudsend_kill(p)
            except psutil.NoSuchProcess:
                pass
        print("[Starting CloudSend server ...]")
        subprocess.Popen(['python3','-u','-m','cloudsend.maestroserver'])
        time.sleep(1)
        #q = multiprocessing.Queue()
        #p = multiprocessing.Process(target=server_main,args=(q,))
        #p = multiprocessing.Process(target=server_main)
        #p.daemon = True
        #p.start()

def cli_translate(command,args):
    if command == 'init':
        return args

    elif command == 'wakeup':
        return args

    elif command == 'start':
        if not args:
            return [False]
        elif len(args)==1:
            return [args[0].strip().lower() == "true"]
        else:
            return [False]

    elif command == 'cfg_add_instances':
        return args

    elif command == 'cfg_add_environments':
        return args

    elif command == 'cfg_add_jobs':
        return args

    elif command == 'cfg_add_config':
        return args

    elif command == 'cfg_reset':
        return args

    elif command == 'deploy':
        return args

    elif command == 'run':
        return args

    elif command == 'kill':
        return args
    
    elif command == 'wait':
        new_args = []
        if args and len(args) >= 1:
            job_state = int(args[0])
            new_args.append(job_state)
        if args and len(args) >= 3:
            run_session = CloudSendRunSessionProxy( int(args[1]) , args[2] )
            new_args.append( stream_dump(run_session) )
        return new_args 

    elif command == 'get_num_active_processes':

        new_args = []
        if args and len(args) >= 2:
            run_session = CloudSendRunSessionProxy( int(args[0]) , args[1] )
            new_args.append( stream_dump(run_session) )
        return new_args 

    elif command == 'get_num_instances':
        return args

    elif command == 'get_states':
        new_args = []
        if args and len(args) >= 2:
            run_session = CloudSendRunSessionProxy( int(args[0]) , args[1] )
            new_args.append( stream_dump(run_session) )
        return new_args 

    elif command == 'print_summary' or command == 'print':
        new_args = []
        if args and len(args) >= 2:
            run_session = CloudSendRunSessionProxy( int(args[0]) , args[1] )
            new_args.append( stream_dump(run_session) )
        if args and len(args) >= 3:
            instance = CloudSendInstanceProxy( args[2] )
            new_args.append( stream_dump(instance) )
        return new_args 

    elif command == 'print_aborted':
        new_args = []
        if args and len(args) >= 2:
            run_session = CloudSendRunSessionProxy( int(args[0]) , args[1] )
            new_args.append( stream_dump(run_session) )
        if args and len(args) >= 3:
            instance = CloudSendInstanceProxy( args[2] )
            new_args.append( stream_dump(instance) )
        return new_args 
        
    elif command == 'print_objects':
        return args

    elif command == 'clear_results_dir':
        return args

    elif command == 'fetch_results':

        new_args = []
        if args and len(args)>=1:
            directory = args[0].strip()
            if directory.lower() == 'none':
                directory = None
            new_args.append(directory)
        if args and len(args)>=3:
            run_session = CloudSendRunSessionProxy( int(args[1]) , args[2] )
            new_args.append( stream_dump(run_session) )
        return new_args

    elif command == 'finalize':
        return args

    elif command == 'shutdown':
        return args

    elif command == 'test':
        return args
    
    else:
        return None

def main():
    multiprocessing.set_start_method('spawn')

    if len(sys.argv)<2:
        print("python3 -m cloudsend.cli CMD [ARGS]")
        sys.exit()

    args = copy.deepcopy(sys.argv)
    cmd_arg = args.pop(0) #trash
    while 'cli' not in cmd_arg:
        cmd_arg = args.pop(0)
    command = args.pop(0)

    ser_args = cli_translate(command,args)
    # if len(args)>0:
    #     the_command =  COMMAND_ARGS_SEP.join( [ command , COMMAND_ARGS_SEP.join(args) ] )
    # else:
    #     the_command = command

    # lets not escape the command, we're not sending it to a stream
    the_command = make_client_command( command , ser_args , False)
    cli(the_command)


if __name__ == '__main__':     
    main()