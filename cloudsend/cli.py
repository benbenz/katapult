import cloudsend
import asyncio
import sys 
import psutil
import subprocess
import multiprocessing 
import time
from cloudsend.maestroserver import main as server_main
from cloudsend.maestroclient import maestro_client

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

def cli():
    start_server() # locally we use python to start the server. maximizes the chance to be Windows complatible
    maestro_client()

def start_server():
    server_started = False
    for pid in psutil.pids():
        try:
            p = psutil.Process(pid)
            if is_cloudsend_process(p,"cloudsend.maestroserver"):
                print("CloudSend server already started ...")
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
        print("Starting CloudSend server ...")
        subprocess.Popen(['python3','-u','-m','cloudsend.maestroserver'])
        time.sleep(1)
        #q = multiprocessing.Queue()
        #p = multiprocessing.Process(target=server_main,args=(q,))
        #p = multiprocessing.Process(target=server_main)
        #p.daemon = True
        #p.start()


if __name__ == '__main__':     
    multiprocessing.set_start_method('spawn')

    if len(sys.argv)<2:
        print("python3 -m cloudsend.cli CMD [ARGS]")
        sys.exit()

    command = sys.argv[1]

    maestro_client(command)
