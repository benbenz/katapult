from abc import ABC , abstractmethod
import cloudrun.utils as cloudrunutils
import sys , json , os , time
import paramiko
import re
from io import BytesIO
import csv , io
import pkg_resources
from cloudrun.core import *
from enum import IntFlag

class CloudRunProviderState(IntFlag):
    NEW           = 0  # provider created
    STARTED       = 1  # provider started
    ASSIGNED      = 2  # provider assigned jobs
    DEPLOYED      = 4  # provider deployed  
    RUNNING       = 8  # provider ran jobs
    WATCHING      = 16 # provider is watching jobs
    ANY           = 16 + 8 + 4 + 2 + 1     

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    
class CloudRunProvider(ABC):

    def __init__(self, conf):

        self._state = CloudRunProviderState.NEW

        self.DBG_LVL = conf.get('debug',1)
        self.DBG_PREFIX = None
        global DBG_LVL
        DBG_LVL = conf.get('debug',1)

        self._config  = conf

        if self._config.get('profile'):
            self.set_profile(self._config.get('profile'))

    def debug_set_prefix(self,value):
        self.DBG_PREFIX = value
        global DBG_PREFIX
        DBG_PREFIX = value

    def debug(self,level,*args,**kwargs):
        if level <= self.DBG_LVL:
            if 'color' in kwargs:
                color = kwargs['color']
                listargs = list(args)
                #listargs.insert(0,color)
                if isinstance(listargs[0], (bytes, bytearray)):
                    str_concat = listargs[0].decode()
                else:
                    str_concat = str(listargs[0])
                listargs[0] = color + str_concat
                listargs.append(bcolors.ENDC)
                args = tuple(listargs)
                kwargs.pop('color')
            try:
                if self.DBG_PREFIX:
                    print(self.DBG_PREFIX,*args,**kwargs) 
                else:
                    print(*args,**kwargs) 
                sys.stdout.flush()
                sys.stderr.flush()
            except:
                pass

    def get_state(self):
        return self._state

    def _get_or_create_instance(self,instance):

        inst_cfg = instance.get_config_DIRTY()
        instance = self.find_instance(inst_cfg)

        if instance is None:
            instance , created = self.create_instance_objects(inst_cfg)
        else:
            created = False

        return instance , created  



    def _start_and_update_instance(self,instance):

        try:
            # CHECK EVERY TIME !
            new_instance , created = self._get_or_create_instance(instance)

            old_id = instance.get_id()
            
            # make sure we update the instance with the new instance data
            instance.update_from_instance(new_instance)

            if instance.get_id() != old_id:
                self.debug(2,"Instance has changed",old_id,"VS",instance.get_id())
                #self._instances_states[instance.get_id()] = { 'changed' : True }
                if not hasattr(self,'_instances_states'):
                    self._instances_states = dict()
                self._instances_states[instance.get_name()] = { 'changed' : True }

        except CloudRunError as cre:

            instance.set_invalid(True)

            self.debug(1,cre)
        
        except Exception as e:
            self.debug(1,e)

            raise e

    def _resolve_dpl_job_paths(self,upfile,dpl_job):
        if self._mutualize_uploads:
            return cloudrunutils.resolve_paths(upfile,dpl_job.get_config('run_script'),'$HOME/run/files',True) 
        else:
            return cloudrunutils.resolve_paths(upfile,dpl_job.get_config('run_script'),dpl_job.get_path(),False)

    def _wait_and_connect(self,instance):

        # wait for instance to be ready 
        self._wait_for_instance(instance)

        # connect to instance
        ssh_client = self._connect_to_instance(instance)
        if ssh_client is not None:
            ftp_client = ssh_client.open_sftp()

            return instance.get_id() , ssh_client , ftp_client        
        else:
            return instance.get_id() , None , None

    def _wait_for_instance(self,instance):
        
        # get the public DNS info when instance actually started (todo: check actual state)
        waitFor = True
        while waitFor:
            self.update_instance_info(instance)

            self.serialize_state()

            lookForDNS       = instance.get_dns_addr() is None
            lookForIP        = instance.get_ip_addr() is None
            instanceState    = instance.get_state()

            lookForState = True
            # 'pending'|'running'|'shutting-down'|'terminated'|'stopping'|'stopped'
            if instanceState == CloudRunInstanceState.STOPPED:
                try:
                    # restart the instance
                    self.start_instance(instance)
                except CloudRunError:
                    self.hard_reset_instance(instance)


            elif instanceState == CloudRunInstanceState.RUNNING:
                lookForState = False

            elif instanceState == CloudRunInstanceState.TERMINATED:
                try:
                    self._start_and_update_instance(instance)
                except:
                    pass

            waitFor = lookForDNS or lookForState  
            if waitFor:
                if lookForDNS:
                    debug(1,"waiting for",instance.get_name(),"...",instanceState.name)
                else:
                    if lookForIP:
                        debug(1,"waiting for",instance.get_name(),"...",instanceState.name)
                    else:
                        debug(1,"waiting for",instance.get_name(),"...",instanceState.name," IP =",instance.get_ip_addr())
                 
                time.sleep(10)

        self.debug(2,instance)     

    def hard_reset_instance(instance):
        self.terminate_instance(instance)
        try :
            self._start_and_update_instance(instance)
        except:
            pass

    def _connect_to_instance(self,instance,**kwargs):
        # ssh into instance and run the script from S3/local? (or sftp)
        region = instance.get_region()
        if region is None:
            region = self.get_user_region(self._config.get('profile'))
        k = paramiko.RSAKey.from_private_key_file('cloudrun-'+str(region)+'.pem')
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.debug(1,"connecting to ",instance.get_dns_addr(),"/",instance.get_ip_addr())
        retrys = 0 
        while True:
            try:
                ssh_client.connect(hostname=instance.get_dns_addr(),username=instance.get_config('img_username'),pkey=k,**kwargs) #,password=’mypassword’)
                break
            except Exception as cexc:
                # check whats going on
                self.update_instance_info(instance)
                if instance.get_state() != CloudRunInstanceState.RUNNING:
                    self._wait_for_instance(instance)
            #except paramiko.ssh_exception.NoValidConnectionsError as cexc:
                if retrys < 5:
                    self.debug(1,cexc)
                    time.sleep(4)
                    self.debug(1,"Retrying ...")
                    retrys = retrys + 1
                elif retrys == 5 and instance.get_state() == CloudRunInstanceState.RUNNING:
                    retrys = retrys + 1
                    self.debug(1,"Trying a reboot ...")
                    self.reboot_instance(instance)
                    time.sleep(4)
                    self._wait_for_instance(instance)
                elif retrys == 6 and instance.get_state() == CloudRunInstanceState.RUNNING:
                    retrys = retrys + 1
                    self.debug(1,"Trying a hard reset ...")
                    self.hard_reset_instance(instance)
                    time.sleep(4)
                    self._wait_for_instance(instance)
                else:
                    self.debug(1,cexc)
                    self.debug(0,"ERROR! instance is unreachable: ",instance,color=bcolors.FAIL)
                    return None
            # except OSError as ose:
            #     if retrys < 5:
            #         self.debug(1,ose)
            #         time.sleep(4)
            #         self.debug(1,"Retrying (2) ...")
            #         retrys = retrys + 1
            #     else:
            #         self.debug(1,cexc)
            #         self.debug(0,"ERROR! instance is unreachable: ",instance)
            #         return None

        self.debug(1,"connected to ",instance.get_ip_addr())    

        return ssh_client              


    def _exec_command(self,ssh_client,command):
        self.debug(2,"Executing ",format( command ))
        try:
            stdin , stdout, stderr = ssh_client.exec_command(command)
            return stdin , stdout , stderr 
        except paramiko.ssh_exception.SSHException as sshe:
            self.debug(1,"The SSH Client has been disconnected!")
            self.debug(1,sshe)
            raise CloudRunError()  
            
    def _run_ssh_commands(self,ssh_client,commands):
        for command in commands:
            self.debug(2,"Executing ",format( command['cmd'] ),"output",command['out'])
            try:
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
                    output = "$HOME/run/out.log" if not 'output' in command else command['output']
                    channel.exec_command(command['cmd']+" 1>"+output+" 2>&1 &")
                    #stdout.read()
                    #pid = int(stdout.read().strip().decode("utf-8"))
            except paramiko.ssh_exception.SSHException as sshe:
                self.debug(1,"The SSH Client has been disconnected!")
                self.debug(1,sshe)
                raise CloudRunError()  

    def _test_reupload(self,instance,file_test,ssh_client,isfile=True):
        re_upload = False
        if isfile:
            stdin0, stdout0, stderr0 = self._exec_command(ssh_client,"[ -f "+file_test+" ] && echo \"ok\" || echo \"not_ok\";")
        else:
            stdin0, stdout0, stderr0 = self._exec_command(ssh_client,"[ -d "+file_test+" ] && echo \"ok\" || echo \"not_ok\";")
        result = stdout0.read()
        if "not_ok" in result.decode():
            debug(1,"re-upload of files ...")
            re_upload = True
        return re_upload                

    def _get_instancetypes_attribute(self,inst_cfg,resource_file,type_col,attr,return_type):

        # Could be any dot-separated package/module name or a "Requirement"
        resource_package = 'cloudrun'
        resource_path = '/'.join(('resources', resource_file))  # Do not use os.path.join()
        #template = pkg_resources.resource_string(resource_package, resource_path)
        # or for a file-like stream:
        #template = pkg_resources.resource_stream(resource_package, resource_path)        
        #with open('instancetypes-aws.csv', newline='') as csvfile:
        csvstr = pkg_resources.resource_string(resource_package, resource_path)
        self._csv_reader = csv.DictReader(io.StringIO(csvstr.decode()))
        for row in self._csv_reader:
            if row[type_col] == inst_cfg.get('type'):
                if return_type == list:
                    arr = row[attr].split(',')
                    res = [ ]
                    for x in arr:
                        try:
                            res.append(int(x))
                        except: 
                            pass
                    if len(res)==0:
                        return None
                elif return_type == int:
                    try:
                        res = int(row[attr])
                    except:
                        return None
                elif return_type == str:
                    return row[attr]
                else:
                    return raw[attr]
        return         

    def _get_resource_file(self,resource_file):
        resource_package = 'cloudrun'
        resource_path = '/'.join(('resources', resource_file))  # Do not use os.path.join()
        #template = pkg_resources.resource_string(resource_package, resource_path)
        # or for a file-like stream:
        #template = pkg_resources.resource_stream(resource_package, resource_path)        
        #with open('instancetypes-aws.csv', newline='') as csvfile:
        #fileio = pkg_resources.resource_string(resource_package, resource_path)
        #self._csv_reader = csv.DictReader(io.StringIO(csvstr.decode()))              
        return pkg_resources.resource_stream(resource_package, resource_path)    

    @abstractmethod
    def get_user_region(self,profile_name):
        pass

    @abstractmethod
    def set_profile(self,profile_name):
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
    def reboot_instance(self,instance):
        pass

    @abstractmethod
    def reset_instance(self,instance):
        pass

    @abstractmethod
    def update_instance_info(self,instance):
        pass

    @abstractmethod
    def wakeup(self):
        pass

    @abstractmethod
    def start(self,reset=False):
        pass

    @abstractmethod
    def assign(self):
        pass

    @abstractmethod
    def deploy(self):
        pass

    @abstractmethod
    def run(self):
        pass

    @abstractmethod
    def watch(self,processes=None,daemon=False):
        pass

    @abstractmethod
    def wait_for_jobs_state(self,job_state,processes=None):
        pass

    @abstractmethod
    def get_jobs_states(self,processes=None):
        pass

    @abstractmethod
    def print_jobs_summary(self,instance=None):
        pass

    @abstractmethod
    def print_aborted_logs(self,instance=None):
        pass
        
def get_client(config):

    if config.get('provider') == 'aws':

        if config.get('maestro','local') == 'local':
            
            craws  = __import__("cloudrun.aws")

            client = craws.aws.AWSCloudRunFatProvider(config)

            return client

        else:

            craws  = __import__("cloudrun.aws")

            client = craws.aws.AWSCloudRunLightProvider(config)

            return client

    else:

        debug(1,config.get('provider'), " not implemented yet")

        raise CloudRunError()

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
DBG_PREFIX=None

def debug(level,*args,**kwargs):
    if level <= DBG_LVL:
        if 'color' in kwargs:
            color = kwargs['color']
            listargs = list(args)
            #listargs.insert(0,color)
            if isinstance(listargs[0], (bytes, bytearray)):
                str_concat = listargs[0].decode()
            else:
                str_concat = str(listargs[0])
            listargs[0] = color + str_concat
            listargs.append(bcolors.ENDC)
            args = tuple(listargs)
            kwargs.pop('color')
        try:
            if DBG_PREFIX:
                print(DBG_PREFIX,*args,**kwargs)
            else:
                print(*args,**kwargs)
        except:
            pass