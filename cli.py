import cloudrun as cr
import asyncio
from cloudruncore import CloudRunError , CloudRunCommandState

try:
    configModule = __import__("config")
    config = configModule.config
except ModuleNotFoundError as mnfe:
    print("\n\033[91mYou need to create a config.py file (see 'config.example.py')\033[0m\n")
    raise mfe

# get client for AWS
cr_client = cr.get_client(config['provider'])

async def mainloop(config):

    while True:

        state = await cr_client.get_command_state()

        print(state)

        await asyncio.sleep(2)

        if state == CloudRunCommandState.DONE:
            break


# run main loop
asyncio.run( mainloop(config) )
