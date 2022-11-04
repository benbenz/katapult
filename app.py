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

async def mainloop(config):

    print("\n== START ==\n")

    # create the instance
    cr_client.start_instance()

    print("\n== RUN ==\n")
        
    # run the script
    script_hash , uid , pid = await cr_client.run_script() 

    print("\n== WAIT ==\n")

    print("Waiting for DONE or ABORTED ...")
    await cr_client.wait_for_script_state(CloudRunCommandState.DONE|CloudRunCommandState.ABORTED,script_hash,uid)

    print("\n== DONE ==\n")

# run main loop
asyncio.run( mainloop(config) )
