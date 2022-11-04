from enum import Enum
from abc import ABC , abstractmethod

class CloudRunError(Exception):
    pass


class CloudRunCommandState(Enum):
    UNKNOWN   = 0
    IDLE      = 1
    RUNNING   = 2
    DONE      = 3
    ABORTED_Q = 4
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
    async def get_script_state( self, uid , pid = None , run_hash = None ):
        pass

    @abstractmethod
    async def tail( self , run_hash ):
        pass        


def get_client(config):

    if config['provider'] == 'aws':

        craws = __import__("cloudrun_aws")

        provider = craws.AWSCloudRunProvider(config)

        return provider

    else:

        print(config['service'], " not implemented yet")
        raise CloudRunError()

