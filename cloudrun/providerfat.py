from abc import ABC , abstractmethod
import cloudrun.utils as cloudrunutils
import sys , json , os , time
import paramiko
import re
import asyncio
import concurrent.futures
import multiprocessing
import math , random
import cloudrun.combopt as combopt
from io import BytesIO
import csv , io
import pkg_resources
from cloudrun.core import *
from cloudrun.provider import CloudRunProvider , CloudRunProviderState , bcolors , debug
from cloudrun.config_state import ConfigManager , StateSerializer
from enum import IntFlag

random.seed()


class CloudRunProviderStateWaitMode(IntFlag):
    NO_WAIT       = 0  # provider dont wait for state
    WAIT          = 1  # provider wait for state 
    WATCH         = 2  # provider watch out for state = wait + revive

class CloudRunFatProvider(CloudRunProvider,ABC):

    def __init__(self, conf):

        CloudRunProvider.__init__(self,conf)

        # self._load_objects()
        # self._preprocess_jobs()
        # self._sanity_checks()
        self._instances = []
        self._environments = []
        self._jobs = []

        self._multiproc_man  = multiprocessing.Manager()
        self._multiproc_lock = self._multiproc_man.Lock()

        # load the config
        self._config_manager = ConfigManager(self,self._config,self._instances,self._environments,self._jobs)
        self._config_manager.load()

        # option
        self._mutualize_uploads = conf.get('mutualize_uploads',True)

        if self._config.get('recover',False):
            # load the state (if existing) and set the recovery mode accordingly
            self._state_serializer = StateSerializer(self)
            self._state_serializer.load()

            consistency = self._state_serializer.check_consistency(self._state,self._instances,self._environments,self._jobs)
            if consistency:
                self.debug(1,"State is consistent with configuration - LOADING old state")
                self._recovery = True
                self._state , self._instances , self._environments , self._jobs = self._state_serializer.transfer()
                self.debug(2,self._instances)
                self.debug(2,self._environments)
                self.debug(2,self._jobs)
                for job in self._jobs:
                    process = job.get_last_process()
                    self.debug(2,process)
            else:
                self._recovery = False
        else:
            self._recovery = False

    def serialize_state(self):
        if self._config.get('recover',False):
            self._state_serializer.serialize(self._state,self._instances,self._environments,self._jobs)

  
    # def get_job(self,index):

    #     return self._jobs[index] 

    def assign(self):

        if self._recovery == True:
            assign_jobs = False
            for job in self._jobs:
                if not job.get_instance():
                    assign_jobs = True
                    break
            if not assign_jobs:
                self.debug(1,"SKIPPING jobs allocation dues to reloaded state...",color=bcolors.WARNING)
                return 

        assignation = self._config.get('job_assign','multi_knapsack')

        for instance in self._instances:
            instance.reset_jobs()
        
        # DUMMY algorithm 
        if assignation=='random':
            for job in self._jobs:
                if job.get_instance():
                    continue
                
                instance = random.choice( self._instances )
                
                job.set_instance(instance)
                self.debug(1,"Assigned job " + str(job) )

        # knapsack / 2d packing / bin packing ...
        else: #if assignation is None or assignation=='multi_knapsack':

            combopt.multiple_knapsack_assignation(self._jobs,self._instances)   

        self._state = CloudRunProviderState.ALLOCATED            

        self.serialize_state()         
               
    def _deploy_instance(self,instance,deploy_states,ssh_client,ftp_client):

        # last file uploaded ...
        re_upload  = self._test_reupload(instance,"$HOME/run/ready", ssh_client)

        #created = deploy_states[instance.get_name()].get('created')

        debug(2,"re_upload",re_upload)

        if re_upload:

            self.debug(2,"creating instance's directories ...")
            stdin0, stdout0, stderr0 = self._exec_command(ssh_client,"mkdir -p $HOME/run $HOME/run/files && rm -f $HOME/run/ready")
            self.debug(2,"directories created")

            self.debug(1,"uploading instance's files ... ")

            # upload the install file, the env file and the script file
            ftp_client = ssh_client.open_sftp()

            # change dir to global dir (should be done once)
            global_path = "/home/" + instance.get_config('img_username') + '/run/'
            ftp_client.chdir(global_path)
            for file in ['config.py','bootstrap.sh','run.sh','microrun.sh','state.sh','tail.sh','getpid.sh']:
                ftp_client.putfo(self._get_resource_file('remote_files/'+file),file)    

            self.debug(1,"Installing PyYAML for newly created instance ...")
            stdin , stdout, stderr = self._exec_command(ssh_client,"pip install pyyaml")
            self.debug(2,stdout.read())
            self.debug(2, "Errors")
            self.debug(2,stderr.read())

            commands = [ 
                # make bootstrap executable
                { 'cmd': "chmod +x "+global_path+"/*.sh ", 'out' : True },              
            ]

            self._run_ssh_commands(ssh_client,commands)

            ftp_client.putfo(BytesIO("".encode()), 'ready')

            self.debug(1,"files uploaded.")


        deploy_states[instance.get_name()] = { 'upload' : re_upload } 

    def _deploy_environments(self,instance,deploy_states,ssh_client,ftp_client):

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

            re_upload_env = self._test_reupload(instance,dpl_env.get_path_abs()+'/ready', ssh_client)

            re_upload_env_mamba  = False
            re_upload_env_pip    = False
            re_upload_env_aptget = False

            if not re_upload_env:
                if dpl_env.get_config('env_conda') is not None:
                    re_upload_env_mamba = self._test_reupload(instance,'$HOME/micromamba/envs/'+dpl_env.get_name_with_hash(), ssh_client,False)
                    re_upload_env = re_upload_env or re_upload_env_mamba
                if dpl_env.get_config('env_pypi') is not None and dpl_env.get_config('env_conda') is None:
                    re_upload_env_pip = self._test_reupload(instance,'$HOME/.'+dpl_env.get_name_with_hash(), ssh_client, False)
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
                global_path = "$HOME/run" # more robust

                self.debug(2,"creating environment directories ...")
                stdin0, stdout0, stderr0 = self._exec_command(ssh_client,"mkdir -p "+files_path+" && rm -f "+dpl_env.get_path_abs()+'/ready')
                self.debug(2,"STDOUT for mkdir -p ",files_path,"...",stdout0.read())
                self.debug(2,"STDERR for mkdir -p ",files_path,"...",stderr0.read())
                self.debug(2,"directories created")

                self.debug(1,"uploading files ... ")

                # upload the install file, the env file and the script file
                # change to env dir
                ftp_client.chdir(dpl_env.get_path_abs())
                ftp_client.putfo(io.StringIO(dpl_env.json()),'config.json')

                self.debug(1,"uploaded.")        

                print_deploy = self._config.get('print_deploy') == True

                commands = [
                    # recreate pip+conda files according to config
                    { 'cmd': "cd " + files_path + " && python3 "+global_path+"/config.py" , 'out' : True },
                    # setup envs according to current config files state
                    # FIX: mamba is not handling well concurrency
                    # we run the mamba installs sequentially below
                    #{ 'cmd': global_path+"/bootstrap.sh \"" + dpl_env.get_name_with_hash() + "\" " + ("1" if self._config['dev'] else "0") , 'out': print_deploy , 'output': dpl_env.get_path()+'/bootstrap.log'},  
                ]

                bootstrap_command = bootstrap_command + (" ; " if bootstrap_command else "") + global_path+"/bootstrap.sh \"" + dpl_env.get_name_with_hash() + "\" " + ("1" if self._config['dev'] else "0")

                self._run_ssh_commands(ssh_client,commands)
                
                # let bootstrap.sh do it ...
                #ftp_client.putfo(BytesIO("".encode()), 'ready')

        if bootstrap_command:
            ftp_client.chdir('/home/'+instance.get_config('img_username')+'/run')
            ftp_client.putfo(io.StringIO(bootstrap_command),'generate_envs.sh')
            commands = [
                {'cmd': 'chmod +x $HOME/run/generate_envs.sh' , 'out':True}, # import to wait for this to be done !
                {'cmd': '$HOME/run/generate_envs.sh' , 'out':print_deploy, 'output': '$HOME/run/bootstrap.log'}
                #{'cmd': bootstrap_command ,'out': print_deploy , 'output': '$HOME/run/bootstrap.log'}
            ]
            self._run_ssh_commands(ssh_client,commands)
        

    def _deploy_jobs(self,instance,deploy_states,ssh_client,ftp_client):

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
                dirname = os.path.dirname(abs_path)
                if dirname:
                    mkdir_cmd = mkdir_cmd + (" && " if mkdir_cmd else "") + "mkdir -p " + dirname #dpl_job.get_path()+'/'+dirname

            self.debug(2,"creating job directories ...")
            stdin0, stdout0, stderr0 = self._exec_command(ssh_client,"mkdir -p "+dpl_job.get_path())
            if mkdir_cmd != "":
                stdin0, stdout0, stderr0 = self._exec_command(ssh_client,mkdir_cmd)
            self.debug(2,"directories created")

            re_upload_env = deploy_states[instance.get_name()][env.get_name_with_hash()]['upload']
            re_upload = self._test_reupload(instance,dpl_job.get_path()+'/ready', ssh_client)

            self.debug(2,"re_upload_env",re_upload_env,"re_upload",re_upload)

            if re_upload: #or re_upload_env:

                stdin0, stdout0, stderr0 = self._exec_command(ssh_client,"rm -f "+dpl_job.get_path()+'/ready')

                self.debug(1,"uploading job files ... ",dpl_job.get_hash())

                global_path = "$HOME/run" # more robust

                # change to job hash dir
                ftp_client.chdir(dpl_job.get_path())
                if job.get_config('run_script'):
                    script_args = job.get_config('run_script').split()
                    script_file = script_args[0]
                    filename = os.path.basename(script_file)
                    try:
                        ftp_client.put(os.path.abspath(script_file),filename)
                    except:
                        self.debug(1,"You defined a script that is not available",job.get_config('run_script'))

                # NEW ! WE now go to 
                # COMMENT THIS IF YOU WANT TO PUT FILES in relation to the jobs' dir
                if self._mutualize_uploads:
                    ftp_client.chdir('/home/'+str(instance.get_config('img_username'))+'/run/files')

                if job.get_config('upload_files'):
                    files = job.get_config('upload_files')
                    if isinstance( files,str):
                        files = [ files ] 
                    for upfile in files:
                        local_path , rel_path , abs_path , rel_remote_path , external = self._resolve_dpl_job_paths(upfile,dpl_job)
                                
                        # check if the remote path has already been uploaded ...
                        if abs_path in file_uploaded:
                            self.debug(1,"skipping upload of file",upfile,"for job#",job.get_rank(),"(file has already been uploaded)")
                            continue
                        file_uploaded[abs_path] = True
                        
                        try:
                            try:
                                ftp_client.put(local_path,rel_remote_path) #os.path.basename(upfile))
                            except Exception as e:
                                self.debug(1,"You defined an upload file that is not available",upfile)
                                self.debug(1,e)
                        except Exception as e:
                            print("Error while uploading file",upfile)
                            print(e)
                if job.get_config('input_file'):

                    local_path , rel_path , abs_path , rel_remote_path , external = self._resolve_dpl_job_paths(job.get_config('input_file'),dpl_job)

                    if abs_path in file_uploaded:
                        self.debug(1,"skipping upload of file",upfile,"for job#",job.get_rank(),"(file has already been uploaded)")
                    else:
                        file_uploaded[abs_path] = True
                        #filename = os.path.basename(job.get_config('input_file'))
                        try:
                            ftp_client.put(local_path,rel_remote_path) #job.get_config('input_file')) #filename)
                        except:
                            self.debug(1,"You defined an input file that is not available:",job.get_config('input_file'))
                
                # used to check if everything is uploaded
                ftp_client.chdir(dpl_job.get_path())
                ftp_client.putfo(BytesIO("".encode()), 'ready')

                self.debug(1,"uploaded.",dpl_job.get_hash())

    def _deploy_all(self,instance):

        deploy_states = dict()

        deploy_states[instance.get_name()] = { }

        attempts = 0 

        for job in instance.get_jobs():
            self.debug(3,"PROCESS in deploy_all",job.get_last_process())

        while attempts < 5:

            if attempts!=0:
                self.debug(1,"Trying again ...")

            instanceid , ssh_client , ftp_client = self._wait_and_connect(instance)

            if ssh_client is None:
                self.debug(1,"ERROR: could not deploy instance",instance,color=bcolors.FAIL)
                return

            try :

                self.debug(1,"-- deploy instances --")

                self._deploy_instance(instance,deploy_states,ssh_client,ftp_client)

                self.debug(1,"-- deploy environments --")

                self._deploy_environments(instance,deploy_states,ssh_client,ftp_client)

                self.debug(1,"-- deploy jobs --")

                self._deploy_jobs(instance,deploy_states,ssh_client,ftp_client) 

                ftp_client.close()
                ssh_client.close()

                break

            except FileNotFoundError as fne:
                self.debug(1,e)
                self.debug(1,"Filename = ",e.filename)
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

    def start(self):
        self._instances_states = dict() 
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            future_to_instance = { pool.submit(self._start_and_update_instance,instance) : instance for instance in self._instances }
            for future in concurrent.futures.as_completed(future_to_instance):
                inst = future_to_instance[future]
                if inst.is_invalid():
                    self.debug(1,"ERROR: Your configuration is causing an instance to not be created. Please fix.",inst.get_config_DIRTY(),color=bcolors.FAIL)
                    sys.exit()
        self._state = CloudRunProviderState.STARTED


                

    # GREAT summary
    # https://www.integralist.co.uk/posts/python-asyncio/

    # deploys:
    # - instances files
    # - environments files
    # - shared script files / upload / inputs ...
    def deploy(self):

        clients = {} 

        for job in self._jobs:
            self.debug(3,"PROCESS in deploy",job.get_last_process())

        # https://docs.python.org/3/library/concurrent.futures.html cf. ThreadPoolExecutor Example¶
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            future_to_instance = { pool.submit(self._deploy_all,
                                                instance) : instance for instance in self._instances
                                                }
            for future in concurrent.futures.as_completed(future_to_instance):
                inst = future_to_instance[future]
                instanceid = inst.get_id()
                #future.result()
            #pool.shutdown()
        self._state = CloudRunProviderState.DEPLOYED    

    def revive(self,instance,rerun=False):
        self.debug(1,"REVIVING instance",instance)

        jobs_can_be_saved = False
        if instance.get_state()==CloudRunInstanceState.STOPPED or instance.get_state()==CloudRunInstanceState.STOPPING:
            self.debug(1,"Instance is stopping/stopped, we just have to re-start the instance",instance,color=bcolors.OKCYAN)
            jobs_can_be_saved = True
            #self.start_instance(instance)
            self._wait_for_instance(instance)
        else:
            # try restarting it
            self._start_and_update_instance(instance)
            # wait for it
            #no need - deploy is doing this already
            #self._wait_for_instance(instance)
            # re-deploy it
            self._deploy_all(instance)
        if rerun:
            processes = self.run(instance,jobs_can_be_saved) #will run the jobs for this instance
            return processes #instance_processes, jobsinfo 
        else :
            return None 

    def _mark_aborted(self,processes,state_mask):

        for process in processes:
            if process.get_state() & state_mask:
                process.set_state(CloudRunProcessState.ABORTED)

    def get_log(self,process,ssh_client):
        uid   = process.get_uid()
        job   = process.get_job()
        env   = job.get_env()
        jhash = job.get_hash()
        path  = env.get_path()
        try:
            run_path = path+'/'+jhash+'/'+uid
            stdin , stdout , stderr = self._exec_command(ssh_client,"cat "+run_path+'/run-'+uid+'.log '+run_path+'/run.log')
            return stdout.read()
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

    def _check_run_state(self,runinfo):
        instance = runinfo.get('instance')
        if instance.get_name() in self._instances_states and self._instances_states[instance.get_name()]['changed']==True:
           self.debug(1,"Instance has changed! States of old jobs should return UNKNOWN and a new batch of jobs will be started",color=bcolors.WARNING)
           #let's just let the following logic do its job ... JOB CENTRIC 
           #return True , None , False
        last_processes_old = [] 
        last_processes_new = []
        do_run = False
        for job in instance.get_jobs():
            last_process = job.get_last_process()
            if not last_process:
                self.debug(2,"Found a job without process, we should run")
                return True , None , False
            last_processes_new.append(copy.copy(last_process))
            last_processes_old.append(last_process)
       
        instances_processes = self._organize_instances_processes(last_processes_new)
        do_run = True
        if instance.get_name() in instances_processes:
            processes_infos = instances_processes[instance.get_name()]
            last_processes_new = self.__get_jobs_states_internal(processes_infos,CloudRunProviderStateWaitMode.NO_WAIT|CloudRunProviderStateWaitMode.WATCH,CloudRunProcessState.ANY,True) # Programmatic >> no print, no serialize
            do_run = False
            all_done = True
            for process_old in last_processes_old:
                uid = process_old.get_uid()
                process_new = processes_infos[uid]['process']
                state_new = process_new.get_state()
                state_old = process_old.get_state()

                # we found one process that hasn't advanced ...
                # let's just run the jobs ...
                #TODO: improve precision of recovery
                self.debug(2,state_old.name,"vs",state_new.name)
                if state_new!=CloudRunProcessState.DONE and (state_new < state_old or (state_new == CloudRunProcessState.ABORTED or state_old == CloudRunProcessState.ABORTED or state_new == CloudRunProcessState.UNKNOWN or state_old == CloudRunProcessState.UNKNOWN)):
                    self.debug(1,"We will run the following job because of an unsatisfying state. Job#",process_new.get_job().get_rank(),"=",process_new.get_state())
                    do_run = True
                    # do not break cause we want to check all_done properly!
                    #break
                all_done = all_done and state_new == CloudRunProcessState.DONE

            if all_done:
                do_run = False

            # it is now time to update the old (memory connected) processes 
            # we've retrieved what we needed and we want to new state to be corrected for future prints
            # this should likely set the states to ABORTED if this is a new instance
            instances_processes = self._organize_instances_processes(last_processes_old)
            processes_infos = instances_processes[instance.get_name()]
            self.__get_jobs_states_internal(processes_infos,CloudRunProviderStateWaitMode.NO_WAIT|CloudRunProviderStateWaitMode.WATCH,CloudRunProcessState.ANY,True) # Programmatic >> no print, no serialize

            if do_run:
                return True , None, False
            else:
                # we return the old ones because those are the ones linked with the memory 
                # the other ones have been separated with copy.copy ...
                return False , last_processes_old , all_done
        else:
            return True , None , False

    def _run_jobs_for_instance(self,runinfo,batch_uid,dpl_jobs) :
        if self._recovery:
            do_run , processes , all_done = self._check_run_state(runinfo)
            if not do_run:
                instance = runinfo.get('instance')
                if all_done:
                    self.debug(1,"Skipping run_jobs because the jobs have completed since we left them :)",instance,color=bcolors.WARNING)
                else:
                    self.debug(1,"Skipping run_jobs because the jobs have advanced as we left them :)",instance,color=bcolors.WARNING)
                return processes

        global_path = "$HOME/run" # more robust

        tryagain = True

        while tryagain:

            processes = []

            instance = runinfo.get('instance')
            cmd_run  = runinfo.get('cmd_run')
            cmd_run_pre = runinfo.get('cmd_run_pre')
            cmd_pid  = runinfo.get('cmd_pid')
            batch_run_file = 'batch_run-'+batch_uid+'.sh'
            batch_pid_file = 'batch_pid-'+batch_uid+'.sh'
            ssh_client = self._connect_to_instance(instance)
            if ssh_client is None:
                ssh_client , processes = self._handle_instance_disconnect(instance,CloudRunProviderStateWaitMode.WATCH,"could not run jobs for instance")
                if ssh_client is None:
                    return []

            ftp_client = ssh_client.open_sftp()
            ftp_client.chdir('/home/'+instance.get_config('img_username')+'/run')
            ftp_client.putfo(BytesIO(cmd_run_pre.encode()+cmd_run.encode()), batch_run_file)
            ftp_client.putfo(BytesIO(cmd_pid.encode()), batch_pid_file)
            # run
            commands = [ 
                { 'cmd': "chmod +x "+global_path+"/"+batch_run_file+" "+global_path+"/"+batch_pid_file, 'out' : True } ,  # important to wait for it >> True !!!
                # execute main script (spawn) (this will wait for bootstraping)
                { 'cmd': global_path+"/"+batch_run_file , 'out' : False } 
            ]
            
            try:
                self._run_ssh_commands(ssh_client,commands)
                tryagain = False
            except Exception as e:
                self.debug(1,e)
                self.debug(1,"ERROR: the instance is unreachable while sending batch",instance,color=bcolors.FAIL)
                ssh_client , processes = self._handle_instance_disconnect(instance,CloudRunProviderStateWaitMode.WATCH,"could not run jobs for instance")
                if ssh_client is None:
                    return []
                tryagain = True

            for uid in runinfo.get('jobs'):
                # we dont have the pid of everybody yet because its sequential
                # lets leave it blank. it can work with the uid ...
                job = dpl_jobs[uid]
                process = CloudRunProcess( job , uid , None , batch_uid) 
                self.debug(2,process) 
                processes.append(process)

            ssh_client.close()

        self.serialize_state()

        return processes 

    def run(self,instance_filter=None,except_done=False):

        # we're not coming from revive but we've recovered a state ...
        if except_done == False and self._recovery == True:
            self.debug(1,"INFO: found serialized state: we will not restart jobs that have completed",color=bcolors.OKCYAN)
            except_done = True

        instances_runs = dict()

        global_path = "$HOME/run" # more robust

        dpl_jobs = dict()

        jobs = self._jobs if not instance_filter else instance_filter.get_jobs()

        # batch uid is shared accross instances
        batch_uid = cloudrunutils.generate_unique_filename()

        for job in jobs:

            if not job.get_instance():
                debug(1,"The job",job,"has not been assigned to an instance!")
                return None

            instance = job.get_instance()

            #if instance_filter is not None:
            #    if instance is not instance_filter:
            #        continue 
            if except_done and job.has_completed():
                continue

            # CHECK EVERY TIME !
            if not instances_runs.get(instance.get_name()):
                # if wait:
                #     await self._wait_for_instance(instance)
                instances_runs[instance.get_name()] = { 'cmd_run':  "", 'cmd_pid': "" , 'cmd_run_pre':  "", 'instance': instance , 'jobs' : [] }

            cmd_run = instances_runs[instance.get_name()]['cmd_run']
            cmd_pid = instances_runs[instance.get_name()]['cmd_pid']
            cmd_run_pre = instances_runs[instance.get_name()]['cmd_run_pre']

            # FOR NOW
            env      = job.get_env()        # get its environment
            # "deploy" the environment to the instance and get a DeployedEnvironment 
            # note: this has already been done in deploy but it doesnt matter ... 
            #       we dont store the deployed environments, and we base everything on remote state ...
            # NOTE: this could change and we store every thing in memory
            #       but this makes it less robust to states changes (especially remote....)
            dpl_env  = env.deploy(instance)
            dpl_job  = job.deploy(dpl_env)

            files_path  = dpl_env.get_path()

            # generate unique PID file
            uid = cloudrunutils.generate_unique_filename() 

            dpl_jobs[uid] = dpl_job
            instances_runs[instance.get_name()]['jobs'].append(uid)
            
            run_path    = dpl_job.get_path() + '/' + uid
            # retrieve PID (this will wait for PID file)
            pid_file   = run_path + "/pid"
            state_file = run_path + "/state"

            is_first = (cmd_run_pre=="")

            cmd_run_pre = cmd_run_pre + "rm -f " + pid_file + " && "
            cmd_run_pre = cmd_run_pre + "mkdir -p " + run_path + " && "
            if is_first: # first sequential script is waiting for bootstrap to be done by default
                cmd_run_pre = cmd_run_pre + "echo 'wait' > " + state_file + "\n"
            else: # all other scripts will be queued
                cmd_run_pre = cmd_run_pre + "echo 'queue' > " + state_file + "\n"

            ln_command = self._get_ln_command(dpl_job,uid)
            self.debug(2,ln_command)
            if ln_command != "":
                cmd_run_pre = cmd_run_pre + ln_command + "\n"

            #cmd_run = cmd_run + "mkdir -p "+run_path + " && "
            cmd_run = cmd_run + global_path+"/run.sh \"" + dpl_env.get_name_with_hash() + "\" \""+dpl_job.get_command()+"\" " + job.get_config('input_file') + " " + job.get_config('output_file') + " " + job.get_hash()+" "+uid+">"+run_path+"/run-"+uid+".log 2>&1"
            cmd_run = cmd_run + "\n"
            cmd_pid = cmd_pid + global_path+"/getpid.sh \"" + pid_file + "\"\n"

            instances_runs[instance.get_name()]['cmd_run'] = cmd_run
            instances_runs[instance.get_name()]['cmd_pid'] = cmd_pid
            instances_runs[instance.get_name()]['cmd_run_pre'] = cmd_run_pre
        
        processes = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            future_to_instance = { pool.submit(self._run_jobs_for_instance,
                                                runinfo,batch_uid,dpl_jobs) : instance for instance_name , runinfo in instances_runs.items()
                                                }
            for future in concurrent.futures.as_completed(future_to_instance):
                inst = future_to_instance[future]
                #instanceid = inst.get_id()
                #future.result()
                fut_processes = future.result()
                if fut_processes is None:
                    self.debug(1,"An error occured while running the jobs. Process will stop.")
                    return None
                for process in fut_processes:
                    # switch to yield when the wait_for_state method is ready ...
                    #yield process
                    processes.append(process)
            #pool.shutdown()        

        self._state = CloudRunProviderState.RUN

        self.serialize_state()

        return processes 

        
    def run_job(self,job):

        if not job.get_instance():
            debug(1,"The job",job,"has not been assigned to an instance!")
            return None

        instance = job.get_instance()

        # CHECK EVERY TIME !
        # if wait:
        #     await self._wait_for_instance(instance)

        # FOR NOW
        env      = job.get_env()        # get its environment
        # "deploy" the environment to the instance and get a DeployedEnvironment 
        # note: this has already been done in deploy but it doesnt matter ... 
        #       we dont store the deployed environments, and we base everything on remote state ...
        # NOTE: this could change and we store every thing in memory
        #       but this makes it less robust to states changes (especially remote....)
        dpl_env  = env.deploy(instance)
        dpl_job  = job.deploy(dpl_env)

        ssh_client = self._connect_to_instance(instance)

        if ssh_client is None:
            self.debug(1,"ERROR: could not run job for instance",instance,color=bcolors.FAIL)
            return None

        files_path = dpl_env.get_path()
        global_path = "$HOME/run" # more robust

        # generate unique PID file
        uid = cloudrunutils.generate_unique_filename() 
         
        run_path    = dpl_job.get_path() + '/' + uid

        self.debug(1,"creating directories ...")
        stdin0, stdout0, stderr0 = self._exec_command(ssh_client,"mkdir -p "+run_path)
        self.debug(1,"directories created")

        ln_command = self._get_ln_command(dpl_job,uid)
        self.debug(2,ln_command)
        if ln_command != "":
            stdin0, stdout0, stderr0 = self._exec_command(ssh_client,ln_command)
            self.debug(2,stdout0.read())

        # run
        commands = [ 
            # execute main script (spawn) (this will wait for bootstraping)
            { 'cmd': global_path+"/run.sh \"" + dpl_env.get_name_with_hash() + "\" \""+dpl_job.get_command()+"\" " + job.get_config('input_file') + " " + job.get_config('output_file') + " " + job.get_hash()+" "+uid+">"+run_path+"/run-"+uid+".log 2>&1", 'out' : False }
        ]

        self._run_ssh_commands(ssh_client,commands)

        # retrieve PID (this will wait for PID file)
        pid_file = run_path + "/pid"
        getpid_cmd = global_path+"/getpid.sh \"" + pid_file + "\""
         
        self.debug(1,"Executing ",format( getpid_cmd ) )
        stdin , stdout, stderr = self._exec_command(ssh_client,getpid_cmd)
        info = stdout.readline().strip().split(',')
        pid = int(info[1])
        #uid = info[0]

        ssh_client.close()

        process = CloudRunProcess( dpl_job , uid , pid )

        self.debug(1,process) 

        return process


    def print_jobs_summary(self,instance=None):
        jobs = instance.get_jobs() if instance is not None else self._jobs
        # the lock is to make sure the prints are not scrambled 
        # when coming back from the instance at the same time ...
        with self._multiproc_lock:
            self.debug(1,"\n----------------------------------------------------------------------------------------------------------------------------------------------------------")
            if instance:
                self.debug(1,instance.get_name(),instance.get_ip_addr())
            for i,job in enumerate(jobs):
                self.debug(1,"\nJob",job.get_rank(),"=",job.str_simple() if instance else job)
                dpl_jobs = job.get_deployed_jobs()
                for dpl_job in dpl_jobs:
                    for process in dpl_job.get_processes():
                        self.debug(1,"|_",process.str_simple())

    def print_aborted_logs(self,instance=None):
        instances = self._instances if instance is None else [ instance ]
        for _instance in instances:
            ssh_client = self._connect_to_instance(_instance)
            for job in _instance.get_jobs():
                process = job.get_last_process()
                if process.get_state() == CloudRunProcessState.ABORTED:
                    self.debug(1,"----------------------------------------------------------------------",color=bcolors.WARNING)
                    self.debug(1,"Job #",job.get_rank(),"has ABORTED with errors:",color=bcolors.WARNING)
                    self.debug(1,self.get_log(process,ssh_client),color=bcolors.WARNING)
                    self.debug(1,process,color=bcolors.WARNING)
            ssh_client.close()          

    def _get_ln_command(self,dpl_job,uid):
        files_to_ln = []
        upload_files = dpl_job.get_config('upload_files')
        lnstr = ""
        if upload_files:
            for up_file in upload_files:
                files_to_ln.append(up_file)
        if dpl_job.get_config('input_file'):
            files_to_ln.append(dpl_job.get_config('input_file'))
        for upfile in files_to_ln:
            local_path , rel_path , abs_path , rel_remote_path , external = self._resolve_dpl_job_paths(upfile,dpl_job)
            filename    = os.path.basename(abs_path)
            filedir_abs = os.path.dirname(abs_path)
            filedir_rel = os.path.dirname(rel_path)
            if filedir_rel and filedir_rel != '/':
                fulldir   = os.path.join(dpl_job.get_path() , uid , filedir_rel)
                uploaddir = os.path.join(dpl_job.get_path() , filedir_rel )
                #lnstr = lnstr + (" && " if lnstr else "") + "mkdir -p " + fulldir + " && ln -sf " + uploaddir + '/' + filename + " " + fulldir + '/' + filename
                lnstr = lnstr + (" && " if lnstr else "") + "mkdir -p " + fulldir + " && ln -sf " + abs_path + " " + fulldir + '/' + filename
            else:
                fulldir   = os.path.join( dpl_job.get_path() , uid )
                uploaddir = dpl_job.get_path()
                #lnstr = lnstr + (" && " if lnstr else "") + "ln -sf " + uploaddir + '/' + filename + " " + fulldir + '/' + filename
                lnstr = lnstr + (" && " if lnstr else "") + "ln -sf " + abs_path + " " + fulldir + '/' + filename

        return lnstr

    def _handle_instance_disconnect(self,instance,wait_mode,msg,processes=None):
        try:
            # check the status on the instance with AWS
            self.update_instance_info(instance)
        except Exception as e:
            self.debug(1,e)
            # we likely have an Internet connection problem ...
            # let's just ignore the situation and continue
            self.debug(1,"INTERNET connection error. The process will stop.")
            return None , None

        # this is an Internet error
        if instance.get_state() == CloudRunInstanceState.RUNNING:
            ssh_client = self._connect_to_instance(instance,timeout=10)
            if ssh_client is None:
                self.debug(1,"FATAL ERROR(0):",msgs,instance,color=bcolors.FAIL)
                return None , None
            return ssh_client , None


        self.debug(1,"ERROR:",msg,instance,color=bcolors.FAIL)
        if processes is not None:
            if instance.get_state() & (CloudRunInstanceState.STOPPING | CloudRunInstanceState.STOPPED) :
                # mark any type of process as aborted, but DONE
                self._mark_aborted(processes,CloudRunProcessState.ANY - CloudRunProcessState.DONE) 
            elif instance.get_state() & (CloudRunInstanceState.TERMINATING | CloudRunInstanceState.TERMINATED):
                # mark any type of process as aborted
                self._mark_aborted(processes,CloudRunProcessState.ANY) 
        rerun_jobs = processes is not None
        if wait_mode & CloudRunProviderStateWaitMode.WATCH:
            processes = self.revive(instance,rerun_jobs)
        ssh_client = self._connect_to_instance(instance,timeout=10)
        if ssh_client is None:
            self.debug(1,"FATAL ERROR(1):",msgs,instance,color=bcolors.FAIL)
        return ssh_client , processes #processes_info , jobsinfo

    def _recompute_jobs_info(self,instance,processes):
        instances_processes = self._organize_instances_processes(processes)
        instance_processes  = instances_processes[instance.get_name()]
        jobsinfo , instance = self._compute_jobs_info(instance_processes)
        return instance_processes , jobsinfo 


    def _compute_jobs_info(self,processes_infos):
        jobsinfo = ""

        for uid , process_info in processes_infos.items():
            process     = process_info['process']
            job         = process.get_job()    # deployed job
            dpl_env     = job.get_env()        # deployed job has a deployed environment
            shash       = job.get_hash()
            uid         = process.get_uid()
            pid         = process.get_pid()
            if jobsinfo:
                jobsinfo = jobsinfo + " " + dpl_env.get_name_with_hash() + " " + str(shash) + " " + str(uid) + " " + str(pid) + " \"" + str(job.get_config('output_file')) + "\""
            else:
                jobsinfo = dpl_env.get_name_with_hash() + " " + str(shash) + " " + str(uid) + " " + str(pid) + " \"" + str(job.get_config('output_file')) + "\""
            
            instance    = job.get_instance() # should be the same for all jobs
        
        return jobsinfo , instance

    def __get_jobs_states_internal( self , processes_infos , wait_mode , job_state , programmatic = False):
        
        jobsinfo , instance = self._compute_jobs_info(processes_infos)

        ssh_client = self._connect_to_instance(instance,timeout=10)

        if ssh_client is None:
            ssh_client , processes = self._handle_instance_disconnect(instance,wait_mode,"could not get jobs states for instance",
                                            [processes_infos[uid]['process'] for uid in processes_infos])
            if ssh_client is None:
                return 
            
            if processes is not None:
                processes_infos , jobsinfo = self._recompute_jobs_info(instance,processes)

        global_path = "$HOME/run"

        processes = []

        while True:

            if not ssh_client.get_transport().is_active():
                ssh_client , processes = self._handle_instance_disconnect(instance,wait_mode,"could not get jobs states for instance. SSH connection lost with",
                                                [processes_infos[uid]['process'] for uid in processes_infos])
                if ssh_client is None:
                    return None
                
                if processes is not None:
                    processes_infos , jobsinfo = self._recompute_jobs_info(instance,processes)

                processes = []

            cmd = global_path + "/state.sh " + jobsinfo
            self.debug(2,"Executing command",cmd)
            try:
                stdin, stdout, stderr = self._exec_command(ssh_client,cmd)
            except Exception as e:
                self.debug(1,"SSH connection error while sending state.sh command")
                ssh_client , processes = self._handle_instance_disconnect(instance,wait_mode,"could not get jobs states for instance. SSH connection lost with",
                                                [processes_infos[uid]['process'] for uid in processes_infos])
                if ssh_client is None:
                    return None
                if processes is not None: # if processes have changed due to restart
                    processes_infos , jobsinfo = self._recompute_jobs_info(instance,processes)
                    cmd = global_path + "/state.sh " + jobsinfo
                
                # try one more time to re-run the command ...
                stdin, stdout, stderr = self._exec_command(ssh_client,cmd)

                processes = []

            while True: 
                lines = stdout.readlines()
                for line in lines:           
                    statestr = line.strip() #line.decode("utf-8").strip()
                    self.debug(2,"State=",statestr,"IP=",instance.get_ip_addr())
                    stateinfo = statestr.split(',')
                    statestr  = re.sub(r'\([0-9]+\)','',stateinfo[2])
                    uid       = stateinfo[0]
                    pid       = stateinfo[1]

                    if uid in processes_infos:
                        process = processes_infos[uid]['process']

                        # we don't have PIDs with batches
                        # let's take the opportunity to update it here...
                        if process.get_pid() is None and pid != "None":
                            process.set_pid( int(pid) )
                        try:
                            state = CloudRunProcessState[statestr.upper()]
                            process.set_state(state)
                            self.debug(2,process)
                            processes_infos[uid]['retrieved'] = True
                            processes_infos[uid]['test']      = job_state & state 
                        except Exception as e:
                            debug(1,"\nUnhandled state received by state.sh!!!",statestr,"\n")
                            debug(2,e)
                            state = CloudRunProcessState.UNKNOWN

                        processes.append(process)

                    else:
                        debug(2,"Received UID info that was not requested")

                if lines is None or len(lines)==0:
                    break

            # print job status summary
            if not programmatic:
                self.print_jobs_summary(instance)

            # all retrived attributes need to be true
            retrieved = all( [ pinfo['retrieved'] for pinfo in processes_infos.values()] )

            if retrieved and all( [ pinfo['test'] for pinfo in processes_infos.values()] ) :
                break

            if not programmatic:
                self.serialize_state()

            if wait_mode & CloudRunProviderStateWaitMode.WAIT:
                #await asyncio.sleep(15)
                time.sleep(15)
            else:
                break

        ssh_client.close() 

        # this should not be necessary but it sometimes seems it needs to be there
        # TODO: debug why ...
        if not programmatic:
            self.serialize_state()

        return processes

    def get_last_processes(self):
        processes = []
        for job in self._jobs:
            processes.append( job.get_last_process())
        return processes

    def _organize_instances_processes( self , processes ):
        instances_processes = dict()
        #instances_list      = dict()
        for process in processes:
            if process is None:
                continue
            job         = process.get_job()   # deployed job
            instance    = job.get_instance()
            if instance is None:
                print("wait_for_job_state: instance is not available!")
                return 
            # initialize the collection dict
            if instance.get_name() not in instances_processes:
                instances_processes[instance.get_name()] = dict()
                #instances_list[instance.get_name()]      = instance
            if process.get_uid() not in instances_processes[instance.get_name()]:
                instances_processes[instance.get_name()][process.get_uid()] = { 'process' : process , 'retrieved' : False  , 'test' : False }
        return instances_processes


    def __get_or_wait_jobs_state( self, processes , wait_state = CloudRunProviderStateWaitMode.NO_WAIT , job_state = CloudRunProcessState.ANY ):   

        if processes is None: 
            processes = self.get_last_processes()

        if processes and not isinstance(processes,list):
            processes = [ processes ]

        instances_processes = self._organize_instances_processes(processes)

        processes = [] 

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            future_to_instance = { pool.submit(self.__get_jobs_states_internal,
                                                processes_infos,wait_state,job_state) : instance_name for instance_name , processes_infos in instances_processes.items()
                                                }
            for future in concurrent.futures.as_completed(future_to_instance):
                inst_name = future_to_instance[future]
                #instanceid = inst.get_id()
                #future.result()
                fut_processes = future.result()
                if fut_processes is not None:
                    for p in fut_processes:
                        processes.append(p)
                else:
                    self.debug(1,"There has been a problem with __get_jobs_states_internal")
            #pool.shutdown()
        
        return processes
        # done

    def wakeup(self):
        if self._state != CloudRunProviderState.WATCH:
            self.debug(1,"Provider was not watching: cancelling automatic wakeup")
            return 
        else:
            self.start()
            self.assign()
            self.deploy()
            self.run()
            self.watch()

    def watch(self,processes=None):

        if not processes or len(processes)==0:
            self.debug(1,"No process to wait for")
        job_state = CloudRunProcessState.DONE|CloudRunProcessState.ABORTED
        
        # switch the state to watch mode ... 
        # this will allow to check if the Provider needs to run all methods until watch, on wakeup
        # (no matter the state recovery)
        self._state = CloudRunProviderState.WATCH
        self.serialize_state()

        return self.__get_or_wait_jobs_state(processes,CloudRunProviderStateWaitMode.WAIT|CloudRunProviderStateWaitMode.WATCH,job_state)


    def wait_for_jobs_state(self,job_state,processes=None):

        if not processes or len(processes)==0:
            self.debug(1,"No process to wait for")

        return self.__get_or_wait_jobs_state(processes,CloudRunProviderStateWaitMode.WAIT,job_state)

    def get_jobs_states(self,processes=None):

        if not processes or len(processes)==0:
            self.debug(1,"No process requested >> getting all jobs' processes")

        return self.__get_or_wait_jobs_state(processes)

    def _tail_execute_command(self,ssh,files_path,uid,line_num):
        run_log = files_path + '/' + uid + '-run.log'
        command = "cat -n %s | tail --lines=+%d" % (run_log, line_num)
        stdin, stdout_i, stderr = ssh.exec_command(command)
        #stderr = stderr.read()
        #if stderr:
        #    print(stderr)
        return stdout_i.readlines()    

    def _tail_get_last_line_number(self,lines_i, line_num):
        return int(lines_i[-1].split('\t')[0]) + 1 if lines_i else line_num     

    @abstractmethod
    def get_user_region(self):
        pass

    @abstractmethod
    def get_recommended_cpus(self,inst_cfg):
        pass

    @abstractmethod
    def get_cpus_cores(self,inst_cfg):
        pass

    @abstractmethod
    def create_instance_objects(self,config):
        pass

    @abstractmethod
    def find_instance(self,config):
        pass

    @abstractmethod
    def start_instance(self,instance):
        pass

    @abstractmethod
    def stop_instance(self,instance):
        pass

    @abstractmethod
    def terminate_instance(self,instance):
        pass

    @abstractmethod
    def update_instance_info(self,instance):
        pass