import cloudrun as cr
import asyncio
from cloudrun import CloudRunError , CloudRunJobState , CloudRunJobRuntimeInfo
import sys

if len(sys.argv)<2:
    print("USAGE: python3 cli.py CMD [ARGS]")
    sys.exit()

command = sys.argv[1]

if command=="wait" and len(sys.argv)<3:
    print("USAGE: python3 cli.py wait UID")
    sys.exit()
elif command=="getstate" and len(sys.argv)<3:
    print("USAGE: python3 cli.py getstate UID")
    sys.exit()
elif command=="getstate" and len(sys.argv)<3:
    print("USAGE: python3 cli.py tail UID")
    sys.exit()

try:
    configModule = __import__("config")
    config = configModule.config
except ModuleNotFoundError as mnfe:
    print("\n\033[91mYou need to create a config.py file (see 'config.example.py')\033[0m\n")
    raise mfe

# get client 
cr_client = cr.get_client(config)

async def tail_loop(process):

    generator = await cr_client.tail(process) 
    for line in generator:
        print(line)

if command=="wait":
    # run main loop
    process = CloudRunProcess( sys.argv[2] )
    asyncio.run( cr_client.wait_for_script_state(CloudRunJobState.DONE|CloudRunJobState.ABORTED,process))
elif command=="getstate":
    process = CloudRunProcess( sys.argv[2] )
    asyncio.run( cr_client.get_script_state(scriptRuntime) )
elif command=="tail":
    process = CloudRunProcess( sys.argv[2] )
    asyncio.run( tail_loop(scriptRuntime) )

