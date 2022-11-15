from enum import IntFlag
from abc import ABC , abstractmethod
import cloudrunutils
import sys , json , os
import paramiko
import re
import asyncio
import copy
import math , random
from io import BytesIO


random.seed()


cr_keypairName         = 'cloudrun-keypair'
cr_secGroupName        = 'cloudrun-sec-group-allow-ssh'
cr_bucketName          = 'cloudrun-bucket'
cr_vpcName             = 'cloudrun-vpc'
cr_instanceNameRoot    = 'cloudrun-instance'
cr_environmentNameRoot = 'cloudrun-env'

class CloudRunError(Exception):
    pass


class CloudRunCommandState(IntFlag):
    UNKNOWN   = 0
    WAIT      = 1  # waiting for bootstraping
    QUEUE     = 2  # queued (for sequential scripts)
    IDLE      = 4  # script about to start
    RUNNING   = 8  # script running
    DONE      = 16 # script has completed
    ABORTED   = 32 # script has been aborted
    ANY       = 32 + 16 + 8 + 4 + 2 + 1 

class CloudRunInstance():

    def __init__(self,config,id,proprietaryData=None):
        # instance region
        self._region   = config.get('region')
        # naming
        self._name     = init_instance_name(config)
        self._id       = id
        self._rank     = config.get('rank',"1.1")
        # IP / DNS
        self._ip_addr  = None
        self._dns_addr = None
        # state
        self._state    = None
        # the config the instance has been created on
        self._config   = config 
        # dict data associated with it (AWS response data e.g.)
        self._data     = proprietaryData
        # jobs list
        self._jobs     = [ ]
        # env dict
        self._envs     = dict()

    def get_region(self):
        return self._region

    def get_id(self):
        return self._id 
     
    def get_name(self):
        return self._name

    def get_rank(self):
        return self._rank

    def get_ip_addr(self):
        return self._ip_addr

    def get_dns_addr(self):
        return self._dns_addr 

    def get_cpus(self):
        return self._config.get('cpus')

    def set_ip_addr(self,value):
        self._ip_addr = value

    def get_state(self):
        return self._state

    def set_dns_addr(self,value):
        self._dns_addr = value
     
    def set_state(self,value):
        self._state = value 

    def set_data(self,data):
        self._data = data 

    def get_data(self,key):
        if not self._data:
            return None
        return self._data.get(key,None)
     
    def get_config(self,key):
        if not self._config:
            return None
        return self._config.get(key,None)

    def append_job(self,job):
        self._jobs.append(job)
        env = job.get_env()
        self._envs[env.get_name()] = env 

    def get_environments(self):
        return self._envs.values()

    def get_jobs(self):
        return self._jobs

    def get_config_DIRTY(self):
        return self._config

    def update_from_instance(self,instance):
        self._region   = instance._region
        self._name     = instance._name
        self._id       = instance._id 
        self._rank     = instance._rank
        self._ip_addr  = instance._ip_addr
        self._dns_addr = instance._dns_addr
        self._state    = instance._state
        self._config   = copy.deepcopy(instance._config)
        self._data     = copy.deepcopy(instance._data)        

    def __repr__(self):
        return "{0}: REGION = {1} , ID = {2} , NAME = {3} , IP = {4} , CPUS = {5} , RANK = {6}".format(type(self).__name__,self._region,self._id,self._name,self._ip_addr,self.get_cpus(),self._rank)

    def __str__(self):
        return "{0}: REGION = {1} , ID = {2} , NAME = {3} , IP = {4} , CPUS = {5} , RANK = {6}".format(type(self).__name__,self._region,self._id,self._name,self._ip_addr,self.get_cpus(),self._rank)

class CloudRunEnvironment():

    def __init__(self,projectName,env_config):
        self._config   = env_config
        self._project  = projectName
        _env_obj       = cloudrunutils.compute_environment_object(env_config)
        self._hash     = cloudrunutils.compute_environment_hash(_env_obj)

        if not self._config.get('env_name'):
            self._name = cr_environmentNameRoot

            append_str = '-' + self._hash
            if env_config.get('dev') == True:
                append_str = ''
            if projectName:
                self._name = cr_environmentNameRoot + '-' + projectName + append_str
            else:
                self._name = cr_environmentNameRoot + append_str
        else:
            self._name = self._config.get('env_name')

        self._path     = "$HOME/run/" + self._name

    def get_name(self):
        return self._name

    def get_path(self):
        return self._path

    def deploy(self,instance):
        return CloudRunDeployedEnvironment(self,instance)

# "Temporary" objects used when starting scripts      

class CloudRunDeployedEnvironment(CloudRunEnvironment):

    # constructor by copy...
    def __init__(self, env, instance):
        #super().__init__( env._project , env._config )
        self._config   = env._config #copy.deepcopy(env._config)
        self._project  = env._project
        self._hash     = env._hash
        self._path     = env._path
        self._name     = env._name
        self._instance = instance
        self._path_abs = "/home/" + instance.get_config('img_username') + '/run/' + self._name

    def get_path_abs(self):
        return self._path_abs

    def get_instance(self):
        return self._instance

    def json(self):
        _env_obj = cloudrunutils.compute_environment_object(self._config)
        # overwrite name in conda config as well
        if _env_obj['env_conda'] is not None:
            _env_obj['env_conda']['name'] = self._name 
        _env_obj['name'] = self._name
        # replace __REQUIREMENTS_TXT_LINK__ with the actual requirements.txt path (dependent of config and env hash)
        # the file needs to be absolute
        _env_obj = cloudrunutils.update_requirements_path(_env_obj,self._path_abs)
        return json.dumps(_env_obj)  


class CloudRunJob():

    def __init__(self,job_cfg):
        self._config    = job_cfg
        self._hash      = cloudrunutils.compute_job_hash(self._config)
        self._env       = None
        self._instance  = None
        self.__deployed = [ ]
        if (not 'input_file' in self._config) or (not 'output_file' in self._config) or not isinstance(self._config['input_file'],str) or not isinstance(self._config['output_file'],str):
            print("\n\n\033[91mConfiguration requires an input and output file names\033[0m\n\n")
            raise CloudRunError() 

    def attach_env(self,env):
        self._env = env 
        self._config['env_name'] = env.get_name()

    def get_hash(self):
        return self._hash

    def get_config(self,key,defaultVal=None):
        return self._config.get(key,defaultVal)

    def get_env(self):
        return self._env

    def get_instance(self):
        return self._instance

    def deploy(self,dpl_env):
        dpl_job = CloudRunDeployedJob(self,dpl_env)
        self.__deployed.append(dpl_job)
        return dpl_job

    def set_instance(self,instance):
        self._instance = instance
        instance.append_job(self)

    def __repr__(self):
        return "{0}: HASH = {1} , INSTANCE = {2}".format(type(self).__name__,self.get_hash(),self.get_instance())
         
    def __str__(self):
        return "{0}: HASH = {1} , INSTANCE = {2}".format(type(self).__name__,self.get_hash(),self.get_instance())


# "Temporary" objects used when starting scripts     
# "Proxy" class that keeps the link with "copied" object
# We proxy all parent methods instead of using inheritance
# this allows to keep the same behavior while keeping the link and sharing memory objects

class CloudRunDeployedJob(CloudRunJob):

    def __init__(self,job,dpl_env):
        #super().__init__( job._config )
        self._job       = job
        #self._config    = copy.deepcopy(job._config)
        #self._hash      = job._hash
        #self._env       = dpl_env
        #self._instance  = job._instance
        self._processes = dict()
        self._path      = dpl_env.get_path_abs() + '/' + self.get_hash()
        self._command   = cloudrunutils.compute_job_command(self._path,self._job._config)

    def attach_process(self,process):
        self._processes[process.get_uid()] = process 

    def get_path(self):
        return self._path

    def get_command(self):
        return self._command

    def attach_env(self,env):
        raise CloudRunError('Can not attach env to deployed job')

    # proxied
    def get_hash(self):
        return self._job._hash

    # proxied
    def get_config(self,key,defaultVal=None):
        return self._job._config.get(key,defaultVal)

    # proxied
    def get_env(self):
        return self._job._env

    # proxied
    def get_instance(self):
        return self._job._instance   

    def deploy(self,dpl_env):
        raise CloudRunError('Can not deploy a deployed job')

    def set_instance(self,instance):
        raise CloudRunError('Can not set the instance of a deployed job')


class CloudRunProcess():

    def __init__(self,dpl_job,uid,pid=None):
        self._job    = dpl_job
        self._uid   = uid
        self._pid   = pid
        self._state = CloudRunCommandState.UNKNOWN
     
    def get_uid(self):
        return self._uid

    def get_pid(self):
        return self._pid

    def get_state(self):
        return self._state
     
    def set_state(self,value):
        self._state = value

    def get_job(self):
        return self._job 

    def __repr__(self):
        return "CloudRunProcess: job = {0} , UID = {1} , PID = {2} , STATE = {3}".format(self._job,self._uid,self._pid,self._state)
         
    def __str__(self):
        return "CloudRunProcess: job = {0} , UID = {1} , PID = {2} , STATE = {3}".format(self._job,self._uid,self._pid,self._state)


class CloudRunProvider(ABC):

    def __init__(self, conf):
        self.DBG_LVL = conf.get('debug',1)
        global DBG_LVL
        DBG_LVL = conf.get('debug',1)

        self._config  = conf
        self._load_objects()
        self._preprocess_jobs()
        self._sanity_checks()

    def debug(self,level,*args,**kwargs):
        if level <= self.DBG_LVL:
            print(*args,**kwargs)

    def _load_objects(self):
        projectName = self._config.get('project')
        inst_cfgs   = self._config.get('instances')
        env_cfgs    = self._config.get('environments')
        job_cfgs    = self._config.get('jobs')

        self._instances = [ ]
        if inst_cfgs:
            for inst_cfg in inst_cfgs:
                # virtually demultiply according to 'number' and 'explode'
                for i in range(inst_cfg.get('number',1)):
                    rec_cpus = self.get_recommended_cpus(inst_cfg)
                    if rec_cpus is None:
                        self.debug(1,"WARNING: could not set recommended CPU size for instance type:",inst_cfg.get('type'))
                        cpu_split = None
                    else:
                        cpu_split = rec_cpus[len(rec_cpus)-1]

                    if cpu_split is None:
                        self.debug(1,"WARNING: removing CPU reqs for instance type:",inst_cfg.get('type'))
                        real_inst_cfg = copy.deepcopy(inst_cfg)
                        real_inst_cfg.pop('number',None)  # provide default value to avoid KeyError
                        real_inst_cfg.pop('explode',None) # provide default value to avoid KeyError

                        real_inst_cfg['cpus'] = None
                        real_inst_cfg['rank'] = "{0}.{1}".format(i+1,1)
                        # [!important!] also copy global information that are used for the name generation ...
                        real_inst_cfg['dev']  = self._config.get('dev',False)
                        real_inst_cfg['project']  = self._config.get('project',None)

                        # starts calling the Service here !
                        # instance , created = self.start_instance( real_inst_cfg )
                        # let's put some dummy instances for now ...
                        instance = CloudRunInstance( real_inst_cfg , None, None )
                        self._instances.append( instance )
                    else:
                        total_inst_cpus = inst_cfg.get('cpus',1)
                        if type(total_inst_cpus) != int and type(total_inst_cpus) != float:
                            print("WARNING: setting default CPUs number to 1 for an instance")
                            total_inst_cpus = 1
                        if inst_cfg.get('explode'):
                            num_sub_instances = math.floor( total_inst_cpus / cpu_split ) # we target CPUs with 16 cores...
                            if num_sub_instances == 0:
                                cpu_inc = total_inst_cpus
                                num_sub_instances = 1
                            else:
                                cpu_inc = cpu_split 
                                num_sub_instances = num_sub_instances + 1
                        else:
                            num_sub_instances = 1
                            cpu_inc = total_inst_cpus
                        cpus_created = 0 
                        for j in range(num_sub_instances):
                            rank = "{0}.{1}".format(i+1,j+1)
                            if j == num_sub_instances-1: # for the last one we're completing the cpus with whatever
                                inst_cpus = total_inst_cpus - cpus_created
                            else:
                                inst_cpus = cpu_inc
                            real_inst_cfg = copy.deepcopy(inst_cfg)
                            real_inst_cfg.pop('number',None)  # provide default value to avoid KeyError
                            real_inst_cfg.pop('explode',None) # provide default value to avoid KeyError
                            real_inst_cfg['cpus'] = inst_cpus
                            real_inst_cfg['rank'] = rank
                            # [!important!] also copy global information that are used for the name generation ...
                            real_inst_cfg['dev']  = self._config.get('dev',False)
                            real_inst_cfg['project']  = self._config.get('project',None)

                            # let's put some dummy instances for now ...
                            instance = CloudRunInstance( real_inst_cfg , None, None )
                            self._instances.append( instance )

                            cpus_created = cpus_created + inst_cpus
        debug(2,self._instances)

        self._environments = [ ] 
        if env_cfgs:
            for env_cfg in env_cfgs:
                # copy the dev global paramter to the environment configuration (will be used for names)
                env_cfg['dev']  = self._config.get('dev',False)
                env = CloudRunEnvironment(projectName,env_cfg)
                self._environments.append(env)

        self._jobs = [ ] 
        if job_cfgs:
            for job_cfg in job_cfgs:
                job = CloudRunJob(job_cfg)
                self._jobs.append(job)

    # fill up the jobs names if not present (and we have only 1 environment defined)
    # link the jobs objects with an environment object
    def _preprocess_jobs(self):
        for job in self._jobs:
            if not job.get_config('env_name'):
                if len(self._environments)==1:
                    job.attach_env(self._environments[0])
                else:
                    print("FATAL ERROR - you have more than one environments defined and the job doesnt have an env_name defined",job)
                    sys.exit()
            else:
                env = self._get_environment(job.get_config('env_name'))
                if not env:
                    print("FATAL ERROR - could not find env with name",job.get_config('env_name'),job)
                    sys.exit()
                else:
                    job.attach_env(env)


    def _sanity_checks(self):
        pass

    def _get_environment(self,name):
        for env in self._environment:
            if env.get_name() == name:
                return env
        return None

    async def _wait_for_instance(self,instance):
        # get the public DNS info when instance actually started (todo: check actual state)
        waitFor = True
        while waitFor:
            self.update_instance_info(instance)

            lookForDNS       = instance.get_dns_addr() is None
            lookForIP        = instance.get_ip_addr() is None
            instanceState    = instance.get_state()

            lookForState = True
            # 'pending'|'running'|'shutting-down'|'terminated'|'stopping'|'stopped'
            if instanceState == 'stopped' or instanceState == 'stopping':
                try:
                    # restart the instance
                    start_instance(instance)
                except CloudRunError:
                    terminate_instance(instance)
                    try :
                        create_instance_objects(config)
                    except:
                        return None

            elif instanceState == 'running':
                lookForState = False

            waitFor = lookForDNS or lookForState  
            if waitFor:
                if lookForDNS:
                    debug(1,"waiting for DNS address and  state ...",instanceState)
                else:
                    if lookForIP:
                        debug(1,"waiting for state ...",instanceState)
                    else:
                        debug(1,"waiting for state ...",instanceState," IP =",instance.get_ip_addr())
                 
                await asyncio.sleep(10)

        self.debug(2,instance)    

    async def _connect_to_instance(self,instance):
        # ssh into instance and run the script from S3/local? (or sftp)
        region = instance.get_region()
        if region is None:
            region = self.get_user_region()
        k = paramiko.RSAKey.from_private_key_file('cloudrun-'+str(region)+'.pem')
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.debug(1,"connecting to ",instance.get_dns_addr(),"/",instance.get_ip_addr())
        while True:
            try:
                ssh_client.connect(hostname=instance.get_dns_addr(),username=instance.get_config('img_username'),pkey=k) #,password=’mypassword’)
                break
            except paramiko.ssh_exception.NoValidConnectionsError as cexc:
                print(cexc)
                await asyncio.sleep(4)
                self.debug(1,"Retrying ...")
            except OSError as ose:
                print(ose)
                await asyncio.sleep(4)
                self.debug(1,"Retrying ...")

        self.debug(1,"connected")    

        return ssh_client

    def get_job(self,index):

        return self._jobs[index] 

    def assign_jobs_to_instances(self):

        # DUMMY algorithm for now 
        for job in self._jobs:
            if job.get_instance():
                continue
            
            instance = random.choice( self._instances )
             
            job.set_instance(instance)
            self.debug(1,"Assigned job " + str(job) )

    # def start(self):
    #     for instance in self._instances:
    #         # create the instance
    #         try:
    #             self.start_instance(instance)
    #         except Exception as e:
    #             traceback.print_exc()
    #             pass

    async def _start_and_wait_for_instance(self,instance):
        # CHECK EVERY TIME !
        new_instance , created = self.start_instance(instance)
         
        # make sure we update the instance with the new instance data
        instance.update_from_instance(new_instance)

        # wait for the instance to be ready
        await self._wait_for_instance(instance)

        return created

    def _test_reupload(self,instance,file_test,ssh_client):
        re_upload = False
        stdin0, stdout0, stderr0 = ssh_client.exec_command("[[ -f "+file_test+" ]] && echo \"ok\" || echo \"not_ok\";")
        result = stdout0.read()
        if "not_ok" in result.decode():
            debug(1,"re-upload of files ...")
            re_upload = True
        return re_upload

    def _deploy_instance(self,instance,deploy_states,ssh_client,ftp_client):

        # last file uploaded ...
        re_upload  = self._test_reupload(instance,"$HOME/run/ready", ssh_client)

        created = deploy_states[instance.get_name()].get('created')

        debug(1,"created",created,"re_upload",re_upload)

        if created or re_upload:

            self.debug(1,"creating instance's directories ...")
            stdin0, stdout0, stderr0 = ssh_client.exec_command("mkdir -p $HOME/run")
            self.debug(1,"directories created")

            self.debug(1,"uploading instance's files ... ")

            # upload the install file, the env file and the script file
            ftp_client = ssh_client.open_sftp()

            # change dir to global dir (should be done once)
            global_path = "/home/" + instance.get_config('img_username') + '/run/'
            ftp_client.chdir(global_path)
            ftp_client.put('remote_files/config.py','config.py')
            ftp_client.put('remote_files/bootstrap.sh','bootstrap.sh')
            ftp_client.put('remote_files/run.sh','run.sh')
            ftp_client.put('remote_files/microrun.sh','microrun.sh')
            ftp_client.put('remote_files/state.sh','state.sh')
            ftp_client.put('remote_files/tail.sh','tail.sh')
            ftp_client.put('remote_files/getpid.sh','getpid.sh')

            self.debug(1,"Installing PyYAML for newly created instance ...")
            stdin , stdout, stderr = ssh_client.exec_command("pip install pyyaml")
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


        deploy_states[instance.get_name()] = { 'upload' : created or re_upload } 

    def _deploy_environments(self,instance,deploy_states,ssh_client,ftp_client):

        re_upload_inst = deploy_states[instance.get_name()]['upload']

        # scan the instances environment (those are set when assigning a job to an instance)
        for environment in instance.get_environments():

            # "deploy" the environment to the instance and get a DeployedEnvironment
            dpl_env  = environment.deploy(instance) 

            self.debug(2,dpl_env.json())

            re_upload_env = self._test_reupload(instance,dpl_env.get_path_abs()+'/ready', ssh_client)

            debug(1,"re_upload_instance",re_upload_inst,"re_upload_env",re_upload_env)

            re_upload = re_upload_env or re_upload_inst

            deploy_states[instance.get_name()][environment.get_name()] = { 'upload' : re_upload }

            if re_upload:
                files_path = dpl_env.get_path()
                global_path = "$HOME/run" # more robust

                self.debug(1,"creating environment directories ...")
                stdin0, stdout0, stderr0 = ssh_client.exec_command("mkdir -p "+files_path)
                self.debug(1,"directories created")

                self.debug(1,"uploading files ... ")

                # upload the install file, the env file and the script file
                # change to env dir
                ftp_client.chdir(dpl_env.get_path_abs())
                remote_config = 'config-'+dpl_env.get_name()+'.json'
                with open(remote_config,'w') as cfg_file:
                    cfg_file.write(dpl_env.json())
                    cfg_file.close()
                    ftp_client.put(remote_config,'config.json')
                    os.remove(remote_config)

                self.debug(1,"uploaded.")                    

                commands = [
                    # recreate pip+conda files according to config
                    { 'cmd': "cd " + files_path + " && python3 "+global_path+"/config.py" , 'out' : False },
                    # setup envs according to current config files state
                    # NOTE: make sure to let out = True or bootstraping is not executed properly 
                    # TODO: INVESTIGATE THIS
                    { 'cmd': global_path+"/bootstrap.sh \"" + dpl_env.get_name() + "\" " + ("1" if self._config['dev'] else "0") , 'out': False },  
                ]

                self._run_ssh_commands(ssh_client,commands)

                ftp_client.putfo(BytesIO("".encode()), 'ready')
        

    def _deploy_jobs(self,instance,deploy_states,ssh_client,ftp_client):

        # scan the instances environment (those are set when assigning a job to an instance)
        for job in instance.get_jobs():
            env      = job.get_env()        # get its environment
            dpl_env  = env.deploy(instance) # "deploy" the environment to the instance and get a DeployedEnvironment
            dpl_job  = job.deploy(dpl_env)

            self.debug(1,"creating job directories ...")
            stdin0, stdout0, stderr0 = ssh_client.exec_command("mkdir -p "+dpl_job.get_path())
            self.debug(1,"directories created")

            re_upload_env = deploy_states[instance.get_name()][env.get_name()]['upload']
            re_upload = self._test_reupload(instance,dpl_job.get_path()+'/ready', ssh_client)

            self.debug(1,"re_upload_env",re_upload_env,"re_upload",re_upload)

            if re_upload or re_upload_env:

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
                if job.get_config('upload_files'):
                    files = job.get_config('upload_files')
                    if isinstance( files,str):
                        files = [ files ] 
                    for upfile in files:
                        try:
                            try:
                                ftp_client.put(upfile,os.path.basename(upfile))
                            except:
                                self.debug(1,"You defined an upload file that is not available",upfile)
                        except Exception as e:
                            print("Error while uploading file",upfile)
                            print(e)
                if job.get_config('input_file'):
                    filename = os.path.basename(job.get_config('run_script'))
                    try:
                        ftp_client.put(job.get_config('input_file'),filename)
                    except:
                        self.debug(1,"You defined an input file that is not available:",job.get_config('input_file'))
                
                # used to check if everything is uploaded
                ftp_client.putfo(BytesIO("".encode()), 'ready')

                self.debug(1,"uploaded.",dpl_job.get_hash())

    async def _deploy_all(self,instance):

        deploy_states = dict()

        # make sure we got the instance ready
        created = await self._start_and_wait_for_instance(instance)

        deploy_states[instance.get_name()] = { 'created' : created }

        # connect to instance
        ssh_client = await self._connect_to_instance(instance)
        ftp_client = ssh_client.open_sftp()

        self.debug(1,"-- deploy instances --")

        self._deploy_instance(instance,deploy_states,ssh_client,ftp_client)

        self.debug(1,"-- deploy environments --")

        self._deploy_environments(instance,deploy_states,ssh_client,ftp_client)

        self.debug(1,"-- deploy jobs --")

        self._deploy_jobs(instance,deploy_states,ssh_client,ftp_client) 

        ftp_client.close()
        ssh_client.close()

    # deploys:
    # - instances files
    # - environments files
    # - shared script files / upload / inputs ...
    async def deploy(self):

        # wait for instance to be deployed
        wait_list = [ ]
        for instance in self._instances:
            wait_list.append( self._deploy_all(instance) )
        await asyncio.gather(*wait_list)


    def _run_ssh_commands(self,ssh_client,commands):
        for command in commands:
            self.debug(1,"Executing ",format( command['cmd'] ),"output",command['out'])
            try:
                #print(stdout.read())
                if command['out']:
                    stdin , stdout, stderr = ssh_client.exec_command(command['cmd'])
                    for l in line_buffered(stdout):
                        self.debug(1,l,end='')

                    errmsg = stderr.read()
                    dbglvl = 1 if errmsg else 2
                    self.debug(dbglvl,"Errors")
                    self.debug(dbglvl,errmsg)
                else:
                    transport = ssh_client.get_transport()
                    channel   = transport.open_session()
                    channel.exec_command(command['cmd']+" 1>/dev/null 2>&1 &")
                    #stdout.read()
                    #pid = int(stdout.read().strip().decode("utf-8"))
            except paramiko.ssh_exception.SSHException as sshe:
                print("The SSH Client has been disconnected!")
                print(sshe)
                raise CloudRunError()    

    async def run_jobs(self,start_and_wait=False):

        instances_runs = dict()

        global_path = "$HOME/run" # more robust

        dpl_jobs = dict()

        for job in self._jobs:

            if not job.get_instance():
                debug(1,"The job",job,"has not been assigned to an instance!")
                return None

            instance = job.get_instance()

            # CHECK EVERY TIME !
            if not instances_runs.get(instance.get_name()):
                if start_and_wait:
                    await self._start_and_wait_for_instance(instance)
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
            cmd_run = cmd_run + "mkdir -p "+run_path + " && "
            cmd_run = cmd_run + global_path+"/run.sh \"" + dpl_env.get_name() + "\" \""+dpl_job.get_command()+"\" " + job.get_config('input_file') + " " + job.get_config('output_file') + " " + job.get_hash()+" "+uid
            cmd_run = cmd_run + "\n"
            cmd_pid = cmd_pid + global_path+"/getpid.sh \"" + pid_file + "\"\n"

            instances_runs[instance.get_name()]['cmd_run'] = cmd_run
            instances_runs[instance.get_name()]['cmd_pid'] = cmd_pid
            instances_runs[instance.get_name()]['cmd_run_pre'] = cmd_run_pre
        
        batch_uid = cloudrunutils.generate_unique_filename()
        
        for instance_name , runinfo in instances_runs.items():
            instance = runinfo.get('instance')
            cmd_run  = runinfo.get('cmd_run')
            cmd_pid  = runinfo.get('cmd_pid')
            batch_run_file = 'batch_run-'+batch_uid+'.sh'
            batch_pid_file = 'batch_pid-'+batch_uid+'.sh'
            ssh_client = await self._connect_to_instance(instance)
            ftp_client = ssh_client.open_sftp()
            ftp_client.chdir('/home/'+instance.get_config('img_username')+'/run')
            ftp_client.putfo(BytesIO(cmd_run_pre.encode()+cmd_run.encode()), batch_run_file)
            ftp_client.putfo(BytesIO(cmd_pid.encode()), batch_pid_file)
            # run
            commands = [ 
                { 'cmd': "chmod +x "+global_path+"/"+batch_run_file+" "+global_path+"/"+batch_pid_file, 'out' : False } ,  
                # execute main script (spawn) (this will wait for bootstraping)
                { 'cmd': global_path+"/"+batch_run_file , 'out' : False } 
            ]
            
            self._run_ssh_commands(ssh_client,commands)

            processes = []
            for uid in runinfo.get('jobs'):
                # we dont have the pid of everybody yet because its sequential
                # lets leave it blank. it can work with the uid ...
                job = dpl_jobs[uid]
                process = CloudRunProcess( job , uid , None ) 
                job.attach_process( process )
                self.debug(1,process) 
                processes.append(process)
            
            # useless .... most scripts are waiting so lets not even get the PIDs....

            # self.debug(1,"Executing ",format( global_path+"/"+batch_pid_file ) )
            # stdin , stdout, stderr = ssh_client.exec_command(global_path+"/"+batch_pid_file)
            # while True: 
            #     lines = stdout.readlines()
            #     for line in lines:     
            #         info    = line.strip().split(',')
            #         uid     = info[0]
            #         pid     = int(info[1])
            #         dpl_job = dpl_jobs[uid]
            #         process = CloudRunProcess( dpl_job , uid , pid )
            #         dpl_job.attach_process( process )
            #         self.debug(1,process) 
            #         processes.append(process)

            #     if not lines or len(lines)==0:
            #         break

            ssh_client.close()

            return processes 

        
    async def run_job(self,job,start_and_wait=False):

        if not job.get_instance():
            debug(1,"The job",job,"has not been assigned to an instance!")
            return None

        instance = job.get_instance()

        # CHECK EVERY TIME !
        if start_and_wait:
            await self._start_and_wait_for_instance(instance)

        # FOR NOW
        env      = job.get_env()        # get its environment
        # "deploy" the environment to the instance and get a DeployedEnvironment 
        # note: this has already been done in deploy but it doesnt matter ... 
        #       we dont store the deployed environments, and we base everything on remote state ...
        # NOTE: this could change and we store every thing in memory
        #       but this makes it less robust to states changes (especially remote....)
        dpl_env  = env.deploy(instance)
        dpl_job  = job.deploy(dpl_env)

        ssh_client = await self._connect_to_instance(instance)

        files_path = dpl_env.get_path()
        global_path = "$HOME/run" # more robust

        # generate unique PID file
        uid = cloudrunutils.generate_unique_filename() 
         
        run_path    = dpl_job.get_path() + '/' + uid

        self.debug(1,"creating directories ...")
        stdin0, stdout0, stderr0 = ssh_client.exec_command("mkdir -p "+run_path)
        self.debug(1,"directories created")

        # run
        commands = [ 
            # execute main script (spawn) (this will wait for bootstraping)
            { 'cmd': global_path+"/run.sh \"" + dpl_env.get_name() + "\" \""+dpl_job.get_command()+"\" " + job.get_config('input_file') + " " + job.get_config('output_file') + " " + job.get_hash()+" "+uid, 'out' : False }
        ]

        self._run_ssh_commands(ssh_client,commands)

        # retrieve PID (this will wait for PID file)
        pid_file = run_path + "/pid"
        getpid_cmd = global_path+"/getpid.sh \"" + pid_file + "\""
         
        self.debug(1,"Executing ",format( getpid_cmd ) )
        stdin , stdout, stderr = ssh_client.exec_command(getpid_cmd)
        info = stdout.readline().strip().split(',')
        pid = int(info[1])
        #uid = info[0]

        ssh_client.close()

        process = CloudRunProcess( dpl_job , uid , pid )
        dpl_job.attach_process( process )

        self.debug(1,process) 

        return process

    async def run_job_OLD(self,job):

        if not job.get_instance():
            debug(1,"The job",job,"has not been assigned to an instance!")
            return None

        instance = job.get_instance()

        # CHECK EVERY TIME !
        new_instance , created = self.start_instance(job.get_instance())
          
        # make sure we update the instance with the new instance data
        instance.update_from_instance(new_instance)

        await self._wait_for_instance(instance)

        # FOR NOW
        env      = job.get_env()        # get its environment
        dpl_env  = env.deploy(instance) # "deploy" the environment to the instance and get a DeployedEnvironment
        dpl_job  = job.deploy(dpl_env)

        # init environment object
        self.debug(2,dpl_env.json())

        ssh_client = await self._connect_to_instance(instance)

        files_path = dpl_env.get_path()

        # generate unique PID file
        uid = cloudrunutils.generate_unique_filename() 
          
        run_path    = dpl_job.get_path() + '/' + uid

        self.debug(1,"creating directories ...")
        stdin0, stdout0, stderr0 = ssh_client.exec_command("mkdir -p "+files_path+" "+run_path)
        self.debug(1,"directories created")


        self.debug(1,"uploading files ... ")

        # upload the install file, the env file and the script file
        ftp_client = ssh_client.open_sftp()

        # change dir to global dir (should be done once)
        global_path = "/home/" + instance.get_config('img_username') + '/run/'
        ftp_client.chdir(global_path)
        ftp_client.put('remote_files/config.py','config.py')
        ftp_client.put('remote_files/bootstrap.sh','bootstrap.sh')
        ftp_client.put('remote_files/run.sh','run.sh')
        ftp_client.put('remote_files/microrun.sh','microrun.sh')
        ftp_client.put('remote_files/state.sh','state.sh')
        ftp_client.put('remote_files/tail.sh','tail.sh')
        ftp_client.put('remote_files/getpid.sh','getpid.sh')
        global_path = "$HOME/run" # more robust

        # change to env dir
        ftp_client.chdir(dpl_env.get_path_abs())
        remote_config = 'config-'+dpl_env.get_name()+'.json'
        with open(remote_config,'w') as cfg_file:
            cfg_file.write(dpl_env.json())
            cfg_file.close()
            ftp_client.put(remote_config,'config.json')
            os.remove(remote_config)
          
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
        if job.get_config('upload_files'):
            files = job.get_config('upload_files')
            if isinstance( files,str):
                files = [ files ] 
            for upfile in files:
                try:
                    try:
                        ftp_client.put(upfile,os.path.basename(upfile))
                    except:
                        self.debug(1,"You defined an upload file that is not available",upfile)
                except Exception as e:
                    print("Error while uploading file",upfile)
                    print(e)
        if job.get_config('input_file'):
            filename = os.path.basename(job.get_config('run_script'))
            try:
                ftp_client.put(job.get_config('input_file'),filename)
            except:
                self.debug(1,"You defined an input file that is not available:",job.get_config('input_file'))

        # used to check if everything is uploaded
        ftp_client.putfo(BytesIO("".encode()), 'uploaded')

        ftp_client.close()

        self.debug(1,"uploaded.")

        if created:
            self.debug(1,"Installing PyYAML for newly created instance ...")
            stdin , stdout, stderr = ssh_client.exec_command("pip install pyyaml")
            self.debug(2,stdout.read())
            self.debug(2, "Errors")
            self.debug(2,stderr.read())

        # run
        commands = [ 
            # make bootstrap executable
            { 'cmd': "chmod +x "+global_path+"/*.sh ", 'out' : True },  
            # recreate pip+conda files according to config
            { 'cmd': "cd " + files_path + " && python3 "+global_path+"/config.py" , 'out' : True },
            # setup envs according to current config files state
            # NOTE: make sure to let out = True or bootstraping is not executed properly 
            # TODO: INVESTIGATE THIS
            { 'cmd': global_path+"/bootstrap.sh \"" + dpl_env.get_name() + "\" " + ("1" if self._config['dev'] else "0") , 'out': True },  
            # execute main script (spawn) (this will wait for bootstraping)
            { 'cmd': global_path+"/run.sh \"" + dpl_env.get_name() + "\" \""+dpl_job.get_command()+"\" " + job.get_config('input_file') + " " + job.get_config('output_file') + " " + job.get_hash()+" "+uid, 'out' : False }
        ]
        for command in commands:
            self.debug(1,"Executing ",format( command['cmd'] ),"output",command['out'])
            try:
                stdin , stdout, stderr = ssh_client.exec_command(command['cmd'])
                #print(stdout.read())
                if command['out']:
                    while True:
                        l = stdout.readline()
                        self.debug(1,l)
                        if l is None:
                            break 
                    #for l in line_buffered(stdout):
                    #    self.debug(1,l)

                    errmsg = stderr.read()
                    dbglvl = 1 if errmsg else 2
                    self.debug(dbglvl,"Errors")
                    self.debug(dbglvl,errmsg)
                else:
                    pass
                    #stdout.read()
                    #pid = int(stdout.read().strip().decode("utf-8"))
            except paramiko.ssh_exception.SSHException as sshe:
                print("The SSH Client has been disconnected!")
                print(sshe)
                raise CloudRunError()

        # retrieve PID (this will wait for PID file)
        pid_file = run_path + "/pid"
        #getpid_cmd = "tail "+pid_file #+" && cp "+pid_file+ " "+run_path+"/pid" # && rm -f "+pid_file
        getpid_cmd = global_path+"/getpid.sh \"" + pid_file + "\""
          
        self.debug(1,"Executing ",format( getpid_cmd ) )
        stdin , stdout, stderr = ssh_client.exec_command(getpid_cmd)
        pid = int(stdout.readline().strip())

        # try:
        #     getpid_cmd = "tail "+pid_file + "2" #+" && cp "+pid_file+ " "+run_path+"/pid && rm -f "+pid_file
        #     self.debug(1,"Executing ",format( getpid_cmd ) )
        #     stdin , stdout, stderr = ssh_client.exec_command(getpid_cmd)
        #     pid2 = int(stdout.readline().strip())
        # except:
        #     pid2 = 0 

        ssh_client.close()

        # make sure we stop the instance to avoid charges !
        #stop_instance(instance)
        process = CloudRunProcess( dpl_job , uid , pid )
        dpl_job.attach_process( process )

        self.debug(1,process) 

        return process        


    async def __get_jobs_states_internal( self , processes_infos , doWait , job_state ):
        
        jobsinfo = ""

        for uid , process_info in processes_infos.items():
            process     = process_info['process']
            job         = process.get_job()    # deployed job
            dpl_env     = job.get_env()        # deployed job has a deployed environment
            shash       = job.get_hash()
            uid         = process.get_uid()
            pid         = process.get_pid()
            if jobsinfo:
                jobsinfo = jobsinfo + " " + dpl_env.get_name() + " " + str(shash) + " " + str(uid) + " " + str(pid) + " \"" + str(job.get_config('output_file')) + "\""
            else:
                jobsinfo = dpl_env.get_name() + " " + str(shash) + " " + str(uid) + " " + str(pid) + " \"" + str(job.get_config('output_file')) + "\""
            
            instance    = job.get_instance() # should be the same for all jobs

        ssh_client = await self._connect_to_instance(instance)

        global_path = "$HOME/run"

        while True:
            cmd = global_path + "/state.sh " + jobsinfo
            self.debug(1,"Executing command",cmd)
            stdin, stdout, stderr = ssh_client.exec_command(cmd)

            while True: 
                lines = stdout.readlines()
                for line in lines:           
                    statestr = line.strip() #line.decode("utf-8").strip()
                    self.debug(1,"State=",statestr)
                    stateinfo = statestr.split(',')
                    statestr  = re.sub(r'\([0-9]+\)','',stateinfo[2])
                    uid       = stateinfo[0]

                    if uid in processes_infos:
                        process = processes_infos[uid]['process']
                        try:
                            state = CloudRunCommandState[statestr.upper()]
                            process.set_state(state)
                            self.debug(1,process)
                            processes_infos[uid]['retrieved'] = True
                            processes_infos[uid]['test']      = job_state & state 
                        except Exception as e:
                            debug(1,"\nUnhandled state received by state.sh!!!",statestr,"\n")
                            debug(2,e)
                            state = CloudRunCommandState.UNKNOWN

                    else:
                        debug(2,"Received UID info that was not requested")
                        pass

                if lines is None or len(lines)==0:
                    break

            # all retrived attributes need to be true
            retrieved = all( [ pinfo['retrieved'] for pinfo in processes_infos.values()] )

            if retrieved and all( [ pinfo['test'] for pinfo in processes_infos.values()] ) :
                break

            if doWait:
                await asyncio.sleep(2)
            else:
                break

        ssh_client.close() 


    async def __get_or_wait_jobs_state( self, processes , do_wait = False , job_state = CloudRunCommandState.ANY ):    

        if not isinstance(processes,list):
            processes = [ processes ]

        # organize by instance
        instances_processes = dict()
        instances_list      = dict()
        for process in processes:
            job         = process.get_job()   # deployed job
            instance    = job.get_instance()
            if instance is None:
                print("wait_for_job_state: instance is not available!")
                return 
            # initialize the collection dict
            if instance.get_name() not in instances_processes:
                instances_processes[instance.get_name()] = dict()
                instances_list[instance.get_name()]      = instance
            if process.get_uid() not in instances_processes[instance.get_name()]:
                instances_processes[instance.get_name()][process.get_uid()] = { 'process' : process , 'retrieved' : False  , 'test' : False }

        # wait for instances to be ready (concurrently)
        instances_wait = [ ]
        for instance in instances_list.values():
            instances_wait.append( self._wait_for_instance(instance))
        await asyncio.gather( *instances_wait ) 

        # wait for each group of processes
        jobs_wait = [ ] 
        for instance_name , processes_infos in instances_processes.items():
            jobs_wait.append( self.__get_jobs_states_internal( processes_infos , do_wait , job_state ) )
        await asyncio.gather( * jobs_wait )

        # done

    async def wait_for_jobs_state(self,processes,job_state):

        await self.__get_or_wait_jobs_state(processes,True,job_state)

    async def get_jobs_states(self,processes):

        await self.__get_or_wait_jobs_state(processes)

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
    def get_instance(self):
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

def get_client(config):

    if config['provider'] == 'aws':

        craws  = __import__("cloudrun_aws")

        client = craws.AWSCloudRunProvider(config)

        return client

    else:

        print(config['service'], " not implemented yet")

        raise CloudRunError()

def init_instance_name(instance_config):
    if instance_config.get('dev',False)==True:
        append_str = '' 
    else:
        append_str = '-' + cloudrunutils.compute_instance_hash(instance_config)

    if 'rank' not in instance_config:
        debug(1,"\033[93mDeveloper: you need to set dynamically a 'rank' attribute in the config for the new instance\033[0m")
        sys.exit(300) # this is a developer error, this should never happen so we can use exit here
        
    if 'project' in instance_config:
        return cr_instanceNameRoot + '-' + instance_config['project'] + '-' + instance_config['rank'] + append_str
    else:
        return cr_instanceNameRoot + '-' + instance_config['rank'] + append_str

def line_buffered(f):
    line_buf = ""
    doContinue = True
    try :
        while doContinue and not f.channel.exit_status_ready():
            try:
                line_buf += f.read(1).decode("utf-8")
                if line_buf.endswith('\n'):
                    yield line_buf
                    line_buf = ''
            except Exception as e:
                #errmsg = str(e)
                #debug(1,"error (1) while buffering line",errmsg)
                pass
                #doContinue = False
    except Exception as e0:
        debug(1,"error (2) while buffering line",str(e0))
        #doContinue = False



DBG_LVL=1

def debug(level,*args,**kwargs):
    if level <= DBG_LVL:
        print(*args,**kwargs)