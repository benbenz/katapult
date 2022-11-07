from enum import IntFlag
from abc import ABC , abstractmethod
import cloudrunutils
import sys

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
        self.__region = region
        # naming
        self.__name = name 
        self.__id = id 
        self.__rank = 1 
        # IP / DNS
        self.__ip_addr  = None
        self.__dns_addr = None
        # the config the instance has been created on
        self.__config = config 
        # dict data associated with it (AWS response data e.g.)
        self.__data = proprietaryData

    def get_region(self):
        return self.__region

    def get_id(self):
        return self.__id 
    
    def get_name(self):
        return self.__name

    def get_rank(self):
        return self.__rank

    def get_ip_addr(self):
        return self.__ip_addr

    def get_dns_addr(self):
        return self.__dns_addr 

    def set_ip_addr(self,value):
        self.__ip_addr = value

    def set_dns_addr(self,value):
        self.__dns_addr = value

    def set_data(self,data):
        self.__data = data 

    def get_data(self,key):
        if not self.__data:
            return None
        return self.__data.get(key,None)
    
    def get_config(self,key):
        if not self.__config:
            return None
        return self.__config.get(key,None)


class CloudRunEnvironment():

    def __init__(self,config):
        self.__config = config

class CloudRunScriptInfo():

    def __init__(self,envObj):
        self.__env = envObj

    def getEnv():
        return self.__env 

class CloudRunScriptRuntimeInfo():

    def __init__(self,script_hash,uid,pid=None):
        self.__hash  = script_hash 
        self.__uid   = uid
        self.__pid   = pid
        self.__state = CloudRunCommandState.UNKNOWN
    
    def get_hash(self):
        return self.__hash

    def get_uid(self):
        return self.__uid

    def get_pid(self):
        return self.__pid

    def get_state(self):
        return self.__state
    
    def set_state(self,value):
        self.__state = value

    def __repr__(self):
        return "CloudRunScriptRuntimeInfo: hash={0},uid={1},pid={2},state={3}".format(self.__hash,self.__uid,self.__pid,self.__state)
        
    def __str__(self):
        return "CloudRunScriptRuntimeInfo: hash={0},uid={1},pid={2},state={3}".format(self.__hash,self.__uid,self.__pid,self.__state)


class CloudRunProvider(ABC):

    def __init__(self, conf):
        self.config  = conf
        self.preprocess_instances()

    # process the instance_types section:
    # - multiply instances according to plurality ('number' and 'explode')
    # - change cpus value according to distribution
    # - adds a 'rank' attribute to the instances configurations
    def preprocess_instances(self):
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
    async def run_script(self):
        pass

    @abstractmethod
    async def get_script_state( self, scriptRuntimeInfo ):
        pass

    @abstractmethod
    async def wait_for_script_state( self, script_state , scriptRunTimeInfo ):
        pass

    @abstractmethod
    async def tail( self, scriptRuntimeInfo ):    
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
    if instance_config.get('dev')==True:
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

def init_environment( projectName , instance , env_config ):
    env_obj  = cloudrunutils.compute_environment_object(env_config)
    env_hash = cloudrunutils.compute_environment_hash(env_obj)

    env_name = cr_environmentNameRoot

    if env_config.get('dev') == True:
        env_name = cr_environmentNameRoot
    else:
        if projectName:
            env_name = cr_environmentNameRoot + '-' + projectName + '-' + env_hash
        else:
            env_name = cr_environmentNameRoot + '-' + env_hash    

    # overwrite name in conda config as well
    if env_obj['env_conda'] is not None:
        env_obj['env_conda']['name'] = env_name 
    env_obj['name'] = env_name
    env_obj['hash'] = env_hash
    env_obj['path'] = "$HOME/run/" + env_name
    env_obj['path_abs'] = "/home/" + instance.get_config('img_username') + '/run/' + env_name

    # replace __REQUIREMENTS_TXT_LINK__ with the actual requirements.txt path (dependent of config and env hash)
    # the file needs to be absolute
    env_obj = cloudrunutils.update_requirements_path(env_obj,env_obj['path_abs'])

    return env_obj           

