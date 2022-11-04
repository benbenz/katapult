import cloudrun as cr
import asyncio

try:
    configModule = __import__("config")
    config = configModule.config
except ModuleNotFoundError as mnfe:
    print("\n\033[91mYou need to create a config.py file (see 'config.example.py')\033[0m\n")
    raise mfe

cr_client = cr.get_client(config)

async def mainloop(config):

    print("\n== START ==\n")

    # create the instance
    cr_client.start_instance()

    print("\n== RUN ==\n")
        
    # run the script
    await cr_client.run_script() 

# run main loop
asyncio.run( mainloop(config) )
