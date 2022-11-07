import cloudrun as cr
import asyncio
from cloudrun import CloudRunError , CloudRunCommandState , CloudRunScriptRuntimeInfo
import sys

if len(sys.argv)<2:
    print("USAGE: python3 cli.py CMD [ARGS]")
    sys.exit()

command = sys.argv[1]

if command=="wait" and len(sys.argv)<4:
    print("USAGE: python3 cli.py wait SCRIPT_HASH UID")
    sys.exit()
elif command=="getstate" and len(sys.argv)<4:
    print("USAGE: python3 cli.py getstate SCRIPT_HASH UID")
    sys.exit()
elif command=="getstate" and len(sys.argv)<4:
    print("USAGE: python3 cli.py tail SCRIPT_HASH UID")
    sys.exit()

try:
    configModule = __import__("config")
    config = configModule.config
except ModuleNotFoundError as mnfe:
    print("\n\033[91mYou need to create a config.py file (see 'config.example.py')\033[0m\n")
    raise mfe

# get client 
cr_client = cr.get_client(config)

async def tail_loop(scriptRuntimeInfo):

    generator = await cr_client.tail(scriptRuntimeInfo) 
    for line in generator:
        print(line)

if command=="wait":
    # run main loop
    scriptRuntime = CloudRunScriptRuntimeInfo( sys.argv[2],sys.argv[3] )
    asyncio.run( cr_client.wait_for_script_state(CloudRunCommandState.DONE|CloudRunCommandState.ABORTED,scriptRuntime))
elif command=="getstate":
    scriptRuntime = CloudRunScriptRuntimeInfo( sys.argv[2],sys.argv[3] )
    asyncio.run( cr_client.get_script_state(scriptRuntime) )
elif command=="tail":
    scriptRuntime = CloudRunScriptRuntimeInfo( sys.argv[2],sys.argv[3] )
    asyncio.run( tail_loop(scriptRuntime) )

