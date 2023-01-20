from abc import ABC , abstractmethod
import katapult.utils as katapultutils
import sys , json , os , time 
import re
from io import BytesIO
import csv , io
import pkg_resources
from katapult.core import *
from katapult.attrs import *
from enum import IntFlag
#import multiprocessing
import asyncio
import asyncssh
import importlib

COMMAND_ARGS_SEP = '__:__'
ARGS_SEP         = '__,__'
STREAM_RESULT    = '__RESULT__:'
PROVIDER_CONFIG  = 'state.config.json'

DIRECTORY_TMP_AUTO_STOP = './tmp-auto_stop'
DIRECTORY_TMP = './tmp'

class KatapultProvider(ABC):

    def __init__(self, conf=None,**kwargs):

        if conf is None:
            conf = dict()

        self._init(conf,**kwargs)
        #KatapultProvider._init(self,conf)

        #self._instances_locks = dict()
        #self._provider_lock   = multiprocessing.Manager().Lock()
        #self._thread_safe_ultra = True # set to False if you want to try per instance locks

    def _init(self,conf,**kwargs):
        self._state = KatapultProviderState.NEW

        self._provider_config = kwargs.get('provider_config') or PROVIDER_CONFIG

        self.DBG_LVL = conf.get('debug',1)
        self.DBG_PREFIX = None
        global DBG_LVL
        DBG_LVL = conf.get('debug',1)

        self._config  = conf
        self._auto_stop = conf.get('auto_stop',True)

        self._profile_name = self._config.get('profile')
        if self._config.get('profile'):
            self.set_profile(self._config.get('profile'))   

        self._init_hidden_properties(conf)

        self._save_config()

        self._mock_server = None 

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
                if not sys.stdout: # or sys.stdout.closed==True:
                    # sys.stdout = sys.__stdout__
                    # print("SYS.STDOUT is DEAD")
                    # sys.stdout = None
                    return

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

        # this is important because we can very well have watch() daemon and wait() method run at the same time
        # and both those methods may call '_start_and_update_instance' > '_get_or_create_instance'
        #with self._lock(instance):
            
        instance = self.find_instance(inst_cfg)

        if instance is None:
            instance , created = self.create_instance_objects(inst_cfg)
        else:
            self.update_instance_info(instance) # make sure we update
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

        except KatapultError as cre:

            instance.set_invalid(True)

            self.debug(1,cre)

        except Exception as e:
            self.debug(1,e)

            raise e

    def _resolve_dpl_job_paths(self,upfile,dpl_job):
        if dpl_job.get_config('run_script'):
            ref_file = dpl_job.get_config('run_script')
            ref_args     = ref_file.split()
            ref_abs_path = os.path.abspath(ref_args[0])
            upf_abs_path = os.path.abspath(upfile)
            # we're gonna set ref_file to None if its not the ref file
            use_ref  = ref_abs_path != upf_abs_path
            ref_file = ref_file if use_ref else None
        else:
            ref_file = os.getcwd()
            ref_file = None

        if self._mutualize_uploads:
            instance = dpl_job.get_instance()
            remote_ref_dir = instance.path_join( instance.get_home_dir() , 'run' , 'files')
            return katapultutils.resolve_paths(instance,upfile,ref_file,remote_ref_dir,True) 
        else:
            instance = dpl_job.get_instance()
            return katapultutils.resolve_paths(instance,upfile,ref_file,dpl_job.get_path(),False)

    # def _lock(self,instance):
    #     if not self._thread_safe_ultra:
    #         if not instance.get_name() in self._instances_locks:
    #             self._instances_locks[instance.get_name()] = multiprocessing.Manager().Lock()
    #         return self._instances_locks[instance.get_name()]
    #     else:
    #         return self._provider_lock


    async def _wait_and_connect(self,instance):

        # wait for instance to be ready 
        await self._wait_for_instance(instance)

        # connect to instance
        ssh_conn = await self._connect_to_instance(instance)
        if ssh_conn is not None:
            ftp_client = await ssh_conn.start_sftp_client()

            return instance.get_id() , ssh_conn , ftp_client        
        else:
            return instance.get_id() , None , None

    async def _wait_for_instance(self,instance,with_reachability=False):
        
        # get the public DNS info when instance actually started (todo: check actual state)
        waitFor = True
        while waitFor:
            # we may be heavily updating the instace already ...
            # with self._lock(instance):
            self.update_instance_info(instance)

            self.serialize_state()

            lookForDNS       = instance.get_dns_addr() is None
            lookForIP        = instance.get_ip_addr() is None
            instanceState    = instance.get_state()
            reachability     = instance.get_reachability()

            lookForState = True
            # 'pending'|'running'|'shutting-down'|'terminated'|'stopping'|'stopped'
            if instanceState == KatapultInstanceState.STOPPED:
                try:
                    # restart the instance
                    self.start_instance(instance)
                except KatapultError:
                    await self.hard_reset_instance(instance)


            elif instanceState == KatapultInstanceState.RUNNING:
                lookForState = False

            elif instanceState == KatapultInstanceState.TERMINATING or instanceState == KatapultInstanceState.TERMINATED:
                try:
                    self._start_and_update_instance(instance)
                except:
                    pass

            if with_reachability:
                waitFor = lookForDNS or lookForState or not reachability
            else:
                waitFor = lookForDNS or lookForState
            if waitFor:
                if lookForDNS:
                    debug(1,"waiting for",instance.get_name(),"...",instanceState.name)
                else:
                    if lookForIP:
                        debug(1,"waiting for",instance.get_name(),"...",instanceState.name)
                    elif lookForState:
                        debug(1,"waiting for",instance.get_name(),"...",instanceState.name," IP =",instance.get_ip_addr())
                    elif with_reachability and not reachability:
                        debug(1,"waiting for",instance.get_name(),"...",instanceState.name," IP =",instance.get_ip_addr(),"(waiting to be reachable)")
                    else:
                        debug(1,"waiting for",instance.get_name(),"...",instanceState.name," IP =",instance.get_ip_addr())
                 
                await asyncio.sleep(10)

        self.debug(2,instance)     

    # async because the one of the fat client will be async ...
    async def hard_reset_instance(self,instance):
        self.terminate_instance(instance)
        try :
            self._start_and_update_instance(instance)
        except:
            pass

    async def _refresh_instance_key(self,instance,force=False):
        region = instance.get_region()
        if force:
            key_filename = self.get_key_filename(self._profile_name,region)
            try:
                os.remove(key_filename)
            except:
                pass
        if self.retrieve_keypair(region): # if the keypair has been created ...
            await self.hard_reset_instance(instance)
            await self._wait_for_instance(instance) 

    def set_mock_server( self , mock_server ):
        self._mock_server  = mock_server 

    async def _connect_to_instance(self,instance,**kwargs):
        # ssh into instance and run the script 
        region = instance.get_region()
        #if region is None:
        #    region = self.get_user_region(self._config.get('profile'))

        # for mocking/testing
        if self._mock_server:
            k = self._mock_server.privkey
        else:
            keypair_filename = self.get_key_filename(self._config.get('profile'),region)
            if not os.path.exists(keypair_filename):
                self.debug(1,"KeyPair not found locally, we will have to regenerate it ...",color=bcolors.WARNING)
                #self.create_keypair(region)
                await self._refresh_instance_key(instance)
            try:
                k = asyncssh.read_private_key(keypair_filename)
            except:
                # key file exists but is invalid >> try again
                await self._refresh_instance_key(instance)
                k = asyncssh.read_private_key(keypair_filename)

        self.debug(1,"connecting to",instance.get_name(),"@",instance.get_ip_addr())
        retrys = 0 
        retrys_key = 0
        while True:
            try:
                if self._mock_server: # mock/testing mode
                    conn = await asyncssh.connect(host=self._mock_server.hostname,port=self._mock_server.port,client_keys=[k],known_hosts=None,**kwargs)
                else:
                    conn = await asyncssh.connect(host=instance.get_dns_addr(),username=instance.get_config('img_username'),client_keys=[k],known_hosts=None,**kwargs) #,password=’mypassword’)
                break
            except asyncssh.PermissionDenied as pde:
                # we need to forward this higher up so we can handle the private key issue
                self.debug(1,pde)
                if retrys_key == 0:
                    self.debug(1,"The key seems to have changed for instance {0}. Recreating instance.".format(instance.get_name()),color=bcolors.WARNING)
                    await self.hard_reset_instance(instance)
                    await self._wait_for_instance(instance) 
                    retrys_key += 1
                    self.debug(1,"Retrying ...")
                elif retrys_key == 1:
                    # we tried to refresh the instance but it did not work
                    # this means the remote key stored in AWS, doesnt match the local .pem private key
                    # refresh it ...
                    await self._refresh_instance_key(instance,True) 
                    retrys_key += 1
                    self.debug(1,"Retrying ...")

            except Exception as cexc:
                # check whats going on
                self.update_instance_info(instance)
                if instance.get_state() != KatapultInstanceState.RUNNING:
                    await self._wait_for_instance(instance)
                if retrys < 5:
                    self.debug(1,cexc)
                    await asyncio.sleep(4)
                    self.debug(1,"Retrying ...")
                    retrys = retrys + 1
                elif retrys == 5 and instance.get_state() == KatapultInstanceState.RUNNING:
                    retrys = retrys + 1
                    self.debug(1,"Trying a reboot ...")
                    self.reboot_instance(instance)
                    await asyncio.sleep(4)
                    await self._wait_for_instance(instance)
                elif retrys == 6 and instance.get_state() == KatapultInstanceState.RUNNING:
                    retrys = retrys + 1
                    self.debug(1,"Trying a hard reset ...")
                    await self.hard_reset_instance(instance)
                    await asyncio.sleep(4)
                    await self._wait_for_instance(instance)
                else:
                    self.debug(1,cexc)
                    self.debug(0,"ERROR! instance is unreachable: ",instance,color=bcolors.FAIL)
                    return None
            # except OSError as ose:
            #     if retrys < 5:
            #         self.debug(1,ose)
            #         await asyncio.sleep(4)
            #         self.debug(1,"Retrying (2) ...")
            #         retrys = retrys + 1
            #     else:
            #         self.debug(1,cexc)
            #         self.debug(0,"ERROR! instance is unreachable: ",instance)
            #         return None

        self.debug(1,"connected to ",instance.get_ip_addr())    

        return conn              


    async def _exec_command(self,ssh_conn,command):
        self.debug(2,"Executing ",format( command ))
        try:
            proc = await ssh_conn.create_process(command)
            return proc.stdout , proc.stderr 
        except (OSError, asyncssh.Error) as sshe:
            self.debug(1,'SSH connection failed: ' + str(sshe),color=bcolors.FAIL)
            #self.debug(1,"The SSH Client has been disconnected!")
            self.debug(2,sshe)
            raise sshe
            
    async def _run_ssh_commands(self,instance,ssh_conn,commands):
        for command in commands:
            self.debug(2,"Executing ",format( command['cmd'] ),"output",command['out'])
            try:
                if command['out']:
                    async with ssh_conn.create_process(command['cmd']) as proc:
                        # for l in line_buffered(proc.stdout):
                        #     self.debug(1,l,end='')
                        async for line in proc.stdout:
                            if not line:
                                break
                            self.debug(1,line,end='')

                        errmsg = await proc.stderr.read()
                        dbglvl = 1 if errmsg else 2
                        self.debug(dbglvl,"Errors")
                        self.debug(dbglvl,errmsg)

                else:
                    if not 'output' in command:
                        output = instance.path_join( instance.get_home_dir() , 'run' , 'out.log' )
                    else:
                        output = command['output']
                    await ssh_conn.create_process("rm " + output + ";" + command['cmd'] + " 1>"+output+" 2>&1 &")
            except (OSError, asyncssh.Error) as sshe:
                self.debug(1,'SSH connection failed: ' + str(sshe),color=bcolors.FAIL)
                #self.debug(1,"The SSH Client has been disconnected!")
                self.debug(2,sshe)
                raise sshe

    async def sftp_put_remote_file(self,ftp_client,name):
        ofile = await ftp_client.open(name,'w')
        await ofile.write(self._get_remote_file(name))
        await ofile.close()

    async def sftp_put_string(self,ftp_client,name,string):
        ofile = await ftp_client.open(name,'w')
        await ofile.write(string)
        await ofile.close()

    async def sftp_put_bytes(self,ftp_client,name,bytes_,encoding='utf-8'):
        #byte_str = bytes_io.read()
        # Convert to a "unicode" object
        string = bytes_.decode(encoding)
        ofile = await ftp_client.open(name,'w',encoding=encoding)
        await ofile.write(string)
        await ofile.close()

    async def _test_reupload(self,instance,file_test,ssh_conn,isfile=True):
        re_upload = False
        if isfile:
            stdout0, stderr0 = await self._exec_command(ssh_conn,"[ -f "+file_test+" ] && echo \"ok\" || echo \"not_ok\";")
        else:
            stdout0, stderr0 = await self._exec_command(ssh_conn,"[ -d "+file_test+" ] && echo \"ok\" || echo \"not_ok\";")
        result = await stdout0.read()
        if "not_ok" in result: #result.decode():
            debug(1,"re-upload of files ...")
            re_upload = True
        return re_upload                

    def _get_instancetypes_attribute(self,inst_cfg,resource_file,type_col,attr,return_type):

        # Could be any dot-separated package or module name or a "Requirement"
        resource_package = 'katapult'
        resource_path = os.sep.join(('resources', resource_file))  # Do not use os.path.join()
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
                    return res
                elif return_type == int:
                    try:
                        res = int(row[attr])
                    except:
                        return None
                    return res 
                elif return_type == str:
                    return row[attr]
                else:
                    return raw[attr]
        return         

    def _get_resource_file(self,resource_file):
        resource_package = 'katapult'
        resource_path = os.sep.join(('resources', resource_file))  # Do not use os.path.join()
        #return pkg_resources.resource_stream(resource_package, resource_path)  
        return pkg_resources.resource_string(resource_package, resource_path).decode()

    def _get_remote_file(self,file):
        return self._get_resource_file(os.sep.join(('remote_files',file)))
    
    def _get_session_out_dir(self,out_dir,run_session,instance=None):
        file_name = 'session-'+str(run_session.get_number())+'-'+run_session.get_id()
        if not instance:
            return os.path.join(out_dir,file_name)        
        else:
            return instance.path_join(out_dir,file_name)    

    # Cloud Stuff
          
    def get_key_filename(self,profile_name,region):
        userid = profile_name
        if not userid:
            userid = 'default'
        #key_filename = 'katapult-'+str(userid)+'-'+str(region)+'.pem'
        #key_filename = 'katapult-'+str(region)+'.pem'
        key_filename = 'katapult-'+self.get_account_id()+'-'+str(region)+'.pem'
        return key_filename

    def get_keypair_name(self,profile_name,region):
        userid = profile_name
        if not userid:
            userid = 'default'
        #key_filename = kt_keypairName+'-'+str(userid)+'-'+str(region)
        key_filename = kt_keypairName+'-'+str(region)
        return key_filename

    @abstractmethod
    def get_region(self):
        pass

    @abstractmethod
    def get_account_id(self):
        pass

    # @abstractmethod
    # def get_user_id(self):
    #     pass

    @abstractmethod
    def set_profile(self,profile_name):
        pass

    @abstractmethod
    def retrieve_keypair(self,region):
        pass

    @abstractmethod
    def create_keypair(self,region):
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
    async def reset_instance(self,instance):
        pass

    @abstractmethod
    def update_instance_info(self,instance):
        pass

    @abstractmethod
    def get_suggested_image(self,region):
        pass

    @abstractmethod
    def version(self):
        pass

    # Core API 

    @abstractmethod
    async def wakeup(self):
        pass

    @abstractmethod
    async def start(self,reset=False):
        pass

    def _save_config(self):
        with open(self._provider_config,'w') as config_file:
            config_file.write( json.dumps(self._config,indent=4) )

    def resolve_config(self,config_list_obj,key_name):
        # config could be a file path
        if isinstance(config_list_obj,str) and os.path.isfile(config_list_obj):
            config = get_config(config_list_obj)
        # config could be a json string stream
        elif isinstance(config_list_obj,str):
            try:
                config = json.loads(config_list_obj)
            except:
                config = dict()
        # config could be an array (of instances, envs or jobs specs)
        elif isinstance(config_list_obj,list):
            config = { key_name : config_list_obj }
        # config could be a katapult-compatible config
        elif isinstance(config_list_obj,dict) and key_name in config_list_obj:
            config = config_list_obj
        # config could be a singleton instance,env or job config
        elif isinstance(config_list_obj,dict):
            config = { key_name : [ config_list_obj ] }
        # other cases
        else:
            config = dict()
    
        return config

    def _init_hidden_properties(self,config,key_name=None):
        keys_list = [ key_name ] if key_name is not None else K_OBJECTS
        for objs_key in keys_list:
            if config.get(objs_key):
                for cfg in config[objs_key]:
                    if K_LOADED not in cfg:
                        cfg[K_LOADED] = False # make sure we mark it as not-loaded
                    if K_CFG_UID not in cfg: 
                        cfg[K_CFG_UID] = katapultutils.generate_unique_id(True) # this will help trace what's been loaded in the generated objects ..

        
    def _cfg_add_objects(self,key_name,config_list_obj,save=True,**kwargs):

        config = self.resolve_config(config_list_obj,key_name)

        self.debug(2,"ADDING objects",config)
        
        self._init_hidden_properties(config,key_name)

        if key_name not in config:
            self.debug(1,"No "+key_name+" specified in config file",config)
            return
        
        if key_name not in self._config:
            self._config[key_name] = []

        for cfg in config[key_name]:
            self._config[key_name].append( cfg )

        # no need, this only plays with global vars...
        # self._init(self._config)
        if save:
            self._save_config()

    async def cfg_add_instances(self,config,**kwargs):
        KatapultProvider._cfg_add_objects(self,'instances',config,True,**kwargs)

    async def cfg_add_environments(self,config,**kwargs):
        KatapultProvider._cfg_add_objects(self,'environments',config,True,**kwargs)

    async def cfg_add_jobs(self,config,**kwargs):
        KatapultProvider._cfg_add_objects(self,'jobs',config,True,**kwargs)

    async def cfg_add_config(self,config,**kwargs):
        KatapultProvider._cfg_add_objects(self,'instances',config,False,**kwargs)
        KatapultProvider._cfg_add_objects(self,'environments',config,False,**kwargs)
        KatapultProvider._cfg_add_objects(self,'jobs',config,False,**kwargs)
        self._save_config()

    async def cfg_reset(self):
        config = copy.deepcopy(self._config)
        if os.path.isfile(self._provider_config):
            try:
                os.remove(self._provider_config)
            except:
                pass
        # removing objects from config:
        config['instances']    = []
        config['environments'] = []
        config['jobs']         = []

        self._init(config,provider_config=self._provider_config)  

    @abstractmethod
    async def get_run_session(self,session_id):
        pass

    @abstractmethod
    async def get_instance(self,instance_name,**kwargs):
        pass

    @abstractmethod
    async def get_environment(self,env_hash,**kwargs):
        pass

    @abstractmethod
    async def get_job(self,job_id,**kwargs):
        pass

    @abstractmethod
    async def get_num_active_processes(self,run_session=None):
        pass
        
    @abstractmethod
    async def get_num_instances(self):
        pass

    @abstractmethod
    async def deploy(self,**kwargs):
        pass

    @abstractmethod
    async def run(self,continue_session=False):
        pass

    @abstractmethod
    async def kill(self,identifier):
        pass

    @abstractmethod
    async def wait(self,job_state,run_session=None):
        pass

    @abstractmethod
    async def get_jobs_states(self,run_session=None):
        pass

    @abstractmethod
    async def print_jobs_summary(self,run_session=None,instance=None):
        pass

    @abstractmethod
    async def print_aborted_logs(self,run_session=None,instance=None):
        pass

    @abstractmethod
    async def print_objects(self):
        pass

    @abstractmethod
    async def clear_results_dir(self,directory=None):
        pass

    @abstractmethod
    async def fetch_results(self,directory=None,run_session=None,use_cached=True,use_normal_output=False):
        pass

    @abstractmethod
    async def finalize(self):
        pass 

    @abstractmethod
    async def get_objects(self):
        pass 

# COMM between light and fat client
def stream_dump(obj):
    if isinstance(obj,list):
        strdump = []
        for v in obj:
            strdump.append(stream_dump(v))
        return strdump
    elif isinstance(obj,dict):
        strdump = {}
        for k,v in obj.items():
            strdump[k] = stream_dump(v)
        return strdump
    elif isinstance(obj,KatapultRunSession):
        return { 'class': type(obj).__name__ , 'id': obj.get_id() }
    elif isinstance(obj,KatapultInstance):
        return { 'class': type(obj).__name__ , 'name':obj.get_name() , 'config':obj.get_config_DIRTY() }
    elif isinstance(obj,KatapultEnvironment):
        return { 'class': type(obj).__name__ , 'hash':obj.get_hash() , 'config':obj.get_config_DIRTY() }
    elif isinstance(obj,KatapultJob):
        return { 'class': type(obj).__name__ , 'id':obj.get_id() , 'config':obj.get_config_DIRTY() }
    # elif isinstance(obj,KatapultProcess):
    #     return { 'class': type(obj).__name__ , 'job': stream_dump(obj.get_job()) , 'uid':obj.get_uid() , 'state': obj.get_state() , 'substate': obj.get_substate() , 'aborted_reason': obj.get_aborted_reason()}
    else:
        return obj      

def stream_load(kt_client,jsondata):
    if isinstance(jsondata,list):
        result = []
        for v in jsondata:
            result.append(stream_load(kt_client,v))
        return result
    elif isinstance(jsondata,dict):
        if jsondata.get('class') in [ 'KatapultRunSession' , 'KatapultRunSessionProxy' ]:
            session_id     = jsondata['id'].strip()
            return kt_client.get_run_session(session_id)
        elif jsondata.get('class') in [ 'KatapultInstance' , 'KatapultInstanceProxy' ]:
            instance_name = jsondata['name'].strip()
            instance_cfg  = jsondata.get('config')
            return kt_client.get_instance(instance_name,config=instance_cfg)    
        elif jsondata.get('class') in [ 'KatapultEnvironment' , 'KatapultEnvironmentProxy' ]:
            env_hash = jsondata['hash'].strip()
            env_cfg  = jsondata.get('config')
            return kt_client.get_environment(env_hash,config=env_cfg)    
        elif jsondata.get('class') in [ 'KatapultJob' , 'KatapultJobProxy' ]:
            job_id   = jsondata['id'].strip()
            job_cfg  = jsondata.get('config')
            return kt_client.get_job(job_id,config=job_cfg)    
        else:        
            result = {}
            for k,v in jsondata.items():
                result[k] = stream_load(kt_client,v)
            return result
    else:
        return jsondata             

def get_config(path):
    config_file = path
    configdir   = os.path.dirname(config_file)
    configbase  = os.path.basename(config_file)
    config_name , config_extension = os.path.splitext(configbase)

    if config_extension=='.json':
        try:
            if os.path.exists(config_file):
                with open(config_file,'r') as config_file:
                    config = json.loads(config_file.read())
                print("loaded config from json file")
            else:
                config = None
        except:
            config = None
    elif config_extension=='.py':
        try:
            # sys.path.append(os.path.abspath(configdir))
            # configModule = __import__(config_name,globals(),locals())
            # config = configModule.config
            spec = importlib.util.spec_from_file_location("", os.path.join(os.getcwd(),config_file))
            foo = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(foo)
            config = foo.config
        except ModuleNotFoundError as mfe:
            config = None
        except:
            config = None
    else:
        return None
    return config

def get_standard_python_librairies():
    #https://stackoverflow.com/questions/6463918/how-to-get-a-list-of-all-the-python-standard-library-modules
    import distutils.sysconfig as sysconfig
    import os
    result = []
    std_lib = sysconfig.get_python_lib(standard_lib=True)
    for top, dirs, files in os.walk(std_lib):
        for nm in files:
            if nm != '__init__.py' and nm[-3:] == '.py':
                result.append( os.path.join(top, nm)[len(std_lib)+1:-3].replace(os.sep, '.') )
    
    # double it with this ...
    from katapult.isort.stdlibs.py39 import stdlib
    for lib in stdlib:
        result.append(lib)
    result.append('.code')
    result.append('.pytest')
    return result

def guess_environment(envname,dir):
    environment_obj = {
        # 'command'    : None ,
        # 'env_aptget' : None , 
        'env_conda'  : [] , 
        'env_pypi'   : [] , 
        'env_julia'  : [] ,
        'name'       : envname 
    }

    librairies = get_standard_python_librairies()

    julia_added = False

    files_to_upload = []

    # https://stackoverflow.com/questions/13454164/os-walk-without-hidden-folders
    for root, dirs, files in os.walk(".", topdown=True):
        # update dirs to ignore hidden directories for next recursion
        dirs[:] = [d for d in dirs if not d[0] == '.']

        for name in files:
            file_path = os.path.join(root, name)
            file_name, file_extension = os.path.splitext(name)   
            if file_extension:
                file_extension = file_extension.lower()   

            if file_extension == '.py':
                files_to_upload.append(file_path)
                with open(file_path,'r') as the_file:
                    try:
                        file_content = the_file.read()
                    except:
                        continue
                    packages = re.findall(r"\s*(from\s+([^\s]+)\s+import\s+([^\s]+)|import\s+([^\s]+).*)",file_content)
                    for pkg in packages:
                        if pkg[3]:
                            pkg_name = pkg[3]
                        elif pkg[1] and pkg[2]:
                            pkg_name = pkg[1] #"{0}.{1}".format(pkg[1],pkg[2])
                        else:
                            pkg_name = None
                        if pkg_name.startswith('.'):
                            continue
                        if pkg_name.startswith('_'):
                            continue
                        #if '#' in pkg[0] and pkg[0].index('#') < pkg[0].
                        if '.' in pkg_name:
                            pkg_name = pkg_name[:pkg_name.index('.')]
                        if not pkg_name:
                            continue
                        if pkg_name in librairies:
                            continue
                        if pkg_name in environment_obj['env_pypi']:
                            continue
                        environment_obj['env_pypi'].append(pkg_name)
            
            elif file_extension == '.jl':
                files_to_upload.append(file_path)
                if not julia_added:
                    environment_obj['env_conda'].append('julia')
                    julia_added = True

                with open(file_path,'r') as the_file:
                    try:
                        file_content = the_file.read()
                    except:
                        continue
                    packages = re.findall(r"(Pkg\.add\(\"([^\^\")]+)\"\)|using\s+([^\s]+))",file_content)
                    for pkg in packages:
                        if pkg[2]:
                            pkg_name = pkg[2]
                        elif pkg[1]:
                            pkg_name = pkg[1]
                        else:
                            pkg_name = None
                        if not pkg_name:
                            continue
                        if pkg_name in environment_obj['env_julia']:
                            continue
                        environment_obj['env_julia'].append(pkg_name)

    return environment_obj , files_to_upload      


def get_client(config_=None,**kwargs):

    provider_config = kwargs.get('provider_config') or PROVIDER_CONFIG

    if isinstance(config_,str): 
        config = get_config(config_)
    elif isinstance(config_,dict):
        config = config_
    else: # get the auto-saved config
        config = get_config(provider_config)

    if config is None:
        debug(1,"You need to specify a valid configuration path",color=bcolors.FAIL)
        debug(1,"(could also not find default config file",provider_config,")",color=bcolors.FAIL)
        raise KatapultError()

    if config.get('provider','aws') == 'aws':

        if config.get('maestro','local') == 'local':
            
            craws  = __import__("katapult.aws")

            client = craws.aws.AWSKatapultFatProvider(config,**kwargs)

            print("Using",client.version())

            return client

        else:

            craws  = __import__("katapult.aws")

            client = craws.aws.AWSKatapultLightProvider(config,**kwargs)

            print("Using",client.version())

            return client

    else:

        debug(1,config.get('provider'), " not implemented yet")

        raise KatapultError()


def get_vscode_client(args):
    
    env_obj , the_files = guess_environment('vscode','.')
    
    config = {
        'project'      : 'vscode' ,
        'profile'      : args.profile , 
        'debug'        : 1 ,
        'maestro'      : 'local' , # one shot is local
        'auto_stop'    : False ,
        'recover'      : False ,
        'mutualize_uploads' : False , # put uploads in the job directory, cause we will move things around later...
        'instances'    : [
            {
                'type'         : args.type or 't3.micro' ,
                'number'       : 1 ,
                'region'       : args.region
            }
        ] ,
        'environments' : [ env_obj ] ,
        'jobs' : [
            {
                'run_command' : 'ls' , # foo command ,
                'upload_files' : the_files , # we're using this feature to upload files
                'input_files' : None , 
                'output_files' : 'foo_out.dat' # foo
            }
        ]
    }
    client = get_client(config,state_file='state.vscode.pickle',provider_config='state.vscode.config.json')  
    return client

def get_rundir_client(args):
    
    env_obj , the_files = guess_environment('run_dir','.')

    if args.output_files:
        output_files = args.output_files.split(",")
    else:
        output_files = None
    
    config = {
        'project'      : 'run_dir' ,
        'profile'      : args.profile , 
        'debug'        : 1 ,
        'maestro'      : 'local' , # one shot is local
        'auto_stop'    : False ,
        'recover'      : True ,
        'mutualize_uploads' : False , # put uploads in the job directory, cause we will move things around later...
        'instances'    : [
            {
                'type'         : args.type or 't3.micro' ,
                'number'       : 1 ,
                'region'       : args.region
            }
        ] ,
        'environments' : [ env_obj ] ,
        'jobs' : [
            {
                'run_script' : args.script_file , 
                'upload_files' : the_files , 
                'input_files' : None ,
                'output_files' : output_files
            }
        ]
    }
    client = get_client(config,state_file='state.rundir.pickle',provider_config='state.rundir.config.json')  
    return client    

def line_buffered(f):
    line_buf = ""
    doContinue = True
    try :
        while doContinue and not f.channel.get_exit_signal():
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

def escape_arg_for_send(args):
    if not args:
        return args
    args_escaped = []
    for i,arg in enumerate(args):
        if isinstance(arg,dict):
            arg = json.dump(arg)
        elif not isinstance(arg,str):
            arg = str(arg)
        arg = arg.replace("\"","\\\"")
        args_escaped.append(arg)
    return args_escaped  

def make_client_command(maestro_command,args,escape=True):

    # OLD SERIALIZATION METHOD (cf. maestroserver.py too)

    # if not args:
    #     the_command = maestro_command
    # else:
    #     if not isinstance(args,list):
    #         args = [ args ]
    #     args = escape_arg_for_send(args)
    #     the_command = COMMAND_ARGS_SEP.join( [ maestro_command , ARGS_SEP.join(args) ] )

    if args and not isinstance(args,list):
        args = [ args ]
    the_command = json.dumps({'cmd':maestro_command,'args':args})

    # escape for stream
    # Note: especially if we have 'run_command' in the jobs description
    # we need to double escape ... example: { "run_command" : "python3 -c \".....\"" }
    if escape:
        #the_command = "\""+the_command.replace("\"","\\\"")+"\""
        the_command = "\""+the_command.replace("\\\"","|*|*|*|").replace("\"","\\\"").replace("|*|*|*|","\\\\\\\"")+"\""
        #the_command = "\""+re.sub(r'([^\])"', r'\g<1>\"', the_command)+"\"" # this escape not-already-escaped quotes...

    return the_command

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
            if not sys.stdout: # or sys.stdout.closed==True:
                return

            if DBG_PREFIX:
                print(DBG_PREFIX,*args,**kwargs)
            else:
                print(*args,**kwargs)
            sys.stdout.flush()
            sys.stderr.flush()
        except:
            pass

def get_EOL_conversion(instance,files_path):
    if 'win' in sys.platform.lower():
        this_platform = KatapultPlatform.WINDOWS
    else:
        this_platform = KatapultPlatform.LINUX
    
    if this_platform != instance.get_platform():
        if this_platform == KatapultPlatform.WINDOWS:
            return "sed -i -e 's/\r$//' "+files_path 
        else:
            raise Error("not implemented yet")
    else:
        return None

def convert_EOL(instance,file_content):
    WINDOWS_LINE_ENDING = b'\r\n'
    UNIX_LINE_ENDING = b'\n'
    
    if 'win' in sys.platform.lower():
        this_platform = KatapultPlatform.WINDOWS
    else:
        this_platform = KatapultPlatform.LINUX
    
    if this_platform != instance.get_platform():
        origin = WINDOWS_LINE_ENDING if this_platform==KatapultPlatform.WINDOWS else UNIX_LINE_ENDING
        dest   = WINDOWS_LINE_ENDING if instance.get_platform()==KatapultPlatform.WINDOWS else UNIX_LINE_ENDING
        file_content = file_content.replace(origin, dest)
        return file_content
