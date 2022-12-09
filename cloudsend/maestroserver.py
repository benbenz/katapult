from cloudsend import provider as cr
import asyncio , os , sys , time
from cloudsend.core import CloudSendProcessState
import traceback
import json
import socket
import asyncio

HOST = 'localhost' #'0.0.0.0' #127.0.0.1' 
PORT = 5000


async def mainloop(ctxt):

    # may be we've just restarted a crashed maestro server process
    # let's test for WATCH state and reach it back again if thats needed
    await ctxt.wakeup()

    server = await asyncio.start_server(ctxt.handle_client, HOST, PORT, reuse_address=True, reuse_port=True)

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    print(f'Serving on {addrs}')

    async with server:
        await server.serve_forever()   

class ByteStreamWriter():

    def __init__(self,writer):
        self.writer = writer 
    
    def write(self,data):
        if isinstance(data,(bytes,bytearray)):
            self.writer.write(data)
        elif isinstance(data,str):
            self.writer.write(data.encode('utf-8'))
        else:
            self.writer.write(str(data,'utf-8').encode('utf-8'))

    async def drain(self):
        await self.writer.drain()

    def close(self):
        self.writer.close()

    def flush(self):
        asyncio.ensure_future( self.writer.drain() )

class ServerContext:
    def __init__(self,config):
        self.cs_client = cr.get_client(config)

    async def wakeup(self):
        await self.cs_client.wakeup()

    async def handle_client(self, reader, writer):
        old_stdout = sys.stdout
        while True:
            try:
                cmd_line = await reader.readline()
                if not cmd_line:
                    break
                cmd_line = cmd_line.decode('utf-8').strip()
                cmd_args = cmd_line.split(':')
                if len(cmd_args)>=2:
                    cmd  = cmd_args[0].strip()
                    args = cmd_args[1].split(',')
                else:
                    cmd  = cmd_line
                    args = None

                await self.process_command(cmd,args,writer)
                break # one-shot command
            except ConnectionResetError as cre:
                try:
                    sys.stdout = old_stdout
                    print(cre)
                    print("DISCONNECTION")
                except:
                    pass
                break    
            except Exception as e:
                try:
                    sys.stdout = old_stdout
                    print(e)
                except:
                    pass
                break  
        try:
            await writer.drain()
        except:
            pass
        try:
            writer.close()
        except:
            pass

    async def process_command(self,command,args,writer):
        #sock = writer.transport.get_extra_info('socket')
        string_writer = ByteStreamWriter(writer)
        sys.stdout = string_writer
        sys.stderr = string_writer
        try:

            if command == 'wakeup':

                await self.cs_client.wakeup()

            elif command == 'start':
                reset = False
                if args:
                    reset = args[0].strip().lower() == "true"
                await self.cs_client.start(reset)

            elif command == 'allocate' or command == 'assign':

                await self.cs_client.assign()

            elif command == 'deploy':

                await self.cs_client.deploy()

            elif command == 'run':

                await self.cs_client.run()
            
            elif command == 'watch':

                daemon = True
                if args:
                    daemon = args[0].strip().lower() == "true"
                await self.cs_client.watch(None,daemon)

            elif command == 'wait':

                await self.cs_client.wait_for_jobs_state(CloudSendProcessState.DONE|CloudSendProcessState.ABORTED)

            elif command == 'get_states':

                await self.cs_client.get_jobs_states()

            elif command == 'print_summary' or command == 'print':

                await self.cs_client.print_jobs_summary()

            elif command == 'print_aborted':

                await self.cs_client.print_aborted_logs()

            elif command == 'fetch_results':

                if args:
                    directory = args[0].strip()
                    await self.cs_client.fetch_results(directory)

            elif command == 'test':

                print("TEST")
            
            else:

                print("UNKNOWN COMMAND")
        
        except Exception as e:
            writer.drain()
            #writer.close()
            raise e

        await writer.drain()
        # to let time for the buffer to be flushed before killing thread and connection
        #time.sleep(1)
        #writer.close()  


# run main loop
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

    #cs_client = cr.get_client(config)
    ctxt = ServerContext(config)

    asyncio.run( mainloop(ctxt) )

if __name__ == '__main__':
    main()    