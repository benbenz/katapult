from cloudrun import provider as cr
import asyncio , os , sys
from cloudrun.core import CloudRunProcessState
import traceback
import json

async def tail_loop(script_hash,uid):

    generator = await cr_client.tail(script_hash,uid) 
    for line in generator:
        print(line)


async def mainloop(cr_client):

    print("\n== START ==\n")

    # distribute the jobs on the instances (dummy algo for now)
    #cr_client.start(True) # True for reset (usually not necessary - usually for dev purposes)
    cr_client.start() 

    print("\n== ALLOCATE JOBS ==\n")

    # distribute the jobs on the instances (dummy algo for now)
    cr_client.assign()

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
    processes = cr_client.run()

    print("\n== WATCH ==\n")

    processes = cr_client.watch(processes,True) #daemon = True >> no wait

    print("\n== WAIT ==\n")

    print("Waiting for DONE or ABORTED ...")
    # now that we have 'watch' before 'wait' , this will exit instantaneously
    # because watch includes 'wait' mode intrinsiquely
    processes = cr_client.wait_for_jobs_state(CloudRunProcessState.DONE|CloudRunProcessState.ABORTED,processes)

    print("\n== GET STATE ==\n")

    # just to show the API ...
    cr_client.get_jobs_states()

    # print("\n== WAIT and TAIL ==\n")

    # task1 = asyncio.create_task(cr_client.wait_for_script_state(CloudRunProcessState.DONE|CloudRunProcessState.ABORTED,script_hash,uid))
    # task2 = asyncio.create_task(tail_loop(script_hash,uid))
    # await asyncio.gather(task1,task2)
    cr_client.print_aborted_logs()

    print("\n== FETCH RESULTS ==\n")

    cr_client.fetch_results('./tmp')

    print("\n== DONE ==\n")

async def waitloop(cr_client):

    print("\n== START ==\n")

    cr_client.start()

    print("\n== WAIT ==\n")
    
    cr_client.wait_for_jobs_state(CloudRunProcessState.DONE|CloudRunProcessState.ABORTED)

    #rint("Waiting for DONE or ABORTED ...")
    #processes = cr_client.wait_for_jobs_state(CloudRunProcessState.DONE|CloudRunProcessState.ABORTED)

    print("\n== GET STATE ==\n")

    # just to show the API ...
    cr_client.get_jobs_states()
    cr_client.print_aborted_logs()

    print("\n== DONE ==\n")        

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

    command = None
    if len(sys.argv)>1:
        command = sys.argv[1]
    
    if command == 'wait':
        asyncio.run( waitloop(cr_client) )
    else:
        asyncio.run( mainloop(cr_client) )

if __name__ == '__main__':
    main()    