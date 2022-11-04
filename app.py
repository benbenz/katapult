import cloudrun as cr
import asyncio
from cloudrun import CloudRunCommandState

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
    cr_client.start_instance()

    print("\n== RUN ==\n")
        
    # run the script
    script_hash , uid , pid = await cr_client.run_script() 

    print("\n== WAIT ==\n")

    print("Waiting for DONE or ABORTED ...")
    await cr_client.wait_for_script_state(CloudRunCommandState.DONE|CloudRunCommandState.ABORTED,script_hash,uid)

    # print("\n== WAIT and TAIL ==\n")

    # task1 = asyncio.create_task(cr_client.wait_for_script_state(CloudRunCommandState.DONE|CloudRunCommandState.ABORTED,script_hash,uid))
    # task2 = asyncio.create_task(tail_loop(script_hash,uid))
    # await asyncio.gather(task1,task2)

    print("\n== DONE ==\n")

# run main loop
asyncio.run( mainloop() )
