import cloudsend
import asyncio
import sys , subprocess , pkg_resources

if len(sys.argv)<2:
    print("USAGE:\npython3 -m cloudsend.cli CMD [ARGS]\nOR\npoetry run cli CMD [ARGS]")
    sys.exit()

resource_package = 'cloudsend'
resource_path    = '/resources/remote_files/startserver.sh'
with pkg_resources.resource_stream(resource_package, resource_path) as server_sh_file:
    script = server_sh_file.read()
    server_proc  = subprocess.call(script,shell=True)
    print(server_proc)

async def mainloop(cr_client):
    while True:
        await asyncio.sleep(30)    

def main():

    command = None
    if len(sys.argv)>1:
        command = sys.argv[1]

    if command=="wait" and len(sys.argv)<3:
        print("USAGE: python3 -m cloudsend.cli wait UID")
        sys.exit()
    elif command=="getstate" and len(sys.argv)<3:
        print("USAGE: python3 -m cloudsend.cli getstate UID")
        sys.exit()

    asyncio.run( mainloop(cr_client) )

if __name__ == '__main__':
    main()    