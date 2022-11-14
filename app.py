import cloudrun as cr
import asyncio
from cloudrun import CloudRunCommandState
import traceback

try:
    configModule = __import__("config")
    config = configModule.config
except ModuleNotFoundError as mnfe:
    print("\n\033[91mYou need to create a config.py file (see 'example/config.example.py')\033[0m\n")
    raise mfe

cr_client = cr.get_client(config)

async def tail_loop(script_hash,uid):

    generator = await cr_client.tail(script_hash,uid) 
    #print('\n\n\nwe are here\n\n\n')
    for line in generator:
        print(line)


async def mainloop():

    print("\n== START ==\n")

    # create the instance
    try:
        cr_client.start_instance(cr_client.get_instance())
    except Exception as e:
        traceback.print_exc()
        print("Aborting mainloop()",str(e))
        return

    print("\n== ALLOCATE JOBS ==\n")

    # distribute the jobs on the instances (dummy algo for now)
    cr_client.assign_jobs_to_instances()

    print("\n== DEPLOY ==\n")

    # pre-deploy instance and environments
    await cr_client.deploy()
    print("deployed")

    print("\n== RUN ==\n")

    # run the scripts and get a process back
    process1 = await cr_client.run_job(cr_client.get_job(0)) 
    process2 = await cr_client.run_job(cr_client.get_job(1)) 

    print("\n== WAIT ==\n")

    print("Waiting for DONE or ABORTED ...")
    await cr_client.wait_for_jobs_state(CloudRunCommandState.DONE|CloudRunCommandState.ABORTED,[process1,process2])

    # print("\n== WAIT and TAIL ==\n")

    # task1 = asyncio.create_task(cr_client.wait_for_script_state(CloudRunCommandState.DONE|CloudRunCommandState.ABORTED,script_hash,uid))
    # task2 = asyncio.create_task(tail_loop(script_hash,uid))
    # await asyncio.gather(task1,task2)

    print("\n== DONE ==\n")

# run main loop
asyncio.run( mainloop() )
