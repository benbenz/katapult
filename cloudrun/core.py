from enum import IntFlag
from abc import ABC , abstractmethod
import cloudrun.utils as cloudrunutils
import json
import copy

cr_keypairName         = 'cloudrun-keypair'
cr_secGroupName        = 'cloudrun-sec-group-allow-ssh'
cr_bucketName          = 'cloudrun-bucket'
cr_vpcName             = 'cloudrun-vpc'
cr_instanceNameRoot    = 'cloudrun-instance'
cr_environmentNameRoot = 'cloudrun-env'


class CloudRunError(Exception):
    pass

class CloudRunInstanceState(IntFlag):
    UNKNOWN     = 0
    STARTING    = 1  # instance starting
    RUNNING     = 2  # instance running
    STOPPING    = 4  # stopping
    STOPPED     = 8  # stopped
    TERMINATING = 16 # terminating
    TERMINATED  = 32 # terminated
    ANY         = 32 + 16 + 8 + 4 + 2 + 1     


class CloudRunJobState(IntFlag):
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
        self._state    = CloudRunJobState.UNKNOWN
        # the config the instance has been created on
        self._config   = config 
        # dict data associated with it (AWS response data e.g.)
        self._data     = proprietaryData
        # jobs list
        self._jobs     = [ ]
        # env dict
        self._envs     = dict()
        # invalid
        self._invalid  = False

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

    def set_invalid(self,val):
        self._invalid = val

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

    def is_invalid(self):
        return self._invalid

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
        # return "{0}: REGION = {1} , ID = {2} , NAME = {3} , IP = {4} , CPUS = {5} , RANK = {6}".format(type(self).__name__,self._region,self._id,self._name,self._ip_addr,self.get_cpus(),self._rank)
        # return "{0}: ID = {1} , NAME = {2} , IP = {3} , CPUS = {4}".format(type(self).__name__,self._id,self._name,self._ip_addr,self.get_cpus())
        return "{0}: NAME = {1} , IP = {2}".format(type(self).__name__,self._name,self._ip_addr)

    def __str__(self):
        # return "{0}: REGION = {1} , ID = {2} , NAME = {3} , IP = {4} , CPUS = {5} , RANK = {6}".format(type(self).__name__,self._region,self._id,self._name,self._ip_addr,self.get_cpus(),self._rank)
        # return "{0}: ID = {1} , NAME = {2} , IP = {3} , CPUS = {4}".format(type(self).__name__,self._id,self._name,self._ip_addr,self.get_cpus())
        return "{0}: NAME = {1} , IP = {2}".format(type(self).__name__,self._name,self._ip_addr)


class CloudRunEnvironment():

    def __init__(self,projectName,env_config):
        self._config   = env_config
        self._project  = projectName
        _env_obj       = cloudrunutils.compute_environment_object(env_config)
        self._hash     = cloudrunutils.compute_environment_hash(_env_obj)

        if not self._config.get('name'):
            self._name = cr_environmentNameRoot

            append_str = '-' + self._hash
            if env_config.get('dev') == True:
                append_str = ''
            if projectName:
                self._name = cr_environmentNameRoot + '-' + projectName + append_str
            else:
                self._name = cr_environmentNameRoot + append_str
        else:
            self._name = self._config.get('name')

        self._path     = "$HOME/run/" + self._name

    def get_name(self):
        return self._name

    def get_path(self):
        return self._path
    def get_config(self,key):
        return self._config.get(key)

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

    def __init__(self,job_cfg,rank):
        self._config    = job_cfg
        self._rank      = rank
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

    def get_rank(self):
        return self._rank

    def get_deployed_jobs(self):
        return self.__deployed

    def deploy(self,dpl_env,add_permanently=True):
        dpl_job = CloudRunDeployedJob(self,dpl_env)
        if add_permanently:
            self.__deployed.append(dpl_job)
        return dpl_job

    def has_completed(self):
        for dpl_job in self.__deployed:
            for process in dpl_job.get_processes():
                if process.get_state() == CloudRunJobState.DONE:
                    return True
        return False

    def set_instance(self,instance):
        self._instance = instance
        instance.append_job(self)

    def str_simple(self):
        return "{0}: HASH = {1} , ENV = {2}".format(type(self).__name__,self.get_hash(),self.get_env().get_name() if self.get_env() else None)

    def __repr__(self):
        return "{0}: HASH = {1} , INSTANCE = {2} , ENV = {3}".format(type(self).__name__,self.get_hash(),self.get_instance(),self.get_env().get_name() if self.get_env() else None)
         
    def __str__(self):
        return "{0}: HASH = {1} , INSTANCE = {2} , ENV = {3}".format(type(self).__name__,self.get_hash(),self.get_instance(),self.get_env().get_name() if self.get_env() else None)


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
        self._processes = []
        self._path      = dpl_env.get_path_abs() + '/' + self.get_hash()
        self._command   = cloudrunutils.compute_job_command(self._path,self._job._config)

    def attach_process(self,process):
        self._processes.append(process)

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

    def get_processes(self):
        return self._processes

    def deploy(self,dpl_env):
        raise CloudRunError('Can not deploy a deployed job')

    def set_instance(self,instance):
        raise CloudRunError('Can not set the instance of a deployed job')


class CloudRunProcess():

    def __init__(self,dpl_job,uid,pid=None,batch_uid=None):
        self._job    = dpl_job
        self._uid   = uid
        self._pid   = pid
        self._batch_uid = batch_uid
        self._state = CloudRunJobState.UNKNOWN
        self._job.attach_process(self)
     
    def get_uid(self):
        return self._uid

    def get_pid(self):
        return self._pid

    def get_state(self):
        return self._state
     
    def set_state(self,value):
        self._state = value

    def set_pid(self,value):
        self._pid = value 

    def get_job(self):
        return self._job 

    def get_batch_uid(self):
        return self._batch_uid

    def str_simple(self):
        if self._batch_uid:
            return "CloudRunProcess: UID = {0} , PID = {1} , BATCH = {2} , STATE = {3}".format(self._uid,self._pid,self._batch_uid,self._state.name)
        else:
            return "CloudRunProcess: UID = {0} , PID = {1} , STATE = {2}".format(self._uid,self._pid,self._state.name)

    def __repr__(self):
        return "CloudRunProcess: job = {0} , UID = {1} , PID = {2} , STATE = {3}".format(self._job,self._uid,self._pid,self._state.name)
         
    def __str__(self):
        return "CloudRunProcess: job = {0} , UID = {1} , PID = {2} , STATE = {3}".format(self._job,self._uid,self._pid,self._state.name)



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