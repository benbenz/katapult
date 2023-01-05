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

    #await cs_client.kill( run_session.get_id() )

    print("\n== WAIT ==\n")

    print("Waiting for DONE or ABORTED ...")
    # now that we have 'watch' before 'wait' , this will exit instantaneously
    # because watch includes 'wait' mode intrinsiquely
    await cs_client.wait(CloudSendProcessState.DONE|CloudSendProcessState.ABORTED,run_session)

    print("\n== SUMMARY ==\n")

    # just to show the API ...
    await cs_client.get_jobs_states()

    # print("\n== WAIT and TAIL ==\n")

    await cs_client.print_aborted_logs()

    print("\n== FETCH RESULTS ==\n")

    await cs_client.fetch_results()

    print("\n== FINALIZE ==\n")

    await cs_client.finalize()

    print("\n== DONE ==\n")

async def cliloop(config_file):

    print("\n== START ==\n")

    # you have to call init before start
    os.system("python3 -m cloudsend.cli init "+config_file)
    os.system("python3 -m cloudsend.cli start")

    # clear the cache
    os.system("python3 -m cloudsend.cli clear_results_dir")

    print("\n== DEPLOY ==\n")

    # pre-deploy instance , environments and job files
    # it is recommended to wait here allthough run.sh should wait for bootstraping
    # currently, the bootstraping is non-blocking
    # so this will barely wait ... (the jobs will do the waiting ...)
    os.system("python3 -m cloudsend.cli deploy")

    print("\n== RUN ==\n")

    # run the scripts and get a process back
    os.system("python3 -m cloudsend.cli run")

    #await cs_client.kill( run_session.get_id() )

    print("\n== ADD more ... ==\n")

    if os.path.isfile('config_add.py'):
        print("waiting 30 seconds before adding stuff ...")
        await asyncio.sleep(30)
        print("adding config_add.py")
        os.system("python3 -m cloudsend.cli cfg_add_config config_add.py")
    else:
        print("this step is optional: you need to have a 'config_add.py' file present")

    print("\n== WAIT ==\n")

    print("Waiting for DONE or ABORTED ...")
    # now that we have 'watch' before 'wait' , this will exit instantaneously
    # because watch includes 'wait' mode intrinsiquely
    os.system("python3 -m cloudsend.cli wait")

    print("\n== SUMMARY ==\n")

    # just to show the API ...
    os.system("python3 -m cloudsend.cli get_jobs_states")

    # print("\n== WAIT and TAIL ==\n")

    os.system("python3 -m cloudsend.cli print_aborted_logs")

    print("\n== FETCH RESULTS ==\n")

    os.system("python3 -m cloudsend.cli fetch_results")

    print("\n== FINALIZE ==\n")

    os.system("python3 -m cloudsend.cli finalize")
    # also shutdown the server ...
    os.system("python3 -m cloudsend.cli shutdown")

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

    print("\n== FINALIZE ==\n")

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
    elif command == 'cli':
        asyncio.run( cliloop(config_file) )
    elif command == 'reset':
        asyncio.run( mainloop(cs_client,True) )
    else:
        asyncio.run( mainloop(cs_client) )

if __name__ == '__main__':
    main()    