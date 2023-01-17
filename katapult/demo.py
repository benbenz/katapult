from katapult import provider as kt
import asyncio , os , sys
from katapult.core import KatapultProcessState
import traceback
import json

async def tail_loop(script_hash,uid):

    generator = await kt_client.tail(script_hash,uid) 
    for line in generator:
        print(line)


async def mainloop(kt_client,reset=False):

    print("\n== START ==\n")

    # distribute the jobs on the instances (dummy algo for now)
    await kt_client.start(reset) 

    # clear the cache
    await kt_client.clear_results_dir()

    print("\n== DEPLOY ==\n")

    # pre-deploy instance , environments and job files
    # it is recommended to wait here allthough run.sh should wait for bootstraping
    # currently, the bootstraping is non-blocking
    # so this will barely wait ... (the jobs will do the waiting ...)
    await kt_client.deploy()

    print("\n== RUN ==\n")

    # run the scripts and get a process back
    run_session = await kt_client.run()

    #await kt_client.kill( run_session.get_id() )

    print("\n== WAIT ==\n")

    print("Waiting for DONE or ABORTED ...")
    # now that we have 'watch' before 'wait' , this will exit instantaneously
    # because watch includes 'wait' mode intrinsiquely
    await kt_client.wait(KatapultProcessState.DONE|KatapultProcessState.ABORTED,run_session)

    print("\n== SUMMARY ==\n")

    # just to show the API ...
    await kt_client.get_jobs_states()

    # print("\n== WAIT and TAIL ==\n")

    await kt_client.print_aborted_logs()

    print("\n== FETCH RESULTS ==\n")

    await kt_client.fetch_results()

    print("\n== FINALIZE ==\n")

    await kt_client.finalize()

    print("\n== DONE ==\n")

async def cliloop(config_file):

    print("\n== START ==\n")

    # you have to call init before start
    os.system("python3 -m katapult.cli init "+config_file)
    os.system("python3 -m katapult.cli start")

    # clear the cache
    os.system("python3 -m katapult.cli clear_results_dir")

    print("\n== DEPLOY ==\n")

    # pre-deploy instance , environments and job files
    # it is recommended to wait here allthough run.sh should wait for bootstraping
    # currently, the bootstraping is non-blocking
    # so this will barely wait ... (the jobs will do the waiting ...)
    os.system("python3 -m katapult.cli deploy")

    print("\n== RUN ==\n")

    # run the scripts and get a process back
    os.system("python3 -m katapult.cli run")

    #await kt_client.kill( run_session.get_id() )

    print("\n== ADD more ... ==\n")

    if os.path.isfile('config_add.py'):
        print("waiting 30 seconds before adding stuff ...")
        await asyncio.sleep(30)
        print("adding config_add.py")
        os.system("python3 -m katapult.cli cfg_add_config config_add.py")
    else:
        print("this step is optional: you need to have a 'config_add.py' file present")

    print("\n== WAIT ==\n")

    print("Waiting for DONE or ABORTED ...")
    # now that we have 'watch' before 'wait' , this will exit instantaneously
    # because watch includes 'wait' mode intrinsiquely
    os.system("python3 -m katapult.cli wait")

    print("\n== SUMMARY ==\n")

    # just to show the API ...
    os.system("python3 -m katapult.cli get_jobs_states")

    # print("\n== WAIT and TAIL ==\n")

    os.system("python3 -m katapult.cli print_aborted_logs")

    print("\n== FETCH RESULTS ==\n")

    os.system("python3 -m katapult.cli fetch_results")

    print("\n== FINALIZE ==\n")

    os.system("python3 -m katapult.cli finalize")
    # also shutdown the server ...
    os.system("python3 -m katapult.cli shutdown")

    print("\n== DONE ==\n")    

async def waitloop(kt_client):

    print("\n== START ==\n")

    await kt_client.start()

    # clear the cache
    await kt_client.clear_results_dir()

    print("\n== WAIT ==\n")
    
    await kt_client.wait(KatapultProcessState.DONE|KatapultProcessState.ABORTED)

    print("\n== SUMMARY ==\n")

    # just to show the API ...
    await kt_client.get_jobs_states()
    await kt_client.print_aborted_logs()

    print("\n== FETCH RESULTS ==\n")

    await kt_client.fetch_results()

    print("\n== FINALIZE ==\n")

    # we have to wait for the watcher daemon here
    # otherwise the program will exit and the daemon will have a CancelledError 
    await kt_client.finalize()

    print("\n== DONE ==\n")        

# run main loop
def main():

    if len(sys.argv)<=1:
        print("You need to specify a config file path: config.json or config.py")
        sys.exit(1)
    
    config_file = sys.argv[1]
    kt_client   = kt.get_client(config_file)
    command = None
    if len(sys.argv)>2: 
        command = sys.argv[2]
    
    if command == 'wait':
        asyncio.run( waitloop(kt_client) )
    elif command == 'cli':
        asyncio.run( cliloop(config_file) )
    elif command == 'reset':
        asyncio.run( mainloop(kt_client,True) )
    else:
        asyncio.run( mainloop(kt_client) )

if __name__ == '__main__':
    main()    