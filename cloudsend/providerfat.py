from abc import ABC , abstractmethod
import cloudsend.utils as cloudsendutils
import sys , json , os , time
import re
#import multiprocessing
import math , random
import cloudsend.combopt as combopt
from io import BytesIO
import csv , io
import pkg_resources
from cloudsend.core import *
from cloudsend.provider import CloudSendProvider , CloudSendProviderState , debug , PROVIDER_CONFIG , DIRECTORY_TMP_AUTO_STOP , DIRECTORY_TMP
from cloudsend.config_state import ConfigManager , StateSerializer , STATE_FILE
from enum import IntFlag
from threading import current_thread
import shutil
import asyncio , asyncssh

random.seed()

SLEEP_PERIOD = 15

class CloudSendProviderStateWaitMode(IntFlag):
    NO_WAIT       = 0  # provider dont wait for state
    WAIT          = 1  # provider wait for state 
    WATCH         = 2  # provider watch out for state = wait + revive

class CloudSendFatProvider(CloudSendProvider,ABC):

    def __init__(self, conf=None):

        # this will call self._init
        CloudSendProvider.__init__(self,conf)

        # will be called by the parent
        #self._init(conf)

    def _init(self,conf):
        super()._init(conf)

        self._instances = []
        self._environments = []
        self._jobs = []
        self._run_sessions = []
        self._current_session = None        

        # load the config
        self._config_manager = ConfigManager(self,self._config,self._instances,self._environments,self._jobs)
        self._config_manager.load()

        # option
        self._mutualize_uploads = conf.get('mutualize_uploads',True)

        self._state_serializer = None
        if self._config.get('recover',False):
            # load the state (if existing) and set the recovery mode accordingly
            self._state_serializer = StateSerializer(self)
            self._state_serializer.load()

            consistency = self._state_serializer.check_consistency(self._state,self._instances,self._environments,self._jobs,self._run_sessions,self._current_session)
            if consistency:
                self.debug(1,"STATE RECOVERY: state is consistent with configuration - LOADING old state",color=bcolors.CVIOLET)
                self._recovery = True
                self._state , self._instances , self._environments , self._jobs , self._run_sessions , self._current_session = self._state_serializer.transfer()
                self.debug(2,self._instances)
                self.debug(2,self._environments)
                self.debug(2,self._jobs)
                self.debug(2,self._run_sessions)
                for job in self._jobs:
                    process = job.get_last_process()
                    self.debug(2,process)
            else:
                self._recovery = False
        else:
            self._recovery = False   

        #self._multiproc_man   = multiprocessing.Manager()
        #self._multiproc_lock  = self._multiproc_man.Lock()
        self._instances_watching = dict()
        self._instances_reviving = dict()

        # watch asyncio future
        self._watcher_task = None
        self._terminate_task = None

        self._save_config() 

    async def _cfg_add_objects(self,conf,method):
        await method(conf)
        self._config_manager.load()    
        self.set_state( self._state & (CloudSendProviderState.NEW|CloudSendProviderState.STARTED))
        if self._state & CloudSendProviderState.STARTED:
            await self.start()

    async def cfg_add_instances(self,conf):
        await self._cfg_add_objects(conf,super().cfg_add_instances)

    async def cfg_add_environments(self,conf):
        await self._cfg_add_objects(conf,super().cfg_add_environments)

    async def cfg_add_jobs(self,conf):
        await self._cfg_add_objects(conf,super().cfg_add_jobs)

    async def cfg_add_config(self,conf):
        await self._cfg_add_objects(conf,super().cfg_add_config)

    async def cfg_reset(self):
        # remove the state file
        if self._state_serializer:
            self._state_serializer.reset()
        elif os.path.isfile(STATE_FILE): # let's always remove it
            try:
                os.remove(STATE_FILE)
            except:
                pass
        # provider reset: remove config file
        await super().cfg_reset()
        # re initialize objects
        self._init(self._config)

    def serialize_state(self):
        if self._config.get('recover',False):
            self._state_serializer.serialize(self._state,self._instances,self._environments,self._jobs,self._run_sessions,self._current_session)

    def set_state(self,value):
        self._state = value
        self.serialize_state()

    # def get_job(self,index):

    #     return self._jobs[index] 

    async def _assign(self):

        if self._recovery == True and self._state & CloudSendProviderState.ASSIGNED:
            assign_jobs = False
            for job in self._jobs:
                if not job.get_instance():
                    assign_jobs = True
                    break
            if not assign_jobs:
                self.debug(1,"STATE RECOVERY: skipping jobs allocation dues to reloaded state...",color=bcolors.CVIOLET)
                return 

        self.set_state(self._state & (CloudSendProviderState.ANY - CloudSendProviderState.ASSIGNED))

        assignation = self._config.get('job_assign','multi_knapsack')

        for instance in self._instances:
            instance.reset_jobs()
        
        # DUMMY algorithm 
        if assignation=='random':
            for job in self._jobs:
                if job.get_instance():
                    self.debug(2,"Job already has an instance",job)
                    continue
                
                instance = random.choice( self._instances )
                
                job.set_instance(instance)
                self.debug(1,"Assigned job " + str(job) )

        # knapsack , 2d packing , bin packing ...
        else: #if assignation is None or assignation=='multi_knapsack':

            combopt.multiple_knapsack_assignation(self._jobs,self._instances)   

        self.set_state( self._state | CloudSendProviderState.ASSIGNED )

        self.serialize_state()         
               
    async def _deploy_instance(self,instance,deploy_states,ssh_conn,ftp_client):

        homedir     = instance.get_home_dir()
        global_path = instance.get_global_dir()
        files_path  = instance.path_join(global_path,'files')
        ready_path  = instance.path_join(global_path,'ready')

        # last file uploaded ...
        re_upload  = await self._test_reupload(instance,ready_path,ssh_conn)

        #created = deploy_states[instance.get_name()].get('created')

        debug(2,"re_upload",re_upload)

        if re_upload:

            self.debug(2,"creating instance's directories ...")
            stdout0, stderr0 = await self._exec_command(ssh_conn,"mkdir -p "+global_path+" "+files_path+" && rm -f "+ready_path)
            self.debug(2,"directories created")

            self.debug(1,"uploading instance's files ... ")

            # upload the install file, the env file and the script file
            ftp_client = await ssh_conn.start_sftp_client()

            # change dir to global dir (should be done once)
            await ftp_client.chdir(global_path)
            for file in ['config.py','bootstrap.sh','run.sh','microrun.sh','state.sh','tail.sh','getpid.sh','reset.sh']:
                await self.sftp_put_remote_file(ftp_client,file) 

            self.debug(1,"Installing PyYAML for newly created instance ...")
            stdout, stderr = await self._exec_command(ssh_conn,"pip install pyyaml")
            self.debug(2,await stdout.read())
            self.debug(2, "Errors")
            self.debug(2,await stderr.read())

            commands = [ 
                # make bootstrap executable
                { 'cmd': "chmod +x "+instance.path_join(global_path,"*.sh"), 'out' : True },              
            ]

            await self._run_ssh_commands(instance,ssh_conn,commands)

            await self.sftp_put_string(ftp_client,'ready',"")

            self.debug(1,"files uploaded.")


        deploy_states[instance.get_name()] = { 'upload' : re_upload } 

    async def _deploy_environments(self,instance,deploy_states,ssh_conn,ftp_client):

        re_upload_inst = deploy_states[instance.get_name()]['upload']

        # scan the instances environment (those are set when assigning a job to an instance)
        #TODO: debug this
        # NOT SURE why we're missing an environment sometimes...
        bootstrap_command = ""

        for environment in instance.get_environments():
        #for environment in self._environments:

            # "deploy" the environment to the instance and get a DeployedEnvironment
            dpl_env  = environment.deploy(instance) 

            self.debug(3,dpl_env.json())

            ready_file = instance.path_join( dpl_env.get_path() , 'ready' )
            re_upload_env = await self._test_reupload(instance,ready_file, ssh_conn)

            re_upload_env_mamba  = False
            re_upload_env_pip    = False
            re_upload_env_aptget = False

            if not re_upload_env:
                if dpl_env.get_config('env_conda') is not None:
                    mamba_test = instance.path_join( instance.get_home_dir() , 'micromamba' , 'envs' , dpl_env.get_name_with_hash() )
                    re_upload_env_mamba = await self._test_reupload(instance,mamba_test, ssh_conn,False)
                    re_upload_env = re_upload_env or re_upload_env_mamba
                if dpl_env.get_config('env_pypi') is not None and dpl_env.get_config('env_conda') is None:
                    venv_test = instance.path_join( instance.get_home_dir() , '.' + dpl_env.get_name_with_hash() )
                    re_upload_env_pip = await self._test_reupload(instance,venv_test, ssh_conn, False)
                    re_upload_env = re_upload_env or re_upload_env_pip
                # TODO: have an aptget install TEST
                #if dpl_env.get_config('env_aptget') is not None:
                #    re_upload_env_aptget = True
                #    re_upload_env = True

            debug(2,"re_upload_instance",re_upload_inst,"re_upload_env",re_upload_env,"re_upload_env_mamba",re_upload_env_mamba,"re_upload_env_pip",re_upload_env_pip,"re_upload_env_aptget",re_upload_env_aptget,"ENV",dpl_env.get_name_with_hash())

            re_upload = re_upload_env #or re_upload_inst

            deploy_states[instance.get_name()][environment.get_name_with_hash()] = { 'upload' : re_upload }

            if re_upload:
                files_path = dpl_env.get_path()
                global_path = instance.get_global_dir() 

                self.debug(2,"creating environment directories ...")
                stdout0, stderr0 = await self._exec_command(ssh_conn,"mkdir -p "+files_path+" && rm -f "+ready_file)
                self.debug(2,"STDOUT for mkdir -p ",files_path,"...",await stdout0.read())
                self.debug(2,"STDERR for mkdir -p ",files_path,"...",await stderr0.read())
                self.debug(2,"directories created")

                self.debug(1,"uploading files ... ")

                # upload the install file, the env file and the script file
                # change to env dir
                await ftp_client.chdir(dpl_env.get_path())
                await self.sftp_put_string(ftp_client,'config.json',dpl_env.json())

                self.debug(1,"uploaded.")        

                print_deploy = self._config.get('print_deploy',False) == True

                config_py = instance.path_join( global_path , 'config.py' )

                commands = [
                    # recreate pip+conda files according to config
                    { 'cmd': "cd " + files_path + " && python3 "+config_py , 'out' : True },
                    # setup envs according to current config files state
                    # FIX: mamba is not handling well concurrency
                    # we run the mamba installs sequentially below
                    #{ 'cmd': instance.path_join( global_path , 'bootstrap.sh' ) + " \"" + dpl_env.get_name_with_hash() + "\" " + ("1" if self._config['dev'] else "0") , 'out': print_deploy , 'output': instance.path_join( dpl_env.get_path() , 'bootstrap._') },  
                ]

                bootstrap_command = bootstrap_command + (" ; " if bootstrap_command else "") + instance.path_join( global_path , 'bootstrap.sh' ) + " \"" + dpl_env.get_name_with_hash() + "\" " + ("1" if self._config['dev'] else "0")

                await self._run_ssh_commands(instance,ssh_conn,commands)
                
        if bootstrap_command:
            gbl_dir = instance.get_global_dir()
            await ftp_client.chdir(gbl_dir)
            await self.sftp_put_string(ftp_client,'generate_envs.sh',bootstrap_command)
            generate_sh = instance.path_join( gbl_dir , 'generate_envs.sh' ) 
            bootstrap_log = instance.path_join( gbl_dir , 'bootstrap.log' )
            commands = [
                {'cmd': 'chmod +x ' + generate_sh , 'out':True}, # import to wait for this to be done !
                {'cmd': generate_sh , 'out':print_deploy, 'output': bootstrap_log }
            ]
            await self._run_ssh_commands(instance,ssh_conn,commands)
        

    async def _deploy_jobs(self,instance,deploy_states,ssh_conn,ftp_client):

        file_uploaded = dict()

        # scan the instances environment (those are set when assigning a job to an instance)
        for job in instance.get_jobs():
            env      = job.get_env()        # get its environment
            dpl_env  = env.deploy(instance) # "deploy" the environment to the instance and get a DeployedEnvironment
            dpl_job  = job.deploy(dpl_env,False) # do not add this dpl_job permanently (only use for utility here)

            input_files = []
            if job.get_config('upload_files'):
                upload_files = job.get_config('upload_files')
                if isinstance(upload_files,str):
                    input_files.append(upload_files)
                else:
                    for upf in upload_files:
                        input_files.append(upf)
            if job.get_config('input_file'):
                input_files.append(job.get_config('input_file'))
            
            mkdir_cmd = ""
            for in_file in input_files:
                local_path , rel_path , abs_path , rel_remote_path , external = self._resolve_dpl_job_paths(in_file,dpl_job)
                dirname = instance.path_dirname(abs_path)
                if dirname:
                    mkdir_cmd = mkdir_cmd + (" && " if mkdir_cmd else "") + "mkdir -p " + dirname 

            self.debug(2,"creating job directories ...")
            stdout0, stderr0 = await self._exec_command(ssh_conn,"mkdir -p "+dpl_job.get_path())
            if mkdir_cmd != "":
                stdout0, stderr0 = await self._exec_command(ssh_conn,mkdir_cmd)
            self.debug(2,"directories created")

            re_upload_env = deploy_states[instance.get_name()][env.get_name_with_hash()]['upload']

            ready_file = instance.path_join( dpl_job.get_path() , 'ready' )
            re_upload = await self._test_reupload(instance,ready_file, ssh_conn)

            self.debug(2,"re_upload_env",re_upload_env,"re_upload",re_upload)

            if re_upload: #or re_upload_env:

                stdout0, stderr0 = await self._exec_command(ssh_conn,"rm -f "+ready_file)

                self.debug(1,"uploading job files ... ",dpl_job.get_hash())

                global_path = instance.get_global_dir()
                files_dir = instance.path_join( global_path , 'files' )

                # change to job hash dir
                await ftp_client.chdir(dpl_job.get_path())
                if job.get_config('run_script'):
                    script_args = job.get_config('run_script').split()
                    script_file = script_args[0]
                    filename = os.path.basename(script_file)
                    try:
                        await ftp_client.put(os.path.abspath(script_file),filename)
                    except:
                        self.debug(1,"You defined a script that is not available",job.get_config('run_script'))

                # NEW ! WE now go to 
                # COMMENT THIS IF YOU WANT TO PUT FILES in relation to the jobs' dir
                if self._mutualize_uploads:
                    await ftp_client.chdir(files_dir)

                if job.get_config('upload_files'):
                    files = job.get_config('upload_files')
                    if isinstance( files,str):
                        files = [ files ] 
                    for upfile in files:
                        local_path , rel_path , abs_path , rel_remote_path , external = self._resolve_dpl_job_paths(upfile,dpl_job)
                                
                        # check if the remote path has already been uploaded ...
                        if abs_path in file_uploaded:
                            self.debug(2,"skipping upload of file",upfile,"for job#",job.get_rank(),"(file has already been uploaded)")
                            continue
                        file_uploaded[abs_path] = True
                        
                        try:
                            try:
                                await ftp_client.put(local_path,rel_remote_path) #os.path.basename(upfile))
                            except Exception as e:
                                self.debug(1,"You defined an upload file that is not available",upfile)
                                self.debug(1,e)
                        except Exception as e:
                            print("Error while uploading file",upfile)
                            print(e)
                if job.get_config('input_file'):

                    local_path , rel_path , abs_path , rel_remote_path , external = self._resolve_dpl_job_paths(job.get_config('input_file'),dpl_job)

                    if abs_path in file_uploaded:
                        self.debug(2,"skipping upload of file",upfile,"for job#",job.get_rank(),"(file has already been uploaded)")
                    else:
                        file_uploaded[abs_path] = True
                        #filename = os.path.basename(job.get_config('input_file'))
                        try:
                            await ftp_client.put(local_path,rel_remote_path) #job.get_config('input_file')) #filename)
                        except:
                            self.debug(1,"You defined an input file that is not available:",job.get_config('input_file'))
                
                # used to check if everything is uploaded
                await ftp_client.chdir(dpl_job.get_path())
                await self.sftp_put_string(ftp_client, 'ready', "")

                self.debug(1,"uploaded.",dpl_job.get_hash())

    async def _deploy_all(self,instance):

        deploy_states = dict()

        deploy_states[instance.get_name()] = { }

        attempts = 0 

        for job in instance.get_jobs():
            self.debug(3,"PROCESS in deploy_all",job.get_last_process())

        while attempts < 5:

            if attempts!=0:
                self.debug(1,"Trying again ...")

            instanceid , ssh_conn , ftp_client = await self._wait_and_connect(instance)

            if ssh_conn is None:
                self.debug(1,"ERROR: could not deploy instance",instance,color=bcolors.FAIL)
                return

            try :

                self.debug(1,"-- deploy instances --")

                await self._deploy_instance(instance,deploy_states,ssh_conn,ftp_client)

                self.debug(1,"-- deploy environments --")

                await self._deploy_environments(instance,deploy_states,ssh_conn,ftp_client)

                self.debug(1,"-- deploy jobs --")

                await self._deploy_jobs(instance,deploy_states,ssh_conn,ftp_client) 

                #ftp_client.close()
                ssh_conn.close()

                break

            except FileNotFoundError as fne:
                self.debug(1,fne)
                self.debug(1,"Filename = ",fne.filename)
                self.debug(1,"Error while deploying")
                #sys.exit() # this only kills the thread
                #os.kill(os.getpid(), signal.SIGINT)
                os._exit(1)
                raise fne

            except Exception as e:
                self.debug(1,e)
                self.debug(1,"Error while deploying")
                #sys.exit() # this only kills the thread
                #os.kill(os.getpid(), signal.SIGINT)
                os._exit(1)
                raise e
            
            attempts = attempts + 1

    # use this to make sure we're not blocking in the generator loop below ...
    # (allow full multithreading)
    async def _start_and_update_and_reset_instance(self,instance,reset):
        self._start_and_update_instance(instance)
        if reset:
           await self.reset_instance(instance)

    

    async def start(self,reset=False):

        if not reset and self._state & CloudSendProviderState.STARTED & self._recovery:
            self.debug(1,"STATE RECOVERY: we're not skipping start() in order to update instance information",color=bcolors.CVIOLET)

        self.set_state( self._state & (CloudSendProviderState.ANY - CloudSendProviderState.STARTED) )

        self._instances_states = dict() 
        self.debug(3,"Starting ...")
        jobs_wait = [ ] 
        for instance in self._instances:
            jobs_wait.append( self._start_and_update_and_reset_instance(instance,reset) )
        await asyncio.gather( * jobs_wait )

        for instance in self._instances:
            if instance.is_invalid():
                self.debug(1,"ERROR: Your configuration is causing an instance to not be created. Please fix.",inst.get_config_DIRTY(),color=bcolors.FAIL)
                sys.exit()

        self.set_state( self._state | CloudSendProviderState.STARTED )

    async def reset_instance(self,instance):
        self.debug(1,'RESETTING instance',instance.get_name())
        instanceid, ssh_conn , ftp_client = await self._wait_and_connect(instance)
        if ssh_conn is not None:
            await self.sftp_put_remote_file(ftp_client,'reset.sh')
            reset_file = instance.path_join( instance.get_home_dir() , 'reset.sh' )
            commands = [
                { 'cmd' : 'chmod +x '+reset_file+' && ' + reset_file , 'out' : True }
            ]
            await self._run_ssh_commands(instance,ssh_conn,commands)
            #ftp_client.close()
            ssh_conn.close()
        self.debug(1,'RESETTING done')    


    async def hard_reset_instance(self,instance):        
        await super().hard_reset_instance(instance)
        await self._deploy_all(instance)

    # GREAT summary
    # https://www.integralist.co.uk/posts/python-asyncio/

    # deploys:
    # - instances files
    # - environments files
    # - shared script files, uploads, inputs ...
    async def deploy(self):

        if not self._state & CloudSendProviderState.STARTED:
            self.debug(1,"Not ready. Call 'start' first",color=bcolors.WARNING)
            return

        if self._state & CloudSendProviderState.DEPLOYED:
            if self._recovery == True:
                self.debug(1,"STATE RECOVERY: skipping deploy due to reloaded state ...",color=bcolors.CVIOLET)
            else:
                self.debug(1,"skipping deploy (already deployed) ...",color=bcolors.OKCYAN)
            return 

        self.set_state( self._state & (CloudSendProviderState.ANY - CloudSendProviderState.DEPLOYED) )

        await self._assign()

        clients = {} 

        for job in self._jobs:
            self.debug(3,"PROCESS in deploy",job.get_last_process())
        
        jobs = []
        for instance in self._instances:
            jobs.append( self._deploy_all(instance) )
        await asyncio.gather( *jobs )

        self.set_state( self._state | CloudSendProviderState.DEPLOYED )

    async def _revive(self,run_session,instance):
        self.debug(1,"REVIVING instance",instance,color=bcolors.OKCYAN)

        jobs_can_be_saved = False
        if instance.get_state()==CloudSendInstanceState.STOPPED or instance.get_state()==CloudSendInstanceState.STOPPING:
            self.debug(1,"Instance is stopping|stopped, we just have to re-start the instance",instance,color=bcolors.OKCYAN)
            jobs_can_be_saved = True
            #self.start_instance(instance)
            await self._wait_for_instance(instance)
            # we also may have to re-deploy (if the instance stopped during WAIT / deployment phase)
            await self._deploy_all(instance)
        else:
            # try restarting it
            self._start_and_update_instance(instance)
            # wait for it
            #no need - deploy is doing this already
            #self._wait_for_instance(instance)
            # re-deploy it
            await self._deploy_all(instance)
        if run_session: 
            await self._run(run_session,instance,jobs_can_be_saved) #will run the jobs for this instance

    def _mark_aborted(self,run_session,instance,state_mask,reason=None):
        if run_session:
            run_session.mark_aborted(instance,state_mask,reason) # mark ABORTED 

    async def get_log(self,process,ssh_conn):
        uid   = process.get_uid()
        job   = process.get_job() # dpl job
        env   = job.get_env() # dpl env
        jhash = job.get_hash()
        path  = env.get_path()
        instance = job.get_instance()
        try:
            run_path = instance.path_join( path , jhash , uid )
            run_log1 = instance.path_join( run_path , 'run-'+uid+'.log' )
            run_log2 = instance.path_join( run_path , 'run.log' )
            stdout , stderr = await self._exec_command(ssh_conn,"cat "+run_log1+' '+run_log2)
            log = await stdout.read()
            return log
        except:
            return None

        # we may not have to do anything:
        # we recovered a state at startup
        # let's make sure the state has "advanced":
        # 1) wait jobs have not aborted
        # 2) queue jobs have not aborted
        # 3) IDLE jobs are ...
        # ...
        # 4) basically the state is > old state ...?

    async def _check_run_state(self,run_session,instance,ssh_conn):
        if instance.get_name() in self._instances_states and self._instances_states[instance.get_name()]['changed']==True:
           self.debug(1,"Instance has changed! States of old jobs should return UNKNOWN and a new batch of jobs will be started",color=bcolors.WARNING)
           #let's just let the following logic do its job ... JOB CENTRIC 
           #return True , False
        
        # we're gonna compare the processes' states of the current 'run_session'
        active_processes_old = run_session.get_active_processes(instance)
        active_processes_new = []
        for p in active_processes_old:
            active_processes_new.append(copy.copy(p))
        do_run = True
        
        # fetch the states for active_processes_new list 
        fetched , ssh_conn = await self.__fetch_states_internal(run_session,instance,active_processes_new,True,ssh_conn)
        do_run = False
        all_done = True
        for process_old in active_processes_old:
            uid = process_old.get_uid()
            process_new = None
            # find the new process equivalent
            for p in active_processes_new:
                if p.get_uid() == uid:
                    process_new = p
                    break
            if process_new is None:
                self.debug(1,"Internal ERROR: process_new is NONE! Should not happen!",color=bcolors.FAIL)
                sys.exit(2)

            state_new = process_new.get_state()
            state_old = process_old.get_state()

            # we found one process that hasn't advanced ...
            # let's just run the jobs ...
            #TODO: improve precision of recovery
            self.debug(2,state_old.name,"vs",state_new.name)
            if state_new!=CloudSendProcessState.DONE and (state_new < state_old or (state_new == CloudSendProcessState.ABORTED or state_old == CloudSendProcessState.ABORTED or state_new == CloudSendProcessState.UNKNOWN or state_old == CloudSendProcessState.UNKNOWN)):
                self.debug(1,"We will run the following job because of an unsatisfying state. Job#",process_new.get_job().get_rank(),"=",process_new.get_state())
                do_run = True
                # do not break cause we want to check all_done properly!
                #break
            all_done = all_done and state_new == CloudSendProcessState.DONE

        if all_done:
            do_run = False

        # it is now time to update the old (memory connected) processes 
        # we've retrieved what we needed and we want to new state to be corrected for future prints
        # this should likely set the states to UNKNOWN if this is a new instance
        # (note: an ABORTED state will not switch to UNKNOWN state - in order to keep the most information)
        fetched , ssh_conn = await self.__fetch_states_internal(run_session,instance,active_processes_old,True,ssh_conn)

        if do_run:
            return True , False , ssh_conn
        else:
            # we return the old ones because those are the ones linked with the memory 
            # the other ones have been separated with copy.copy ...
            return False , all_done , ssh_conn

    async def _ensure_watch(self):
        if not self.is_watching():
            self.debug(1,"Started watching ...")
            await self._watch()



    async def _run_jobs_for_instance(self,run_session,batch,instance,except_done) :

        # we're not coming from revive but we've recovered a state ...
        # if except_done == False and self._recovery == True:
        #     self.debug(1,"STATE RECOVERY: found serialized state: we will not restart jobs that have completed",color=bcolors.CVIOLET)
        #     except_done = True

        instanceid , ssh_conn , ftp_client = await self._wait_and_connect(instance)
        if ssh_conn is None:
            ssh_conn = await self._handle_instance_disconnect(run_session,instance,True,"could not run jobs for instance")
            if ssh_conn is None:
                self.debug(1,"Could not run jobs for instance",instance,color=bcolors.FAIL)
                return 
        
        #if self._recovery:
        if except_done and self._recovery:
            do_run , all_done , ssh_conn = await self._check_run_state(run_session,instance,ssh_conn)
            if not do_run:
                if all_done:
                    self.debug(1,"STATE RECOVERY: skipping run_jobs because the jobs have completed since we left them :) @",instance.get_name(),color=bcolors.CVIOLET)
                else:
                    self.debug(1,"STATE RECOVERY: skipping run_jobs because the jobs have advanced as we left them :) @",instance.get_name(),color=bcolors.CVIOLET)
                return

        global_path = instance.get_global_dir()

        cmd_run     = ""
        cmd_run_pre = "" 
        cmd_pid     = ""

        for job in instance.get_jobs():

            if except_done and job.has_completed():
                continue

            # should literally never happen
            if not job.get_instance():
                debug(1,"The job",job,"has not been assigned to an instance!",color=bcolors.FAIL)
                continue
            
            # FOR NOW
            env      = job.get_env()        # get its environment
            # "deploy" the environment to the instance and get a DeployedEnvironment 
            # note: this has already been done in deploy but it doesnt matter ... 
            #       we dont store the deployed environments, and we base everything on remote state ...
            # NOTE: this could change and we store every thing in memory
            #       but this makes it less robust to states changes (especially remote....)
            dpl_env  = env.deploy(instance)
            # deploy the job (adds)
            dpl_job  = job.deploy(dpl_env)
            # the batch creates the process
            process  = batch.create_process(dpl_job)

            if process is None:
                sys.exit(1)
            
            self.debug(2,process) 

            files_path  = dpl_env.get_path()

            run_path    = instance.path_join( dpl_job.get_path() , process.get_uid() )
            pid_file    = instance.path_join( run_path , 'pid' )
            state_file  = instance.path_join( run_path , 'state' )

            is_first = (cmd_run_pre=="")
            cmd_run_pre = cmd_run_pre + "rm -f " + pid_file + " && "
            cmd_run_pre = cmd_run_pre + "mkdir -p " + run_path + " && "
            if is_first: # first sequential script is waiting for bootstrap to be done by default
                cmd_run_pre = cmd_run_pre + "echo 'wait' > " + state_file + "\n"
            else: # all other scripts will be queued
                cmd_run_pre = cmd_run_pre + "echo 'queue' > " + state_file + "\n"

            uid = process.get_uid()

            ln_command = self._get_ln_command(dpl_job,uid)
            self.debug(2,ln_command)
            if ln_command != "":
                cmd_run_pre = cmd_run_pre + ln_command + "\n"

            run_sh  = instance.path_join( global_path , 'run.sh' )
            run_log = instance.path_join( run_path , 'run-'+uid+'.log' )
            pid_sh  = instance.path_join( global_path , 'getpid.sh' )
            cmd_run = cmd_run + run_sh+" \"" + dpl_env.get_name_with_hash() + "\" \""+dpl_job.get_command()+"\" " + job.get_config('input_file') + " " + job.get_config('output_file') + " " + job.get_hash()+" "+uid+">"+run_log+" 2>&1"
            cmd_run = cmd_run + "\n"
            cmd_pid = cmd_pid + pid_sh + " \"" + pid_file + "\"\n"

        tryagain = True

        while tryagain:

            batch_run_file = instance.path_join( global_path , 'batch_run-'+batch.get_uid()+'.sh')
            batch_pid_file = instance.path_join( global_path , 'batch_pid-'+batch.get_uid()+'.sh')
            try:
                ftp_client = await ssh_conn.start_sftp_client()
                await ftp_client.chdir(global_path)
                await self.sftp_put_string(ftp_client,batch_run_file,cmd_run_pre+cmd_run)
                await self.sftp_put_string(ftp_client, batch_pid_file,cmd_pid)
                # run
                commands = [ 
                    { 'cmd': "chmod +x "+batch_run_file+" "+batch_pid_file, 'out' : True } ,  # important to wait for it >> True !!!
                    # execute main script (spawn) (this will wait for bootstraping)
                    { 'cmd': batch_run_file , 'out' : False } 
                ]
                
                await self._run_ssh_commands(instance,ssh_conn,commands)
                tryagain = False
            except Exception as e:
                self.debug(1,e)
                self.debug(1,"ERROR: the instance is unreachable while sending batch",instance,color=bcolors.FAIL)
                ssh_conn = await self._handle_instance_disconnect(run_session,instance,True,"could not run jobs for instance")
                if ssh_conn is None:
                    return 
                tryagain = True

        ssh_conn.close()

        self.serialize_state()

    # entry point ...
    async def run(self):

        # we were actually still running processes
        # >> let's use the current session that has been loaded
        if self._recovery and self._state & CloudSendProviderState.RUNNING:
            self.debug(1,"STATE RECOVERY: continuing run job ...",color=bcolors.CVIOLET)
            await self._run(self._current_session,None,True,False)
        else:

            if not self._state & CloudSendProviderState.DEPLOYED:
                method_to_call = self._get_method_to_call()
                self.debug(1,"Not ready for run. Call '"+method_to_call+"' first.",color=bcolors.WARNING)
                return

            if self._recovery and self._state & CloudSendProviderState.IDLE:
                self.debug(1,"STATE RECOVERY: jobs have been ran already - about the run again",color=bcolors.CVIOLET)

            # we're gonna create a new run session ... deativate entirely the old one
            if self._current_session:
                self._current_session.deactivate() 

            # create the new session
            number = len(self._run_sessions)
            self._current_session = CloudSendRunSession(number)
            self._run_sessions.append(self._current_session)

            # run the new session
            await self._run(self._current_session)
        
        return self._current_session

    async def _run(self,run_session,instance_filter=None,except_done=False,do_init=True):

        # update the Provider state
        self.set_state( self._state & (CloudSendProviderState.ANY - CloudSendProviderState.RUNNING - CloudSendProviderState.IDLE) )

        if instance_filter:
            instances = [ instance_filter ] 
        else:
            instances = self._instances

        if do_init:
            # we're about the re-run the processes for 'instances'
            # we need to de-activate the processes of the batch on those instances...
            for instance in instances:
                run_session.deactivate(instance)

        # a batch is accross instances, create it now
        # IMPORTANT: create it after de-activation !
        batch = run_session.create_batch()

        # run the jobs on each instances
        jobs = []
        for instance in instances:
            jobs.append( self._run_jobs_for_instance(run_session,batch,instance,except_done) ) 
        await asyncio.gather( *jobs )

        # update the Provider state
        self.set_state( self._state | CloudSendProviderState.RUNNING )

        # Now we can start wathing !
        # NOTE: do not ensure watch at the beginning of run...
        #       not sure why but this causes the GatheringFuture to fail
        await self._ensure_watch()


    def print_jobs_summary(self,run_session=None,instance=None):
        if not self._state & CloudSendProviderState.STARTED:
            self.debug(1,"Not ready to get print jobs. Call 'start' first",color=bcolors.WARNING)
            return

        jobs = instance.get_jobs() if instance is not None else self._jobs
        # the lock is to make sure the prints are not scrambled 
        # when coming back from the instance at the same time ...
        #with self._multiproc_lock:
        self.debug(1,"\n----------------------------------------------------------------------------------------------------------------------------------------------------------")
        if instance:
            self.debug(1,instance.get_name(),instance.get_ip_addr())
        for i,job in enumerate(jobs):
            self.debug(1,"\nJob",job.get_rank(),"=",job.str_simple() if instance else job)
            dpl_jobs = job.get_deployed_jobs()
            for dpl_job in dpl_jobs:
                for process in dpl_job.get_processes():
                    if run_session:
                        session = process.get_batch().get_session()
                        if run_session != session:
                            continue
                    self.debug(1,"|_",process.str_simple())

    async def print_aborted_logs(self,run_session=None,instance=None):
        if not self._state & CloudSendProviderState.STARTED:
            self.debug(1,"Not ready to get logs. Call 'start' first",color=bcolors.WARNING)
            return

        instances = self._instances if instance is None else [ instance ]
        for _instance in instances:
            ssh_conn   = None
            ftp_client = None
            for job in _instance.get_jobs():
                process = job.get_last_process()
                if process is None: # should not really happened but it did while writing code
                    continue
                if process.get_state() == CloudSendProcessState.ABORTED:
                    if run_session:
                        session = process.get_batch().get_session()
                        if run_session != session:
                            continue
                    if not ssh_conn:
                        instanceid , ssh_conn , ftp_client = await self._wait_and_connect(_instance)
                    log = await self.get_log(process,ssh_conn)
                    self.debug(1,"----------------------------------------------------------------------",color=bcolors.WARNING)
                    self.debug(1,"Job #",job.get_rank(),"has ABORTED with errors:",color=bcolors.WARNING)
                    self.debug(1,log,color=bcolors.WARNING)
                    self.debug(1,process,color=bcolors.WARNING)
            if ssh_conn:
                # ftp_client.close()
                ssh_conn.close()   

    async def print_objects(self):
        self.debug(1,"STATE =",self._state)
        self.debug(1,"\nINSTANCES: --------------------")
        for instance in self._instances:
            self.debug(1,instance)
        self.debug(1,"\nENVIRONMENTS: -----------------")
        for env in self._environments:
            self.debug(1,env)
        self.debug(1,"\nJOBS: -------------------------")
        for job in self._jobs:
            self.debug(1,job)

    def _get_method_to_call(self):
        if not self._state   & CloudSendProviderState.STARTED:
            return 'start'
        elif not self._state & CloudSendProviderState.DEPLOYED:
            return 'deploy'
        elif not self._state & CloudSendProviderState.RUNNING:
            return 'run'
        elif not self._state & CloudSendProviderState.ASSIGNED:
            return 'assign'
        else:
            return ''  

    async def clear_results_dir(self,out_dir=None) :

        if out_dir is None:
            out_dir = DIRECTORY_TMP

        if not os.path.isabs(out_dir):
            out_dir = os.path.join(os.getcwd(),out_dir)

        shutil.rmtree(out_dir, ignore_errors=True)   

        out_dir2 = os.path.join(os.getcwd(),DIRECTORY_TMP_AUTO_STOP)
        shutil.rmtree(out_dir2, ignore_errors=True)   
        

    async def fetch_results(self,out_dir=None,run_session=None,use_cached=True):

        if out_dir is None:
            out_dir = DIRECTORY_TMP

        if not os.path.isabs(out_dir):
            out_dir = os.path.join(os.getcwd(),out_dir)

        if not run_session:
            run_session = self._current_session

        if not run_session:
            self.debug(1,"No result to fetch",color=bcolors.WARNING)
            return None

        session_out_dir = self._get_session_out_dir(out_dir,run_session)

        # we've already fetched the results
        if use_cached and os.path.exists(session_out_dir):
            return session_out_dir

        # we've already fetched the results with the auto_stop functionality ...
        auto_dir = self._get_session_out_dir(DIRECTORY_TMP_AUTO_STOP,run_session)
        if not os.path.isabs(auto_dir):
            auto_dir = os.path.join(os.getcwd(),auto_dir)
        if use_cached and os.path.exists(auto_dir):
            return auto_dir

        # special case - we may reach this point with a shallow CloudSendRunSessionProxy object
        # this is to allow the FatClient to search the cache (see above)
        # but we cant go further than that
        if isinstance(run_session,CloudSendRunSessionProxy):
            self.debug(1,"Failed finding session results",color=bcolors.FAIL)
            return None

        #processes = self.get_last_processes()
        processes = run_session.get_ran_processes()

        clients   = dict()

        try:
            shutil.rmtree(session_out_dir, ignore_errors=True)
        except:
            pass
        try:
            os.makedirs(session_out_dir)
        except:
            pass

        for process in processes:

            if process.get_state() != CloudSendProcessState.DONE and process.get_state() != CloudSendProcessState.ABORTED:
                self.debug(2,"Skipping process import",process.get_uid(),process.get_state())
            
            dpl_job  = process.get_job()
            rank     = dpl_job.get_rank()
            instance = dpl_job.get_instance()

            if not instance.get_name() in clients:
                clients[instance.get_name()] = dict()
                instanceid , ssh_conn , ftp_client = await self._wait_and_connect(instance)
                if ssh_conn is not None:
                    #ftp_client = await ssh_conn.start_sftp_client()
                    clients[instance.get_name()] = { 'ssh': ssh_conn , 'ftp' : ftp_client}
                else:
                    self.debug(1,"Skipping instance",instance.get_name(),"(unreachable)",color=bcolors.WARNING)
            else:
                ssh_conn = clients[instance.get_name()]['ssh']
                ftp_client = clients[instance.get_name()]['ftp']
            
            retrys = 0 
            while True:
                try :
                    if process.get_state() == CloudSendProcessState.ABORTED:
                        local_path = os.path.join(session_out_dir,'job_'+str(rank).zfill(3)+'_error.log')
                        log = await self.get_log(process,ssh_conn)
                        try:
                            with open(local_path,'w') as log_file:
                                log_file.write(log)
                        except:
                            pass

                    elif process.get_state() == CloudSendProcessState.DONE:
                        out_file = dpl_job.get_config('output_file') # this file is written for the local machine
                        remote_file_path = instance.path_join( process.get_path() , out_file )
                        directory = instance.path_dirname( remote_file_path )
                        filename  = instance.path_basename( remote_file_path )
                        
                        file_name , file_extension = os.path.splitext(out_file)
                        file_name = file_name.replace(os.sep,'_')
                        #ftp_client.chdir(directory)
                        local_path = os.path.join(session_out_dir,'job_'+str(rank).zfill(3)+'_'+file_name+file_extension)
                        await ftp_client.chdir( directory )
                        try:
                            await ftp_client.get( filename , local_path )   
                        except asyncssh.sftp.SFTPNoSuchFile:
                            self.debug(1,"No file for process",process.get_uid(),"job#",rank,directory,filename,local_path)
                            pass
                    break
                except (OSError, asyncssh.Error):
                    retrys += 1
                    if retrys < 5:
                        await asyncio.sleep(10)
                        instanceid , ssh_conn , ftp_client = await self._wait_and_connect(instance)
                        if ssh_conn is not None:
                            #ftp_client = await ssh_conn.start_sftp_client()
                            clients[instance.get_name()] = { 'ssh': ssh_conn , 'ftp' : ftp_client}
                        else:
                            self.debug(1,"Fetch results: could not wait for instance",instance.get_name(),color=bcolors.FAIL)
                            break
                    else:
                        self.debug(1,"Enough retries. Stop fetching results",color=bcolors.FAIL)
                        break
        
        for client in clients.values():
            #client['ftp'].close()
            client['ssh'].close()

        return session_out_dir

    async def finalize(self):
        if self._watcher_task:
            await self._watcher_task
            # while not self._watcher_task.done():
            #     await asyncio.sleep(SLEEP_PERIOD)

    # this method fetched a "real" RunSession object in memory
    # this is used especially when we use the light client to control a fat client
    # a proxied session is used (shallow object with only an ID and a number)
    # and we need to retrieve a true connected object in memory 
    def get_run_session( self , session_number , session_id ):
        for session in self._run_sessions:
            if session.get_id() == session_id and session.get_number() == session_number:
                return session
        return None

    def get_instance( self , instance_name ):
        for instance in self._instances:
            if instance.get_name() == instance_name:
                return instance
        return None

    def _get_ln_command(self,dpl_job,uid):
        files_to_ln = []
        upload_files = dpl_job.get_config('upload_files')
        lnstr = ""
        instance = dpl_job.get_instance()
        if upload_files:
            for up_file in upload_files:
                files_to_ln.append(up_file)
        if dpl_job.get_config('input_file'):
            files_to_ln.append(dpl_job.get_config('input_file'))
        for upfile in files_to_ln:
            local_path , rel_path , abs_path , rel_remote_path , external = self._resolve_dpl_job_paths(upfile,dpl_job)
            filename    = instance.path_basename(abs_path)
            filedir_abs = instance.path_dirname(abs_path)
            filedir_rel = instance.path_dirname(rel_path)
            if filedir_rel and filedir_rel != instance.path_sep() :
                fulldir   = instance.path_join(dpl_job.get_path() , uid , filedir_rel)
                uploaddir = instance.path_join(dpl_job.get_path() , filedir_rel )
                full_file_path = instance.path_join( fulldir , filename )
                lnstr = lnstr + (" && " if lnstr else "") + "mkdir -p " + fulldir + " && ln -sf " + abs_path + " " +  full_file_path
            else:
                fulldir   = instance.path_join( dpl_job.get_path() , uid )
                fulldir2  = dpl_job.get_path() # let's also put symbolic links by the file itself ... 
                uploaddir = dpl_job.get_path()
                full_file_path  = instance.path_join( fulldir  , filename )
                full_file_path2 = instance.path_join( fulldir2 , filename )
                lnstr = lnstr + (" && " if lnstr else "") + "ln -sf " + abs_path + " " + full_file_path + " && ln -sf " + abs_path + " " + full_file_path2

        return lnstr

    async def _handle_instance_disconnect(self,run_session,instance,do_revive,msg):

        # let the priority to the watching/reviving process (should only be one)
        # this is really just in case ...
        # this is especially for the test below: instance.get_state() == CloudSendInstanceState.RUNNING:
        # we want to make sure that no other process may have re-started (quickly) the instance
        # NOTE: this was relevant when we had *concurrent* and *similar* watch and wait processes
        # not the case anymore.... wait is now leveraging watch
        if not do_revive:
            await asyncio.sleep(SLEEP_PERIOD)
            while self._instances_reviving[instance.get_name()]:
                self.debug(1,"waiting for reviving instance (2)",instance)
                await asyncio.sleep(SLEEP_PERIOD)
        else:
            self._instances_reviving[instance.get_name()] = True

        if self._instances_watching.get(instance.get_name(),False) == False:
            self.debug(1,"We have stopped watching the instance - We won't try to reconnect",color=bcolors.WARNING)
            return None 
            
        try:
            # check the status on the instance with AWS
            self.update_instance_info(instance)
        except Exception as e:
            self.debug(1,e)
            # we likely have an Internet connection problem ...
            # let's just ignore the situation and continue
            self.debug(1,"INTERNET connection error. The process will stop.")
            return None 

        # this is an Internet error
        if instance.get_state() == CloudSendInstanceState.RUNNING:
            ssh_conn = await self._connect_to_instance(instance)
            if ssh_conn is None:
                self.debug(1,"FATAL ERROR(0):",msgs,instance,color=bcolors.FAIL)
                return None 
            self.debug(2,"HANDLE_DISCONNECT: LIKELY INTERNET ERROR?")
            return ssh_conn

        self.debug(1,"ERROR:",msg,instance,color=bcolors.FAIL)
        if run_session:
            if instance.get_state() & (CloudSendInstanceState.STOPPING | CloudSendInstanceState.STOPPED) :
                # mark any type of process as aborted, but DONE
                self._mark_aborted(run_session,instance,CloudSendProcessState.ANY - CloudSendProcessState.DONE,"instance stopped") 
            elif instance.get_state() & (CloudSendInstanceState.TERMINATING | CloudSendInstanceState.TERMINATED):
                # mark any type of process as aborted
                self._mark_aborted(run_session,instance,CloudSendProcessState.ANY,"instance terminated") 
            if do_revive:
                await self._revive(run_session,instance)
        ssh_conn = await self._connect_to_instance(instance)
        if ssh_conn is None:
            self.debug(1,"FATAL ERROR(1):",msgs,instance,color=bcolors.FAIL)

        # free the lock
        if do_revive:
            self._instances_reviving[instance.get_name()] = False 

        return ssh_conn 

    def _compute_jobs_info(self,processes):
        jobsinfo = ""

        for process in processes:
            job         = process.get_job()    # deployed job
            dpl_env     = job.get_env()        # deployed job has a deployed environment
            shash       = job.get_hash()
            uid         = process.get_uid()
            pid         = process.get_pid()
            if jobsinfo:
                jobsinfo = jobsinfo + " " + dpl_env.get_name_with_hash() + " " + str(shash) + " " + str(uid) + " " + str(pid) + " \"" + str(job.get_config('output_file')) + "\""
            else:
                jobsinfo = dpl_env.get_name_with_hash() + " " + str(shash) + " " + str(uid) + " " + str(pid) + " \"" + str(job.get_config('output_file')) + "\""
            
        return jobsinfo 
    
    async def __fetch_states_internal( self, run_session, instance , processes , do_revive , ssh_conn ):

        fetched     = dict()

        # nothing to fetch
        if not processes or len(processes)==0:
            return fetched , ssh_conn
    
        global_path = instance.get_global_dir()
        state_sh    = instance.path_join( global_path , 'state.sh' )
        jobsinfo    = self._compute_jobs_info(processes)
        cmd         =  state_sh + " " + jobsinfo
        
        self.debug(2,"PROCESSES sent for state.sh",processes)
        self.debug(2,"Executing command",cmd)
        
        attempts = 0 
        while True:
            try:
                stdout, stderr = await self._exec_command(ssh_conn,cmd)
                data = await stdout.read()
                break
            except (OSError, asyncssh.Error):
                self.debug(1,"SSH connection error while sending state.sh command")
                ssh_conn = await self._handle_instance_disconnect(run_session,instance,do_revive,"could not get jobs states for instance. SSH connection lost with")
                if ssh_conn is None:
                    return None
                # this is part of a run session we're looking at...
                # lets update the processes and subsequent variables after the error
                if run_session:
                    processes = run_session.get_active_processes(instance)
                    jobsinfo  = self._compute_jobs_info(processes)
                    cmd       =  state_sh + " " + jobsinfo

                attempts += 1
            if attempts > 5:
                self.debug(1,"TOO MANY ATTEMPTS",color=bcolors.FAIL)
                return None                

        for line in data.splitlines():      
            if not line or line.strip()=="":
                break     
            statestr = line.strip() 
            self.debug(2,"State=",statestr,"IP=",instance.get_ip_addr())
            stateinfo = statestr.split(',')
            statestr  = re.sub(r'\([0-9]+\)','',stateinfo[2])
            uid       = stateinfo[0]
            pid       = stateinfo[1]

            process = None
            for p in processes:
                if p.get_uid() == uid:
                    process = p
                    break
            if process is not None:
                fetched[uid] = True
                # we don't have PIDs with batches
                # let's take the opportunity to update it here...
                if process.get_pid() is None and pid != "None":
                    process.set_pid( int(pid) )
                try:
                    state = CloudSendProcessState[statestr.upper()]
                    # let's keep as much history as we know 
                    # ABORTED state has more info than UNKNOWN ...
                    # on a new state recovery, the newly created instance is returining UNKNOWN
                    # but if the maestro witnessed an ABORTED state
                    # we prefer to keep this ...
                    if not (process.get_state() == CloudSendProcessState.ABORTED and state == CloudSendProcessState.UNKNOWN):
                        process.set_state(state)
                    self.debug(2,process)
                    # SUPER IMPORTANT TO TEST with retrieved (remote) state !
                    # if we tested with curernt state we could test against all ABORTED jobs and the wait() function would cancel...
                    # this could potentially happen though
                    # instead, the retrieved state is actually UNKNOWN
                    self.debug(2,'The state is ',uid,state)
                except Exception as e:
                    debug(1,"\nUnhandled state received by state.sh!!!",statestr,"\n")
                    debug(2,e)
                    state = CloudSendProcessState.UNKNOWN
            else:
                debug(2,"Received UID info that was not requested")

        return fetched , ssh_conn

    async def __wait_for_state_internal( self , run_session , instance , job_state , wait_mode , daemon ):

        instance_name = instance.get_name()
        try:

            if wait_mode & CloudSendProviderStateWaitMode.WATCH:
                self._instances_watching[instance_name] = True
                self._instances_reviving[instance_name] = False
            
            ssh_conn = await self._connect_to_instance(instance)

            do_revive = (wait_mode & CloudSendProviderStateWaitMode.WATCH)!=0

            if ssh_conn is None:
                ssh_conn = await self._handle_instance_disconnect(run_session,instance,do_revive,"could not get jobs states for instance")
                if ssh_conn is None:
                    return None

            global_path = instance.get_global_dir() 

            while True:

                # update before
                processes = run_session.get_active_processes(instance)

                fetched , ssh_conn = await self.__fetch_states_internal(run_session,instance,processes,do_revive,ssh_conn)

                # always update the activate processes in case something happened
                processes = run_session.get_active_processes(instance)

                # print job status summary
                if not daemon:
                    self.print_jobs_summary(run_session,instance)

                # all retrived attributes need to be true
                arr_retrieved = [ fetched.get(process.get_uid(),False) for process in processes]
                arr_test      = [ (process.get_state() & job_state)!=0 for process in processes]
                retrieved = all( arr_retrieved )
                tested    = all( arr_test )

                self.debug(2,retrieved,arr_retrieved)
                self.debug(2,tested   ,arr_test     )

                if retrieved and tested :
                    break

                self.serialize_state()

                if wait_mode & CloudSendProviderStateWaitMode.WAIT:
                    try:
                        await asyncio.sleep(SLEEP_PERIOD)
                    except asyncio.exceptions.CancelledError:
                        self.debug(1,"Wait process cancelled",color=bcolors.WARNING)
                else:
                    break

            ssh_conn.close() 

            self.serialize_state()

            if wait_mode & CloudSendProviderStateWaitMode.WATCH:
                self._instances_watching[instance.get_name()] = False        
                any_watching = any( self._instances_watching.values() )
                debug(2,self._instances_watching)

                if not any_watching:
                    self.debug(1,"WATCHING has ended",color=bcolors.OKCYAN)
                    run_session.deactivate()
                    # we mark it specifically as IDLE so we know it's been ran once ... (could be useful)
                    self.set_state(  (CloudSendProviderState.IDLE | self._state) & (CloudSendProviderState.ANY - CloudSendProviderState.WATCHING - CloudSendProviderState.RUNNING) )
                    self.debug(2,"entering IDLE state",self._state)

                # lets wait 1 minutes before stopping
                # this helps with the demo which runs a wait() and a get() sequentially ...
                if self._auto_stop:
                    try:
                        # wait 2 mins so the demo works smoothly 
                        await asyncio.sleep(60*2)
                    except asyncio.CancelledError as cerr:
                        raise cerr
                    try:
                        self.debug(1,"Stopping instance",instance.get_name(),color=bcolors.WARNING)
                        self.stop_instance(instance)
                    except:
                        pass
                    #if not any_watching:
                    #    self.debug(1,"Stopping the fat client (maestro) because all instances have ran the jobs",color=bcolors.WARNING)
                    #    os.system("sudo shutdown -h now")

        except Exception as e:
            # make sure we catch any exception and unlock those variables
            if wait_mode & CloudSendProviderStateWaitMode.WATCH:
                self._instances_watching[instance_name] = False
                self._instances_reviving[instance_name] = False
            raise e

    async def __auto_stop_watch_terminate( self , run_session ):

        while True:

            any_watching = any( self._instances_watching.values() )

            if not any_watching and self._auto_stop:

                await asyncio.sleep( 60 * 60 * 2 ) # wait 2 hours 
                #await asyncio.sleep( 1 ) # wait 1 second (for testing)

                self.debug(1,"Getting results",color=bcolors.WARNING)

                # don't use the cache?
                await self.fetch_results(DIRECTORY_TMP_AUTO_STOP,run_session,False)

                self.debug(1,"Results auto-fetched",color=bcolors.WARNING)

                for instance in run_session.get_instances():

                    self.debug(1,"Terminating instance",instance.get_name(),color=bcolors.WARNING)

                    self.terminate_instance(instance)

                # and stopping the fat client
                self.debug(1,"Stopping the fat client (maestro) because all instances have ran the jobs",color=bcolors.WARNING)
                
                os.system("sudo shutdown -h now")

                # let it do its job
                await asyncio.sleep(2)

                break

            else:            
                
                await asyncio.sleep( SLEEP_PERIOD )
                #await asyncio.sleep( 1 )


    def _get_num_workers(self):
        num_workers = 10
        if self._instances:
            num_workers = len(self._instances)
        return num_workers

    async def __wait_jobs_state( self, run_session , wait_state = CloudSendProviderStateWaitMode.NO_WAIT , job_state = CloudSendProcessState.ANY , daemon = False ):   

        if not run_session:
            return None

        jobs = []
        for instance in self._instances:
            jobs.append( self.__wait_for_state_internal(run_session,instance,job_state,wait_state,daemon) )

        if not daemon:
            await asyncio.gather( *jobs )
        else:
            if wait_state & CloudSendProviderStateWaitMode.WATCH:
                await self._cancel_watch()
                # spawn it ...
                self._watcher_task = asyncio.ensure_future( asyncio.gather( *jobs ) )            
                self.debug(2,self._watcher_task)
                # add the auto_stop coroutine
                self._terminate_task = asyncio.ensure_future(self.__auto_stop_watch_terminate(run_session))
                self.debug(2,self._terminate_task)
                self.debug(2,"Watching ...")
            else:
                asyncio.ensure_future( asyncio.gather( *jobs ) )

            await asyncio.sleep(2) # let it go to the loop
        # done

    async def wakeup(self):
        # if self._state != CloudSendProviderState.WATCHING:
        #     self.debug(1,"Provider was not watching: cancelling automatic wakeup")
        #     return 
        # else:
        if self._recovery:
            if self._state & CloudSendProviderState.STARTED:
                await self.start()
            if self._state & CloudSendProviderState.ASSIGNED:
                await self._assign()
            if self._state & CloudSendProviderState.DEPLOYED:
                await self.deploy()
            # should we have those here ? Or just let watch do it's thing ? 
            # actually, thanks to state recovery, run_jobs should be smart enough to not run DONE jobs again...
            if self._state & CloudSendProviderState.RUNNING:
                await self.run()
        else:
            # self.start()
            # self._assign()
            # self.deploy()
            pass

    async def _cancel_watch(self):
        if self._watcher_task is not None:
            self._watcher_task.cancel()
            try:
                await self._watcher_task
                self._watcher_task = None
            except asyncio.CancelledError:
                pass
        if self._terminate_task is not None:
            self._terminate_task.cancel()
            try:
                await self._terminate_task
                self._terminate_task = None
            except asyncio.CancelledError:
                pass


    def is_watching(self):
        res = self._watcher_task is not None 
        res = res and not self._watcher_task.cancelled() and not self._watcher_task.done() 
        res = res and self._state & CloudSendProviderState.WATCHING 
        return res

    async def _watch(self):

        if not self._state & CloudSendProviderState.STARTED:
            self.debug(1,"Not ready to watch. Call 'start' first",color=bcolors.WARNING)
            return

        job_state = CloudSendProcessState.DONE|CloudSendProcessState.ABORTED
        
        # switch the state to watch mode ... 
        # this will allow to check if the Provider needs to run all methods until watch, on wakeup
        # (no matter the state recovery)
        self.set_state( self._state | CloudSendProviderState.WATCHING )

        await self.__wait_jobs_state(self._current_session , CloudSendProviderStateWaitMode.WAIT|CloudSendProviderStateWaitMode.WATCH,job_state,True)

    async def _wait(self,job_state,run_session,instance):
        while True:

            # with this new in-memory test, we can't run the test while the instance is reviving
            # because the activate processes are being changed ...
            while self._instances_reviving.get(instance.get_name(),False):
                self.debug(1,"waiting for reviving instance (1)",instance)
                await asyncio.sleep(SLEEP_PERIOD)

            self.print_jobs_summary(run_session,instance)

            if not run_session:
                break
            
            test = True 
            for process in run_session.get_active_processes(instance):
                test = test and (process.get_state() & job_state )
            
            if test:
                break
            
            await asyncio.sleep(SLEEP_PERIOD)

    
    async def wait(self,job_state,run_session=None):
        
        await self._ensure_watch()

        # let the watcher fetch the first time states ...
        await asyncio.sleep(1)

        if run_session is None:
            run_session = self._current_session

        # OLD METHOD
        # we used to fetch the same way watch was fetching but this is redundant
        # and it was causing issues between lists of processes etc.
        #return await self.__get_or_wait_jobs_state(CloudSendProviderStateWaitMode.WAIT,job_state)
        
        # NEW METHOD
        jobs = []
        for instance in self._instances:
            jobs.append( self._wait(job_state,run_session,instance) )
        await asyncio.gather( *jobs )

    async def __get_jobs_states_internal(self,run_session,instance):
        instanceid , ssh_conn , ftp_client = await self._wait_and_connect(instance)

        # no recovery here , this is an observation call ... we just fail ...
        if ssh_conn is None:
            self.debug(1,"ERROR: could not get jobs states",instance,color=bcolors.FAIL)
            return

        # let's update the active processes
        processes = run_session.get_active_processes(instance)
        # first argument: run_session = None, so this won't trigger re-runs etc....
        await self.__fetch_states_internal(None,instance,processes,False,ssh_conn)

        # print
        self.print_jobs_summary(run_session,instance)

        ssh_conn.close()


    async def get_jobs_states(self,run_session=None):

        self.debug(2,'Getting Jobs States ...')

        if not self._state & CloudSendProviderState.STARTED:
            self.debug(1,"Not ready to get job states. Call 'start' first")
            return

        if not run_session:
            run_session = self._current_session

        jobs = []
        for instance in self._instances:
            jobs.append( self.__get_jobs_states_internal(run_session,instance) )
        
        await asyncio.gather( *jobs )


    @abstractmethod
    def get_recommended_cpus(self,inst_cfg):
        pass

    @abstractmethod
    def get_cpus_cores(self,inst_cfg):
        pass