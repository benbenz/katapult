from cloudsend import provider as cs
import asyncio , os , sys
from cloudsend.core import CloudSendProcessState
import traceback
import json

async def tail_loop(script_hash,uid):

    generator = await cs_client.tail(script_hash,uid) 
    for line in generator:
        print(line)


async def mainloop(cs_client,reset=False):

    print("\n== START ==\n")

    # distribute the jobs on the instances (dummy algo for now)
    await cs_client.start(reset) 

    # clear the cache
    await cs_client.clear_results_dir()

    print("\n== DEPLOY ==\n")

    # pre-deploy instance , environments and job files
    # it is recommended to wait here allthough run.sh should wait for bootstraping
    # currently, the bootstraping is non-blocking
    # so this will barely wait ... (the jobs will do the waiting ...)
    await cs_client.deploy()

    print("\n== RUN ==\n")

    # run the scripts and get a process back
    run_session = await cs_client.run()

    await cs_client.kill( run_session.get_id() )

    print("\n== WAIT ==\n")

    print("Waiting for DONE or ABORTED ...")
    # now that we have 'watch' before 'wait' , this will exit instantaneously
    # because watch includes 'wait' mode intrinsiquely
    await cs_client.wait(CloudSendProcessState.DONE|CloudSendProcessState.ABORTED)

    print("\n== SUMMARY ==\n")

    # just to show the API ...
    await cs_client.get_jobs_states()

    # print("\n== WAIT and TAIL ==\n")

    await cs_client.print_aborted_logs()

    print("\n== FETCH RESULTS ==\n")

    await cs_client.fetch_results()

    await cs_client.finalize()

    print("\n== DONE ==\n")

async def waitloop(cs_client):

    print("\n== START ==\n")

    await cs_client.start()

    # clear the cache
    await cs_client.clear_results_dir()

    print("\n== WAIT ==\n")
    
    await cs_client.wait(CloudSendProcessState.DONE|CloudSendProcessState.ABORTED)

    print("\n== SUMMARY ==\n")

    # just to show the API ...
    await cs_client.get_jobs_states()
    await cs_client.print_aborted_logs()

    print("\n== FETCH RESULTS ==\n")

    await cs_client.fetch_results()

    # we have to wait for the watcher daemon here
    # otherwise the program will exit and the daemon will have a CancelledError 
    await cs_client.finalize()

    print("\n== DONE ==\n")        

# run main loop
def main():

    if len(sys.argv)<=1:
        print("You need to specify a config file path: config.json or config.py")
        sys.exit(1)
    
    config_file = sys.argv[1]
    cs_client   = cs.get_client(config_file)
    command = None
    if len(sys.argv)>2: 
        command = sys.argv[2]
    
    if command == 'wait':
        asyncio.run( waitloop(cs_client) )
    elif command == 'reset':
        asyncio.run( mainloop(cs_client,True) )
    else:
        asyncio.run( mainloop(cs_client) )

if __name__ == '__main__':
    main()    