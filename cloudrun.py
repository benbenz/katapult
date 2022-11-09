from enum import IntFlag
from abc import ABC , abstractmethod
import cloudrunutils
import sys , json , os
import paramiko
import re
import asyncio
import copy


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
    IDLE      = 1
    RUNNING   = 2
    DONE      = 4
    ABORTED   = 8

class CloudRunInstance():

    def __init__(self,region,name,id,config,proprietaryData=None):
        # instance region
        self._region = region
        # naming
        self._name = name 
        self._id = id 
        self._rank = 1 
        # IP / DNS
        self._ip_addr  = None
        self._dns_addr = None
        # state
        self._state = None
        # the config the instance has been created on
        self._config = config 
        # dict data associated with it (AWS response data e.g.)
        self._data = proprietaryData
            

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


class CloudRunEnvironment():

    def __init__(self,projectName,env_config,dev=False):
        self._config   = env_config
        self._env_obj  = cloudrunutils.compute_environment_object(env_config)
        self._hash     = cloudrunutils.compute_environment_hash(self._env_obj)

        if not self._config.get('env_name'):
            self._name = cr_environmentNameRoot

            if env_config.get('dev') == True:
                self._name = cr_environmentNameRoot
            else:
                if projectName:
                    self._name = cr_environmentNameRoot + '-' + projectName + '-' + self._hash
                else:
                    self._name = cr_environmentNameRoot + '-' + self._hash    
        else:
            self._name = self._config.get('env_name')

        # overwrite name in conda config as well
        if self._env_obj['env_conda'] is not None:
            self._env_obj['env_conda']['name'] = self._name 
        self._env_obj['name'] = self._name
        self._env_obj['hash'] = self._hash
        self._env_obj['path'] = "$HOME/run/" + self._name

    def get_name(self):
        return self._name

    def get_path(self):
        return self._env_obj['path']

    def deploy(self,instance):
        return CloudRunDeployedEnvironment(self,instance)

    def json(self):
        return json.dumps(self._env_obj)        

class CloudRunDeployedEnvironment(CloudRunEnvironment):

    def __init__(self, env, instance):
        self._config   = copy.deepcopy(env._config)
        self._env_obj  = copy.deepcopy(env._env_obj)
        self._hash     = env._hash
        self._name     = env._name
        #env_obj = self._env_obj.copy()
        self._env_obj['path_abs'] = "/home/" + instance.get_config('img_username') + '/run/' + self._name
        # replace __REQUIREMENTS_TXT_LINK__ with the actual requirements.txt path (dependent of config and env hash)
        # the file needs to be absolute
        self._env_obj = cloudrunutils.update_requirements_path(self._env_obj,self._env_obj['path_abs'])

    def get_path_abs(self):
        return self._env_obj['path_abs']


class CloudRunJob():

    def __init__(self,job_cfg):
        self._config  = job_cfg
        self._hash    = cloudrunutils.compute_job_hash(self._config)
        self._env     = None
        if (not 'input_file' in self._config) or (not 'output_file' in self._config) or not isinstance(self._config['input_file'],str) or not isinstance(self._config['output_file'],str):
            print("\n\n\033[91mConfiguration requires an input and output file names\033[0m\n\n")
            raise CloudRunError() 

    def attach_env(self,env):
        self._env = env 
        self._config['env_name'] = env.get_name()

    def get_hash(self):
        return self._hash

    def get_config(self,key):
        return self._config.get(key)

    def get_env(self):
        return self._env

    def deploy(self,dpl_env):
        return CloudRunDeployedJob(self,dpl_env)

    def __repr__(self):
        return "{0}: HASH = {1}".format(type(self).__name__,self._hash)
        
    def __str__(self):
        return "{0}: HASH = {1}".format(type(self).__name__,self._hash)


class CloudRunDeployedJob(CloudRunJob):

    def __init__(self,job,dpl_env):
        self._config    = copy.deepcopy(job._config)
        self._hash      = job._hash
        self._env       = dpl_env
        self._processes = dict()
        self._path      = dpl_env.get_path_abs() + '/' + self.get_hash()
        self._command   = cloudrunutils.compute_job_command(self._path,self._config)

    def attach_process(self,runtimeInfo):
        self._processes[runtimeInfo.get_uid()] = runtimeInfo 

    def get_path(self):
        return self._path

    def get_command(self):
        return self._command


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
        self._config  = conf
        self._load_objects()
        self._preprocess_instances()
        self._preprocess_jobs()
        self._sanity_checks()
        self.DBG_LVL = conf.get('debug',1)

    def debug(self,level,*args):
        if level <= self.DBG_LVL:
            print(*args)

    def _load_objects(self):
        projectName = self._config.get('project')
        env_cfgs    = self._config.get('environments')
        job_cfgs    = self._config.get('jobs')
        dev         = self._config.get('dev')

        self._environments = [ ] 
        if env_cfgs:
            for env_cfg in env_cfgs:
                env = CloudRunEnvironment(projectName,env_cfg,dev)
                self._environments.append(env)

        self._jobs = [ ] 
        if job_cfgs:
            for job_cfg in job_cfgs:
                job = CloudRunJob(job_cfg)
                self._jobs.append(job)

    # process the instance_types section:
    # - multiply instances according to plurality ('number' and 'explode')
    # - change cpus value according to distribution
    # - adds a 'rank' attribute to the instances configurations
    def _preprocess_instances(self):
        pass
        
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
                        debug(1,"waiting for state ...",instanceState," IP =",updated_instance.get_ip_addr())
                
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

    async def run_script(self):

        # CHECK EVERY TIME !
        instance , created = self.start_instance()

        await self._wait_for_instance(instance)

        # FOR NOW
        job      = self._jobs[0]        # retrieve default script
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
            filename = os.path.basename(job.get_config('run_script'))
            try:
                ftp_client.put(job.get_config('run_script'),filename)
            except:
                self.debug(1,"You defined an script that is not available",job.get_config('run_script'))
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
            { 'cmd': global_path+"/bootstrap.sh \"" + dpl_env.get_name() + "\" " + ("1" if self._config['dev'] else "0") + " &", 'out': True },  
            # execute main script (spawn) (this will wait for bootstraping)
            { 'cmd': global_path+"/run.sh \"" + dpl_env.get_name() + "\" \""+dpl_job.get_command()+"\" " + job.get_config('input_file') + " " + job.get_config('output_file') + " " + job.get_hash()+" "+uid, 'out' : False }
        ]
        for command in commands:
            self.debug(1,"Executing ",format( command['cmd'] ),"output",command['out'])
            try:
                stdin , stdout, stderr = ssh_client.exec_command(command['cmd'])
                #print(stdout.read())
                if command['out']:
                    for l in line_buffered(stdout):
                        self.debug(1,l)

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

    # this allow any external process to wait for a specific job
    async def get_script_state( self, processObj ):

        instance = self.get_instance()

        if instance is None:
            print("get_command_state: instance is not available!")
            return CloudRunCommandState.UNKNOWN

        await self._wait_for_instance(instance)

        job         = processObj.get_job() # deployed job
        dpl_env     = job.get_env() # deployed job has a deployed environment
        files_path  = dpl_env.get_path()
        global_path = "$HOME/run"

        ssh_client = await self._connect_to_instance(instance)

        shash = processObj.get_hash()
        uid   = processObj.get_uid()
        pid   = processObj.get_pid()

        cmd = global_path + "/state.sh " + dpl_env.get_name() + " " + str(shash) + " " + str(uid) + " " + str(pid) + " " + self._config['output_file']
        self.debug(1,"Executing command",cmd)
        stdin, stdout, stderr = ssh_client.exec_command(cmd)

        statestr = stdout.read().decode("utf-8").strip()
        self.debug(1,"State=",statestr)
        statestr = re.sub(r'\([0-9]+\)','',statestr)
        try:
            state = CloudRunCommandState[statestr.upper()]
            process.set_state(state)
            self.debug(1,process)
        except:
            print("\nUnhandled state received by state.sh!!!\n")
            state = CloudRunCommandState.UNKNOWN

        ssh_client.close()

        return state

    async def wait_for_script_state( self, script_state , process ):    
        instance = self.get_instance()

        if instance is None:
            print("get_command_state: instance is not available!")
            return CloudRunCommandState.UNKNOWN

        await self._wait_for_instance(instance)

        job         = process.get_job() # deployed job
        dpl_env     = job.get_env()        # deployed job has a deployed environment
        files_path  = dpl_env.get_path()
        global_path = "$HOME/run"
        shash       = job.get_hash()
        uid         = process.get_uid()
        pid         = process.get_pid()

        ssh_client = await self._connect_to_instance(instance)


        while True:

            cmd = global_path + "/state.sh " + dpl_env.get_name() + " " + str(shash) + " " + str(uid) + " " + str(pid) + " " + str(job.get_config('output_file'))
            self.debug(1,"Executing command",cmd)
            stdin, stdout, stderr = ssh_client.exec_command(cmd)

            statestr = stdout.read().decode("utf-8").strip()
            self.debug(1,"State=",statestr)
            statestr = re.sub(r'\([0-9]+\)','',statestr)

            try:
                state = CloudRunCommandState[statestr.upper()]
                process.set_state(state)
                self.debug(1,process)
            except:
                print("\nUnhandled state received by state.sh!!!",statestr,"\n")
                state = CloudRunCommandState.UNKNOWN

            if state & script_state:
                break 

            await asyncio.sleep(2)

        ssh_client.close()

        return state

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
    def get_instance(self):
        pass

    @abstractmethod
    def start_instance(self):
        pass

    @abstractmethod
    def stop_instance(self):
        pass

    @abstractmethod
    def terminate_instance(self):
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

def init_instance_name(instance_config,dev=False):
    if dev==True:
        return cr_instanceNameRoot
    else:
        instance_hash = cloudrunutils.compute_instance_hash(instance_config)

        # if 'rank' not in instance_config:
        #     debug(1,"\033[93mDeveloper: you need to set dynamically a 'rank' attribute in the config for the new instance\033[0m")
        #     sys.exit(300) # this is a developer error, this should never happen so we can use exit here
        instance_rank = str(1) #instance_config['rank']

        if 'project' in instance_config:
            return cr_instanceNameRoot + '-' + instance_config['project'] + '-' + instance_rank + '-' + instance_hash
        else:
            return cr_instanceNameRoot + '-' + instance_config['rank'] + '-' + instance_hash    

def line_buffered(f):
    line_buf = ""
    doContinue = True
    try :
        while doContinue and not f.channel.exit_status_ready():
            try:
                line_buf += f.read(16).decode("utf-8")
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

