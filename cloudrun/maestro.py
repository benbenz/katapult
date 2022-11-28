from cloudrun import provider as cr
import asyncio , os , sys
from cloudrun.core import CloudRunProcessState
import traceback
import json

async def mainloop(cr_client,command):

    if command == 'start':

        cr_client.start()

    elif command == 'allocate':

        cr_client.assign_jobs_to_instances()

    elif command == 'deploy':

        cr_client.deploy()

    elif command == 'run':

        cr_client.run_jobs()
    
    elif command == 'wait':

        cr_client.wait_for_jobs_state(CloudRunProcessState.DONE|CloudRunProcessState.ABORTED)

    elif command == 'get_states':

        cr_client.get_jobs_states()

    elif command == 'print_aborted':

        cr_client.print_aborted_logs()

# run main loop
def main():

    if len(sys.argv)<2:
        print("USAGE: python3 -m cloudrun.maestro CMD [ARGS]")
        sys.exit()

    command = sys.argv[1]

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

    asyncio.run( mainloop(cr_client,command) )

if __name__ == '__main__':
    main()    