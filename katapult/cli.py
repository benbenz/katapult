import katapult
import asyncio
import sys 
import psutil
import subprocess
import multiprocessing 
import time
import copy
import argparse
import os
import re
from katapult.maestroserver import main as server_main
from katapult.maestroclient import maestro_client
from katapult.provider import make_client_command , stream_dump , get_client , get_vscode_client , get_rundir_client
from katapult.core import KatapultProcessState

# if [[ $(ps aux | grep "katapult.maestroserver" | grep -v 'grep') ]] ; then
#     echo "Katapult server already running"
# else
#     if [[ $(ps -ef | awk '/[m]aestroserver/{print $2}') ]] ; then
#         ps -ef | awk '/[m]aestroserver/{print $2}' | xargs kill 
#     fi
#     echo "Starting Katapult server ..."
#     python3 -u -m katapult.maestroserver
# fi

def katapult_kill(p):
    try:
        p.kill()
    except:
        pass
    try:
        p.terminate()
    except:
        pass

def is_katapult_process(p,name='maestroserver'):
    try:
        if name in p.name():
            return True
        for arg in p.cmdline():
            if name in arg:
                return True
        return False
    except psutil.AccessDenied:
        return False
    except psutil.NoSuchProcess:
        return False

def cli(command):
    start_server() # locally we use python to start the server. maximizes the chance to be Windows complatible
    maestro_client(command)

# basically this: https://dev.to/cindyledev/remote-development-with-visual-studio-code-on-aws-ec2-4cla
# in one CLI ...
async def cli_one_shot(args):

    if args.command == 'vscode':

        kt = get_vscode_client(args)
        await kt.prepare_for_vscode()
        # https://stackoverflow.com/questions/54402104/how-to-connect-ec2-instance-with-vscode-directly-using-pem-file-in-sftp/60305052#60305052
        # https://stackoverflow.com/questions/60144074/how-to-open-a-remote-folder-from-command-line-in-vs-code
        # on OSX:
        # /Applications/Visual\ Studio\ Code.app/Contents/MacOS/Electron --folder-uri=vscode-remote://ubuntu@13.38.11.243/home/ubuntu/
        os.system( "/Applications/Visual\ Studio\ Code.app/Contents/MacOS/Electron")

    elif args.command == 'run_dir':

        kt = get_rundir_client(args)
        await kt.start()
        await kt.deploy()
        await kt.run()
        await kt.wait(KatapultProcessState.DONE|KatapultProcessState.ABORTED)
        await kt.print_aborted_logs()
        dir = await kt.fetch_results()
        print("FETCHED RESULTS ARE in",dir)
    

def start_server():
    server_started = False
    for pid in psutil.pids():
        try:
            p = psutil.Process(pid)
            if is_katapult_process(p,"katapult.maestroserver"):
                print("[Katapult server already started]")
                server_started = True
                break
        except psutil.NoSuchProcess:
            pass
    if not server_started:
        # make sure we kill any rogue processes
        for pid in psutil.pids():
            try:
                p = psutil.Process(pid)
                for pp in p.children(recursive=True):
                    if is_katapult_process(pp):
                        katapult_kill(pp)
                if is_katapult_process(p):
                    katapult_kill(p)
            except psutil.NoSuchProcess:
                pass
        print("[Starting Katapult server ...]")
        subprocess.Popen(['python3','-u','-m','katapult.maestroserver'])
        time.sleep(1)
        #q = multiprocessing.Queue()
        #p = multiprocessing.Process(target=server_main,args=(q,))
        #p = multiprocessing.Process(target=server_main)
        #p.daemon = True
        #p.start()

def cli_translate(args):
    if args.command == 'init':
        return [ args.config ]

    elif args.command == 'wakeup':
        return None

    elif args.command == 'start':
        return [ args.reset ]

    elif args.command == 'cfg_add_instances':
        return [ args.config , json.loads(args.kwargs) if kwargs else {} ]

    elif args.command == 'cfg_add_environments':
        return [ args.config , json.loads(args.kwargs) if kwargs else {} ]

    elif args.command == 'cfg_add_jobs':
        return [ args.config , json.loads(args.kwargs) if kwargs else {} ]

    elif args.command == 'cfg_add_config':
        return [ args.config , json.loads(args.kwargs) if kwargs else {} ]

    elif args.command == 'cfg_reset':
        return [ args.config , json.loads(args.kwargs) if kwargs else {} ]

    elif args.command == 'deploy':
        return [ json.loads(args.kwargs) if kwargs else {} ]

    elif args.command == 'run':
        return [ args.continue_session ]

    elif args.command == 'kill':
        return [ args.identifier ]
    
    elif args.command == 'wait':
        if args.run_session is not None:
            return [ args.job_state , stream_dump( KatapultRunSessionProxy( args.run_session ) ) ]
        else:
            return [ args.job_state ]

    elif args.command == 'get_num_active_processes':
        if args.run_session is not None:
            return [ stream_dump( KatapultRunSessionProxy( args.run_session ) ) ]
        else:
            return None

    elif args.command == 'get_num_instances':
        return None

    elif args.command == 'get_jobs_states':
        argsarr = []
        if args.run_session is not None:
            argsarr.append( stream_dump( KatapultRunSessionProxy(args.run_session) ) )
        if args.last_running_processes is not None:
            argsarr.append(args.last_running_processes)
        return argsarr

    elif args.command == 'print_summary':
        argsarr = []
        if args.run_session is not None:
            argsarr.append( stream_dump( KatapultRunSessionProxy(args.run_session) ) )
        if args.instance is not None:
            argsarr.append( stream_dump( KatapultInstanceProxy(args.instance) ) )
        return argsarr

    elif args.command == 'print_aborted_logs':
        argsarr = []
        if args.run_session is not None:
            argsarr.append( stream_dump( KatapultRunSessionProxy(args.run_session) ) )
        if args.instance is not None:
            argsarr.append( stream_dump( KatapultInstanceProxy(args.instance) ) )
        return argsarr
        
    elif args.command == 'print_objects':
        return None

    elif args.command == 'clear_results_dir':
        return None

    # out_dir=None,run_session=None,use_cached=True,use_normal_output=False
    elif args.command == 'fetch_results':
        argsarr = []
        if args.directory is not None:
            argsarr.append(args.directory)
        if args.run_session is not None:
            argsarr.append( stream_dump( KatapultRunSessionProxy( args.run_session ) ) )
        if args.use_cached is not None:
            argsarr.append( args.use_cached )
        if args.use_normal_output is not None:
            argsarr.append( use_normal_output )
        return argsarr

    elif command == 'finalize':
        return None

    elif command == 'shutdown':
        return None

    elif command == 'test':
        return None

    elif args.command == 'start_instance':
        return [ stream_dump( KatapultInstanceProxy(args.instance) ) ) ]

    elif args.command == 'stop_instance':
        return [ stream_dump( KatapultInstanceProxy(args.instance) ) ) ]

    elif args.command == 'terminate_instance':
        return [ stream_dump( KatapultInstanceProxy(args.instance) ) ) ]

    elif args.command == 'reboot_instance':
        return [ stream_dump( KatapultInstanceProxy(args.instance) ) ) ]

    else:
        return None

def main():
    multiprocessing.set_start_method('spawn')

    argParser = argparse.ArgumentParser(prog = 'katapult.cli',description = 'run Katapult commands',epilog = '--Thanks!')  
    
    #argParser.add_argument('command')
    subparsers = argParser.add_subparsers(dest='command')  
    subparsers.required = True  

    parser_vscode  = subparsers.add_parser('vscode')
    parser_vscode.add_argument("-p", "--profile", help="your aws profile name")
    parser_vscode.add_argument("-t", "--type", help="the aws instance type")
    parser_vscode.add_argument("-r", "--region", help="the aws region")

    parser_run_dir = subparsers.add_parser('run_dir')
    parser_run_dir.add_argument("script_file",help="the (entry) script to run")
    parser_run_dir.add_argument("output_files",help="the output file(s)",default=None)
    parser_run_dir.add_argument("-p", "--profile", help="your aws profile name")
    parser_run_dir.add_argument("-t", "--type", help="the aws instance type")
    parser_run_dir.add_argument("-r", "--region", help="the aws region")

    parser_init = subparsers.add_parser('init')
    parser_init.add_argument("config",help="config file path or config file json string")
    
    parser_wakeup = subparsers.add_parser('wakeup')

    parser_start = subparsers.add_parser('start')
    parser_start.add_argument("-r","--reset",help="reset option",nargs='?',type=bool,const=False)
    
    parser_cfg_add_instances = subparsers.add_parser('cfg_add_instances')
    parser_cfg_add_instances.add_argument("config",help="config file path or config file json string")
    parser_cfg_add_instances.add_argument("-kw","--kwargs",help="a json dictionnary of optional parameters")    

    parser_cfg_add_envs = subparsers.add_parser('cfg_add_environments')
    parser_cfg_add_envs.add_argument("config",help="config file path or config file json string")
    parser_cfg_add_envs.add_argument("-kw","--kwargs",help="a json dictionnary of optional parameters")    

    parser_cfg_add_jobs = subparsers.add_parser('cfg_add_jobs')
    parser_cfg_add_jobs.add_argument("config",help="config file path or config file json string")
    parser_cfg_add_jobs.add_argument("-kw","--kwargs",help="a json dictionnary of optional parameters")    

    parser_cfg_add_config = subparsers.add_parser('cfg_add_config')
    parser_cfg_add_config.add_argument("config",help="config file path or config file json string")
    parser_cfg_add_config.add_argument("-kw","--kwargs",help="a json dictionnary of optional parameters")    

    parser_cfg_reset = subparsers.add_parser('cfg_reset')
    parser_cfg_reset.add_argument("config",help="config file path or config file json string")
    parser_cfg_reset.add_argument("-kw","--kwargs",help="a json dictionnary of optional parameters")    

    parser_deploy = subparsers.add_parser('deploy')
    parser_deploy.add_argument("-kw","--kwargs",help="a json dictionnary of optional parameters")    

    parser_run = subparsers.add_parser('run')
    parser_run.add_argument("-c","--continue_session",nargs='?',const=False,type=bool,help="continue the current running session")    

    parser_run = subparsers.add_parser('kill')
    parser_run.add_argument("identifier",help="id of the object to kill (process, job, session)")    

    parser_wait = subparsers.add_parser('wait')
    parser_wait.add_argument("job_state",help="the value of the job state to wait for (bit to bit)")    
    parser_wait.add_argument("-s","--run_session",help="the run-session's id to wait for")

    parser_numproc = subparsers.add_parser('get_num_active_processes')
    parser_numproc.add_argument("-s","--run_session",help="the run-session's id to wait for")

    parser_numinst = subparsers.add_parser('get_num_instances')

    parser_states = subparsers.add_parser('get_jobs_states')
    parser_states.add_argument("-s","--run_session",help="the run-session's id to get the jobs states for")
    parser_states.add_argument("-l","--last_running_processes",help="only the last running processes",nargs='?',type=bool,const=True)

    parser_printsum = subparsers.add_parser('print_summary')
    parser_printsum.add_argument("-s","--run_session",help="the run-session's to print")
    parser_printsum.add_argument("-i","--instance",help="an instance filter")

    parser_logs = subparsers.add_parser('print_aborted_logs')
    parser_logs.add_argument("-s","--run_session",help="the run-session's to print the aborted logs")
    parser_logs.add_argument("-i","--instance",help="an instance filter")

    parser_printobjs = subparsers.add_parser('print_objects')

    parser_cleardir = subparsers.add_parser('clear_result_dir')

    parser_fetch = subparsers.add_parser('fetch_results')
    parser_fetch.add_argument("-d","--directory",help="the root directory to download the files to")
    parser_fetch.add_argument("-s","--run_session",help="the run-session's to print the aborted logs")
    parser_fetch.add_argument("-c","--use_cached",help="whether to use the results cache or re-download")
    parser_fetch.add_argument("-n","--use_normal_output",help="use original output file names or not")

    parser_finalize = subparsers.add_parser('finalize')

    parser_shutdown = subparsers.add_parser('shutdown')

    parser_test = subparsers.add_parser('test')

    # parser_startinstance = subparsers.add_parser('start_instance')
    # parser_startinstance.add_argument("instance",help="the instance to start")

    # parser_stopinstance = subparsers.add_parser('stop_instance')
    # parser_stopinstance.add_argument("instance",help="the instance to stop")

    # parser_terminateinstance = subparsers.add_parser('terminate_instance')
    # parser_terminateinstance.add_argument("instance",help="the instance to terminate")

    # parser_rebootinstance = subparsers.add_parser('reboot_instance')
    # parser_rebootinstance.add_argument("instance",help="the instance to reboot")

    args = argParser.parse_args()

    # if len(sys.argv)<2:
    #     print("python3 -m katapult.cli CMD [ARGS]")
    #     sys.exit()
    # args = copy.deepcopy(sys.argv)
    # cmd_arg = args.pop(0) #trash
    # while 'cli' not in cmd_arg:
    #     cmd_arg = args.pop(0)
    # command = args.pop(0)
    #one_shot_command = command in [ 'vscode' , 'run_dir' ]
    
    one_shot_command = args.command in [ 'vscode' , 'run_dir' ]

    if one_shot_command:
        asyncio.run( cli_one_shot(args) )
        #asyncio.run( cli_one_shot() )
    else:
        ser_args = cli_translate(args)
        #ser_args = cli_translate(command,args)
        # lets not escape the command, we're not sending it to a stream
        #the_command = make_client_command( command , ser_args , False)
        the_command = make_client_command( args.command , ser_args , False)
        cli(the_command)


if __name__ == '__main__':     
    main()