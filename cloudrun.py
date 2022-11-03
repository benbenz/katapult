import cloudrun_aws as craws
import asyncio

class CloudRunError(Exception):
    pass

try:
    configModule = __import__("config")
    config = configModule.config
except ModuleNotFoundError as mnfe:
    print("\n\033[91mYou need to create a config.py file (see 'config.example.py')\033[0m\n")
    raise mfe

config['service'] = 'aws'

async def mainloop(config):

    if config['service'] == 'aws':
        # set the debug level for AWS module
        craws.set_debug_level(config['debug'])

        print("\n== START ==\n")

        # create the instance
        craws.start(config)

        print("\n== RUN ==\n")
        
        # run the script
        await craws.run(config) 

    elif config['service'] == 'azure':
        # not implemented yet
        print("\n\nAZURE implementation not done yet\n\n")
        raise CloudRunError()

# run main loop
asyncio.run( mainloop(config) )
