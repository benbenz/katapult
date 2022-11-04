from enum import Enum
from abc import ABC , abstractmethod
import cloudrunutils

cr_keypairName         = 'cloudrun-keypair'
cr_secGroupName        = 'cloudrun-sec-group-allow-ssh'
cr_bucketName          = 'cloudrun-bucket'
cr_vpcName             = 'cloudrun-vpc'
cr_instanceNameRoot    = 'cloudrun-instance'
cr_environmentNameRoot = 'cloudrun-env'

class CloudRunError(Exception):
    pass


class CloudRunCommandState(Enum):
    UNKNOWN   = 0
    IDLE      = 1
    RUNNING   = 2
    DONE      = 3
    ABORTED   = 5


class CloudRunProvider(ABC):

    def __init__(self, conf):
        self.config  = conf

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
    async def get_script_state( self, script_hash , uid , pid = None ):
        pass

    @abstractmethod
    async def wait_for_script_state( self, script_state , script_hash , uid , pid = None , ):
        pass

    @abstractmethod
    async def tail( self, script_hash , uid , pid = None , ):    
        pass    

    def init_environment( self ):
        env_obj  = cloudrunutils.compute_environment_object(self.config)
        env_hash = cloudrunutils.compute_environment_hash(env_obj)

        env_name = cr_environmentNameRoot

        if ('dev' in self.config) and (self.config['dev'] == True):
            env_name = cr_environmentNameRoot
        else:
            if 'project' in self.config:
                env_name = cr_environmentNameRoot + '-' + self.config['project'] + '-' + env_hash
            else:
                env_name = cr_environmentNameRoot + '-' + env_hash    

        # overwrite name in conda config as well
        if env_obj['env_conda'] is not None:
            env_obj['env_conda']['name'] = env_name 
        env_obj['name'] = env_name
        env_obj['hash'] = env_hash
        env_obj['path'] = "$HOME/run/" + env_name
        env_obj['path_abs'] = "/home/" + self.config['img_username'] + '/run/' + env_name

        # replace __REQUIREMENTS_TXT_LINK__ with the actual requirements.txt path (dependent of config and env hash)
        # the file needs to be absolute
        env_obj = cloudrunutils.update_requirements_path(env_obj,env_obj['path_abs'])

        return env_obj              


def get_client(config):

    if config['provider'] == 'aws':

        craws  = __import__("cloudrun_aws")

        client = craws.AWSCloudRunProvider(config)

        return client

    else:

        print(config['service'], " not implemented yet")

        raise CloudRunError()

