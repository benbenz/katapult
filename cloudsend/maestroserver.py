from cloudsend import provider as cs
from cloudsend.provider import COMMAND_ARGS_SEP , ARGS_SEP
import asyncio , os , sys , time
from cloudsend.core import CloudSendProcessState , bcolors
import traceback
import json
import socket
import asyncio

HOST = 'localhost' #'0.0.0.0' #127.0.0.1' 
PORT = 5000


async def mainloop(ctxt):

    await ctxt.init()

    server = await asyncio.start_server(ctxt.handle_client, HOST, PORT, reuse_address=True, reuse_port=True)

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    print(f'Serving on {addrs}')

    try:
        async with server:
            await server.serve_forever()   
    except asyncio.CancelledError:
        ctxt.restore_stdio()
        print("Shutting down ...")


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
    def __init__(self,args):
        self.cs_client  = None
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        self.auto_init = any( arg == 'auto_init' for arg in args )

    async def init(self):
        if self.auto_init: # set to True by the crontab in case maestro crashed
            self.cs_client = cs.get_client(None)
            # we've just restarted a crashed maestro server process
            # let's test for WATCH state and reach it back again if thats needed
            await self.wakeup()

    async def wakeup(self):
        await self.cs_client.wakeup()

    async def handle_client(self, reader, writer):
        while True:
            try:
                cmd_line = await reader.readline()
                if not cmd_line:
                    break
                cmd_line = cmd_line.decode('utf-8').strip()
                cmd_args = cmd_line.split(COMMAND_ARGS_SEP)
                if len(cmd_args)>=2:
                    cmd  = cmd_args[0].strip()
                    args = cmd_args[1].split(ARGS_SEP)
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

        if self.cs_client is None:
            if command != 'init' and command != 'shutdown':
                print(bcolors.WARNING+"Server not ready. Run 'init CONFIG_FILE' or 'start' command first"+bcolors.ENDC)
                await writer.drain()
                return 
        try:

            if command == 'init':

                if not args:
                    config_ = None
                elif len(args)==1:
                    config_ = args[0].strip()
                else:
                    config_ = None
                self.cs_client  = cs.get_client(config_)

                await self.wakeup()                

            elif command == 'wakeup':

                await self.cs_client.wakeup()

            elif command == 'start':

                if not args:
                    reset = False
                elif len(args)==1:
                    reset = args[0].strip().lower() == "true"
                else:
                    reset = False

                await self.cs_client.start(reset)

            elif command == 'cfg_add_instances':
                if len(args)==1:
                    config = args[0]
                else:
                    print("Error: you need to send a JSON stream for config")
                    await writer.drain()
                    return
                await self.cs_client.cfg_add_instances(config)

            elif command == 'cfg_add_environments':
                if len(args)==1:
                    config = args[0]
                else:
                    print("Error: you need to send a JSON stream for config")
                    await writer.drain()
                    return
                await self.cs_client.cfg_add_environments(config)

            elif command == 'cfg_add_jobs':
                if len(args)==1:
                    config = args[0]
                else:
                    print("Error: you need to send a JSON stream for config")
                    await writer.drain()
                    return
                await self.cs_client.cfg_add_jobs(config)

            elif command == 'cfg_add_config':
                if len(args)==1:
                    config = json.loads( args[0] )
                else:
                    print("Error: you need to send a JSON stream for config")
                    await writer.drain()
                    return
                await self.cs_client.cfg_add_config(config)

            elif command == 'cfg_reset':

                await self.cs_client.cfg_reset()

            elif command == 'deploy':

                await self.cs_client.deploy()

            elif command == 'run':

                await self.cs_client.run()
            
            elif command == 'wait':

                await self.cs_client.wait(CloudSendProcessState.DONE|CloudSendProcessState.ABORTED)

            elif command == 'get_states':

                await self.cs_client.get_jobs_states()

            elif command == 'print_summary' or command == 'print':

                await self.cs_client.print_jobs_summary()

            elif command == 'print_aborted':

                await self.cs_client.print_aborted_logs()

            elif command == 'print_objects':

                await self.cs_client.print_objects()

            elif command == 'fetch_results':

                if args:
                    directory = args[0].strip()
                    await self.cs_client.fetch_results(directory)

            elif command == 'finalize':
                
                await self.cs_client.finalize()

            elif command == 'shutdown':

                asyncio.get_event_loop().stop()

            elif command == 'test':

                print("TEST")
            
            else:

                print("UNKNOWN COMMAND")
        
        except Exception as e:
            print(e)
            await writer.drain()
            #writer.close()
            self.restore_stdio()
            print(e)
            raise e

        await writer.drain()
        # to let time for the buffer to be flushed before killing thread and connection
        #time.sleep(1)
        #writer.close()  

    def restore_stdio(self):
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr

# run main loop
def main():

    ctxt = ServerContext(sys.argv)

    try:
        asyncio.run( mainloop(ctxt) )
    except RuntimeError:
        pass

if __name__ == '__main__':
    main()    