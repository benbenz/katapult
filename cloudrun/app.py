from cloudrun import core as cr
import asyncio , os , sys
from cloudrun.core import CloudRunCommandState
import traceback

async def tail_loop(script_hash,uid):

    generator = await cr_client.tail(script_hash,uid) 
    #print('\n\n\nwe are here\n\n\n')
    for line in generator:
        print(line)


async def mainloop(cr_client):

    print("\n== START ==\n")

    # distribute the jobs on the instances (dummy algo for now)
    cr_client.start()

    print("\n== ALLOCATE JOBS ==\n")

    # distribute the jobs on the instances (dummy algo for now)
    cr_client.assign_jobs_to_instances()

    print("\n== DEPLOY ==\n")

    # pre-deploy instance , environments and job files
    # it is recommended to wait here allthough run.sh should wait for bootstraping
    # currently, the bootstraping is non-blocking
    # so this will barely wait ... (the jobs will do the waiting ...)
    cr_client.deploy()

    print("\n== RUN ==\n")

    # run the scripts and get a process back
    # process1  = await cr_client.run_job(cr_client.get_job(0)) 
    # process2  = await cr_client.run_job(cr_client.get_job(1)) 
    # processes = [ process1 , process2 ]
    processes = cr_client.run_jobs()

    print("\n== WAIT ==\n")

    print("Waiting for DONE or ABORTED ...")
    cr_client.wait_for_jobs_state(processes,CloudRunCommandState.DONE|CloudRunCommandState.ABORTED)

    print("\n== GET STATE ==\n")

    # just to show the API ...
    cr_client.get_jobs_states(processes)

    # print("\n== WAIT and TAIL ==\n")

    # task1 = asyncio.create_task(cr_client.wait_for_script_state(CloudRunCommandState.DONE|CloudRunCommandState.ABORTED,script_hash,uid))
    # task2 = asyncio.create_task(tail_loop(script_hash,uid))
    # await asyncio.gather(task1,task2)

    print("\n== DONE ==\n")

# run main loop
def main():

    try:
        sys.path.append(os.path.abspath(os.getcwd()))    
        configModule = __import__("config")
        config = configModule.config
    except ModuleNotFoundError as mfe:
        print("\n\033[91mYou need to create a config.py file (see 'example/config.example.py')\033[0m\n")
        raise mfe

    cr_client = cr.get_client(config)

    asyncio.run( mainloop(cr_client) )