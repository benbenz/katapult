import cloudrun as cr
import asyncio
from cloudrun import CloudRunError , CloudRunProcessState , CloudRunJobRuntimeInfo
import sys

if len(sys.argv)<2:
    print("USAGE:\npython3 -m cloudrun.cli CMD [ARGS]\nOR\npoetry run cli CMD [ARGS]")
    sys.exit()

async def mainloop(cr_client):
    pass    

def main():

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
    command = None
    if len(sys.argv)>1:
        command = sys.argv[1]

    if command=="wait" and len(sys.argv)<3:
        print("USAGE: python3 -m cloudrun.cli wait UID")
        sys.exit()
    elif command=="getstate" and len(sys.argv)<3:
        print("USAGE: python3 -m cloudrun.cli getstate UID")
        sys.exit()
    elif command=="getstate" and len(sys.argv)<3:
        print("USAGE: python3 -m cloudrun.cli tail UID")
        sys.exit()

    asyncio.run( mainloop(cr_client) )

if __name__ == '__main__':
    main()    