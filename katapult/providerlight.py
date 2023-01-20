
from abc import ABC , abstractmethod
from katapult.provider import KatapultProvider , stream_load , stream_dump , line_buffered , make_client_command , STREAM_RESULT, DIRECTORY_TMP , get_EOL_conversion
from katapult.core import *
from katapult.attrs import *
import copy , io
from zipfile import ZipFile
import sys , os , fnmatch
import re , json
from os.path import basename
import pkg_resources
import time
import random
import shutil
import asyncssh
import asyncio
import platform

random.seed()

####################################
# Client handling MAESTRO instance #
####################################

class KatapultLightProvider(KatapultProvider,ABC):

    def __init__(self,conf=None,**kwargs):

        KatapultProvider.__init__(self,conf,**kwargs)

        #self._install_maestro()

    def _init(self,conf,**kwargs):
        self.ssh_conn   = None
        self.ftp_client = None
        self._current_session = None
        super()._init(conf,**kwargs)
        self._load()
    
    def _load(self):
        self._maestro = None
        if self._config.get('maestro')=='remote':
            if not self._config.get('instances') or len(self._config.get('instances'))==0:
                self.debug(2,"There are no instances to watch - skipping maestro creation")
                return
            else:
                # let's try to match the region of the first instance ...
                region = None
                if len(self._config.get('instances')) > 0:
                    region = self._config.get('instances')[0].get('region')
                if not region:
                    region = self.get_region()

                img_id , img_user , img_type = self.get_suggested_image(region)
                if not img_id:
                    self.debug(1,"Using first instance information to create MAESTRO")
                    img_id   = self._config.get('instances')[0].get('img_id')
                    img_user = self._config.get('instances')[0].get('img_username')
                    img_type = self._config.get('instances')[0].get('img_type')
                
                maestro_cfg = { 
                    'maestro'      : True ,
                    'img_id'       : img_id ,
                    'img_username' : img_user ,                 
                    'type'         : img_type , 
                    'dev'          : self._config.get('dev',False) ,
                    'project'      : self._config.get('project',None) ,
                    'region'       : region ,
                    '_maestro_name_proj' : self._config.get('_maestro_name_proj',False)
                }
                self._maestro = KatapultInstance(maestro_cfg,None)

    async def _deploy_maestro(self,reset):
        # deploy the maestro ...
        if self._maestro is None:
            self.debug(2,"no MAESTRO object to deploy")
            return

        # wait for maestro to be ready
        instanceid , ssh_conn , ftp_client = await self._wait_and_connect(self._maestro)

        home_dir = self._maestro.get_home_dir()
        katapult_dir = self._maestro.path_join( home_dir , 'katapult' )
        files_dir = self._maestro.path_join( katapult_dir , 'files' )
        ready_file = self._maestro.path_join( katapult_dir , 'ready' )
        maestro_file = self._maestro.path_join( home_dir , 'maestro' )
        aws_dir = self._maestro.path_join( home_dir , '.aws' )
        aws_config = self._maestro.path_join( aws_dir , 'config' )
        if self._maestro.get_platform() == KatapultPlatform.LINUX or self._maestro.get_platform() == KatapultPlatform.WINDOWS_WSL :
            activate_file = self._maestro.path_join( katapult_dir , '.venv' , 'maestro' , 'bin' , 'activate' )
        elif self._maestro.get_platform() == KatapultPlatform.WINDOWS:
            activate_file = self._maestro.path_join( katapult_dir , '.venv' , 'maestro' , 'Scripts' , 'activate.bat' )
        elif self._maestro.get_platform() == KatapultPlatform.UNKNOWN:
            if 'windows' in platform.system().lower():
                activate_file = os.path.join( katapult_dir , '.venv' , 'maestro' , 'Scripts' , 'activate.bat' )
            else:
                activate_file = self._maestro.path_join( katapult_dir , '.venv' , 'maestro' , 'bin' , 'activate' )
        elif self._maestro.get_platform() == KatapultPlatform.MOCK:
            if 'windows' in platform.system().lower():
                activate_file = os.path.join( katapult_dir , '.venv' , 'maestro' , 'Scripts' , 'activate.bat' )
            else:
                activate_file = self._maestro.path_join( katapult_dir , '.venv' , 'maestro' , 'bin' , 'activate' )

        re_init  = await self._test_reupload(self._maestro,ready_file, ssh_conn)

        if re_init:
            # remove the file
            stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(ssh_conn,ftp_client,'rm -f ' + ready_file )
            # make katapult dir
            stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(ssh_conn,ftp_client,'mkdir -p ' + files_dir ) 
            # mark it as maestro...
            stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(ssh_conn,ftp_client,'echo "" > ' + maestro_file ) 
            # add manually the 
            if self._config.get('profile'):
                profile = self._config.get('profile')
                region  = self.get_region() # we have a profile so this returns the region for this profile
                aws_config_cmd = "mkdir -p "+aws_dir+" && echo \"[profile "+profile+"]\nregion = " + region + "\noutput = json\" > " + aws_config
                stdout , stderr , ssh_conn , ftp_client =  await self._exec_maestro_command_simple(ssh_conn,ftp_client,aws_config_cmd)
            # grant its admin rights (we need to be (stopped or) running to be able to do that)
            self.grant_admin_rights(self._maestro)
            # setup auto_stop behavior for maestro
            self.setup_auto_stop(self._maestro)
            # deploy Katapult on the maestro
            await self._deploy_katapult(ssh_conn,ftp_client)
            # mark as ready
            stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(ssh_conn,ftp_client,'if [ -f '+activate_file+' ]; then echo "" > '+ready_file+' ; fi')

        # deploy the config to the maestro (every time)
        await self._deploy_config(ssh_conn,ftp_client)

        # let's redeploy the code every time for now ... (if not already done in re_init)
        if not re_init and reset:
            await self._deploy_katapult_files(ssh_conn,ftp_client)

        # start the server (if not already started)
        await self._run_server(ssh_conn)

        # wait for maestro to have started
        await self._wait_for_maestro(ssh_conn)

        #time.sleep(30)

        self.ssh_conn = ssh_conn
        self.ftp_client = ftp_client
        #ftp_client.close()
        #ssh_conn.close()

        self.debug(1,"MAESTRO is READY",color=bcolors.OKCYAN)


    async def _deploy_katapult_files(self,ssh_conn,ftp_client):
        await ftp_client.chdir(self._get_katapult_dir())
        # CP437 is IBM zip file encoding
        await self.sftp_put_bytes(ftp_client,'katapult.zip',self._create_katapult_zip(),'CP437')
        commands = [
            { 'cmd' : 'cd '+self._get_katapult_dir()+' && unzip -o katapult.zip && rm katapult.zip' , 'out' : True } ,
        ]
        await self._run_ssh_commands(self._maestro,ssh_conn,commands) 
        
        filesOfDirectory = os.listdir('.')
        pattern = "katapult*.pem"
        for file in filesOfDirectory:
            if fnmatch.fnmatch(file, pattern):
                await ftp_client.put(os.path.abspath(file),os.path.basename(file))
        sh_files = self._get_remote_files_path( '*.sh')
        commands = [
            { 'cmd' : 'chmod +x ' + sh_files , 'out' : True } ,
        ]
        eol_command = get_EOL_conversion(self._maestro,sh_files)
        if eol_command:
            commands.append({'cmd':eol_command,'out':True})

        await self._run_ssh_commands(self._maestro,ssh_conn,commands) 


    async def _deploy_katapult(self,ssh_conn,ftp_client):

        # upload katapult files
        await self._deploy_katapult_files(ssh_conn,ftp_client)
        
        maestroenv_sh = self._get_remote_files_path( 'maestroenv.sh' )
        # unzip katapult files, install and run
        commands = [
            { 'cmd' : maestroenv_sh , 'out' : True } ,
        ]
        await self._run_ssh_commands(self._maestro,ssh_conn,commands)

    async def _run_server(self,ssh_conn):
        # run the server
        startmaestro_sh = self._get_remote_files_path( 'startmaestro.sh' )
        commands = [
            { 'cmd' : startmaestro_sh , 'out' : False , 'output' : 'maestro.log' },
            { 'cmd' : 'crontab -r ; echo "* * * * * '+startmaestro_sh+' auto_init" | crontab', 'out' : True }
        ]
        await self._run_ssh_commands(self._maestro,ssh_conn,commands)

        # we have separated run and init and start 
        # we need to init with the deployed config
        self.debug(1,"initialize server with config")
        init_objects = await self._exec_maestro_command("init","config.json")
        
        self._update_K_loaded(init_objects)

        # TODO: improve return result from init and match whats been loaded and what has not
        # (same as cfg_add_***)
        # for objs_key in ['instances','environments','jobs']:
        #     if self._config.get(objs_key):
        #         for obj_cfg in self._config[objs_key]:
        #             obj_cfg[K_LOADED]=True

    async def _deploy_config(self,ssh_conn,ftp_client,config_filename='config.json',only_new=False):

        config , mkdir_cmd , files_to_upload_per_dir = self._translate_config_for_maestro(only_new)

        # we can add some keyed arguments to the config ...
        # useful to serialize some arguments between light client and fat client
        # if kwargs and len(kwargs)>0:
        #     config['_kwargs'] = dict()
        #     for k,v in kwargs.items():
        #         config['_kwargs'][k] = stream_dump(v)

        # serialize the config and send it to the maestro
        await ftp_client.chdir(self._get_katapult_dir())
        await self.sftp_put_string(ftp_client,config_filename,json.dumps(config))
        # execute the mkdir_cmd
        if mkdir_cmd:
            stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(ssh_conn,ftp_client,mkdir_cmd)
            await stdout.read()
        for remote_dir , files_infos in files_to_upload_per_dir.items():
            await ftp_client.chdir(remote_dir)
            for file_info in files_infos:
                remote_file = os.path.basename(file_info['remote'])
                try:
                    await ftp_client.put(file_info['local'],remote_file)
                except FileNotFoundError as fnfe:
                    self.debug(1,"You have specified a file that does not exist:",fnfe,color=bcolors.FAIL)
                except asyncssh.sftp.SFTPNoSuchFile as nsf:
                    self.debug(1,"You have specified a file that does not exist:",nsf,remote_dir,file_info,color=bcolors.FAIL)
        return config 

    def _translate_config_for_maestro(self,only_new):
        if only_new:
            config = dict()
            for master_key in self._config:
                if master_key in K_OBJECTS:
                    config[master_key] = []                    
                    for obj_cfg in self._config[master_key]:
                        if obj_cfg.get(K_LOADED) == False:
                            config[master_key].append(copy.deepcopy(obj_cfg))
                else:
                    config[master_key] = copy.deepcopy(self._config[master_key])
        else:
            config = copy.deepcopy(self._config)

        config['maestro'] = 'local' # the config is for maestro, which needs to run local

        config['region'] = self.get_region()

        if config.get('instances'):
            for i , inst_cfg in enumerate(config.get('instances')):
                # we need to freeze the region within each instance config ...
                if not config['instances'][i].get('region'):
                    config['instances'][i]['region'] = self.get_region()

        if config.get('environments'):
            for i , env_cfg in enumerate(config.get('environments')):
                # Note: we are using a simple KatapultEnvironment here 
                # we're not deploying at this stage
                # but this will help use re-use all the business logic in katapultutils envs
                # in order to standardize the environment and create an inline version 
                # through the KatapultEnvironment::json() method
                env = KatapultEnvironment(self._config.get('project'),env_cfg)
                config['environments'][i] = env.get_env_obj()
                config['environments'][i][K_COMPUTED] = True

        files_to_upload = dict()

        if config.get('jobs'):
            for i , job_cfg in enumerate(config.get('jobs')):
                if job_cfg.get('run_script'):
                    run_script = job_cfg.get('run_script')  
                    ref_file0  = run_script
                    args       = ref_file0.split(' ')
                    if args and len(args)>0:
                        ref_file0 = args[0]
                else:
                    ref_file0 = None
                #for attr,use_ref in [ ('run_script',False) , ('upload_files',True) , ('input_files',True) , ('output_files',True) ] :
                for attr,use_ref in [ ('run_script',False) , ('upload_files',True) , ('input_files',True) ] :
                    upfiles = job_cfg.get(attr)
                    ref_file = ref_file0 if use_ref else None
                    if not upfiles:
                        continue
                    if isinstance(upfiles,str):
                        upfiles_split = upfiles.split(' ')
                        if len(upfiles_split)>0:
                            upfiles = upfiles_split[0]
                    if isinstance(upfiles,str):
                        local_abs_path , local_rel_path , remote_abs_path , remote_rel_path , external = self._resolve_maestro_job_paths(upfiles,ref_file,self._get_home_dir())
                        if local_abs_path not in files_to_upload:
                            files_to_upload[local_abs_path] = { 'local' : local_abs_path , 'remote' : remote_abs_path }
                        if attr == 'run_script':
                            args = run_script.split(' ')
                            args[0] = remote_abs_path
                            config['jobs'][i][attr] = (' ').join(args)
                        else:
                            config['jobs'][i][attr] = remote_abs_path
                    else:
                        config['jobs'][i][attr] = []
                        for upfile in upfiles:
                            local_abs_path , local_rel_path , remote_abs_path , remote_rel_path , external = self._resolve_maestro_job_paths(upfile,ref_file,self._get_home_dir())
                            if local_abs_path not in files_to_upload:
                                files_to_upload[local_abs_path] = { 'local' : local_abs_path , 'remote' : remote_abs_path }
                            config['jobs'][i][attr].append(remote_abs_path)
        
        mkdir_cmd = ""
        files_to_upload_per_dir = dict()
        for key,file_info in files_to_upload.items():
            remote_dir = os.path.dirname(file_info['remote'])
            if remote_dir not in files_to_upload_per_dir:
                files_to_upload_per_dir[remote_dir] = []
                mkdir_cmd += "mkdir -p " + remote_dir + ";"
            files_to_upload_per_dir[remote_dir].append(file_info)

        self.debug(2,config)

        return config , mkdir_cmd , files_to_upload_per_dir

    def _resolve_maestro_job_paths(self,upfile,ref_file,home_dir):
        files_path = self._maestro.path_join( home_dir , 'files' )
        return katapultutils.resolve_paths(self._maestro,upfile,ref_file,files_path,True) # True for mutualized 

    def _get_home_dir(self):
        return self._maestro.get_home_dir()

    def _get_katapult_dir(self):
        return self._maestro.path_join( self._get_home_dir() , 'katapult' )

    def _get_remote_files_path(self,files=None):
        if not files:
            return self._maestro.path_join( self._get_katapult_dir() , 'katapult' , 'resources' , 'remote_files' )        
        else:
            return self._maestro.path_join( self._get_katapult_dir() , 'katapult' , 'resources' , 'remote_files' , files )        

    def _zip_package(self,package_name,src,dest,zipObj):
        dest = os.path.join( dest , os.path.basename(src) ).rstrip( os.sep )
        if pkg_resources.resource_isdir(package_name, src):
            #if not os.path.isdir(dest):
            #    os.makedirs(dest)
            for res in pkg_resources.resource_listdir(package_name, src):
                self.debug(2,'scanning package resource',res)
                self._zip_package(package_name,os.path.join( src , res), dest, zipObj)
        else:
            if os.path.splitext(src)[1] not in [".pyc"] and not src.strip().endswith(".DS_Store"):
                #copy_resource_file(src, dest) 
                data_str = pkg_resources.resource_string(package_name, src)
                self.debug(2,"Writing",src)
                zipObj.writestr(dest,data_str)

    def _create_katapult_zip(self):
        zip_buffer = io.BytesIO()
        # create a ZipFile object
        with ZipFile(zip_buffer, 'w') as zipObj:    
            import katapult as kt
            katapultinit = os.path.abspath(kt.__file__) # this is the __init__.py file
            katapultmodu = os.path.dirname(katapultinit)
            katapultroot = os.path.dirname(katapultmodu)
            for otherfilepath in [ 'requirements.txt' ]:
                opened = False
                for thedir in [katapultmodu , katapultroot ]: # not sure why: Kyel bug Windows
                    thefilepath = os.path.join(thedir,otherfilepath)
                    if os.path.exists(thefilepath):
                        try:
                            with open(thefilepath,'r') as thefile:
                                opened = True
                                data = thefile.read()
                                zipObj.writestr(otherfilepath,data)
                        except:
                            self.debug(1,"Could not open file ",thefilepath,color=bcolors.FAIL)
                            pass
                if not opened:
                    self.debug(1,"Could not open file ",otherfilepath,color=bcolors.FAIL)
            # write the package
            self._zip_package("katapult",".","katapult",zipObj)

        self.debug(2,"ZIP BUFFER SIZE =",zip_buffer.getbuffer().nbytes)

        # very important...
        zip_buffer.seek(0)

        return zip_buffer.getvalue() #.getbuffer()

    async def _wait_for_maestro(self,ssh_conn):
        #if self.ssh_conn is None:
        #    instanceid , self.ssh_conn , self.ftp_client = self._wait_and_connect(self._maestro)
        
        waitmaestro_sh = self._get_remote_files_path( 'waitmaestro.sh' )
        cmd = waitmaestro_sh+" 1" # 1 = with tail log

        stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(ssh_conn,None,cmd)      

        try:
            async for line in stdout:
                if not line:
                    break
                self.debug(1,line,end='')
        except asyncssh.misc.ConnectionLost:
            pass
        except StopAsyncIteration:
            pass

        # for l in await line_buffered(stdout):
        #     if not l:
        #         break
        #     self.debug(1,l,end='')

    async def _exec_maestro_command_simple(self,ssh_conn,ftp_client,command_line):
        if ssh_conn is None:
            instanceid , ssh_conn , ftp_client = await self._wait_and_connect(self._maestro)
        retrys = 0 
        while True:
            try:
                stdout,stderr = await self._exec_command(ssh_conn,command_line)      
                return stdout,stderr,ssh_conn,ftp_client
            except (OSError, asyncssh.Error) as e:
                retrys += 1
                if retrys<5:
                    self.debug(1,"Retrying ...",color=bcolors.WARNING)
                    self.debug(2,"Retrying command",maestro_command,color=bcolors.WARNING)
                    await asyncio.sleep(10)
                    instanceid , ssh_conn , ftp_client = await self._wait_and_connect(self._maestro)
                    await self._run_server(ssh_conn)
                else:
                    self.debug(1,"Enough Retries",e,color=bcolors.FAIL)
                    break     
        return None,None,ssh_conn,ftp_client 

    async def _exec_maestro_command(self,maestro_command,raw_args=None):

        # args = None
        # if maestro_command != "init":
        #     if raw_args:
        #         args = []
        #         if isinstance(raw_args,list):
        #             for arg in raw_args:
        #                 # we dont dump the array cause we want to use the separators __,__
        #                 # so we dump the individual array elements
        #                 args.append( stream_dump(arg) ) 
        #         else:
        #             args = stream_dump(raw_args)
        # else:
        #     args = raw_args

        args = stream_dump(raw_args)

        the_command = make_client_command(maestro_command,args)

        if self.ssh_conn is None:
            instanceid , self.ssh_conn , self.ftp_client = await self._wait_and_connect(self._maestro)
        
        # -u for no buffering
        waitmaestro_sh = self._get_remote_files_path( 'waitmaestro.sh' )
        venv_python    = self._maestro.path_join( self._get_katapult_dir() , '.venv' , 'maestro' , 'bin' , 'python3' )

        cmd = "cd "+self._get_katapult_dir()+ " && "+waitmaestro_sh+" && sudo "+venv_python+" -u -m katapult.maestroclient " + the_command

        retrys = 0 

        while True:
            try:
                stdout , stderr = await self._exec_command(self.ssh_conn,cmd)    
                try:
                    async for line in stdout:
                        if not line:
                            break
                        # kinda dirty ... 
                        if line.startswith(STREAM_RESULT):
                            line = line.replace(STREAM_RESULT,'')
                            line = line.strip()
                            self.debug(2,"Got RESULT",line,color=bcolors.OKCYAN)
                            return stream_load(self,json.loads(line)) # result is printed last...
                        else:
                            self.debug(1,line,end='')
                except asyncssh.misc.ConnectionLost:
                    pass
                except StopAsyncIteration:
                    pass
                except:
                    pass
                
                break
            except (OSError, asyncssh.Error):
                retrys += 1
                if retrys<5:
                    await asyncio.sleep(10)
                    self.debug(1,"Retrying _exec_maestro_command",cmd,color=bcolors.WARNING)
                    instanceid , self.ssh_conn , self.ftp_client = await self._wait_and_connect(self._maestro)
                    await self._run_server(self.ssh_conn)
                else:
                    self.debug(1,"Enough tries _exec_maestro_command",color=bcolors.FAIL)
                    break


        return None

        # for l in await line_buffered(stdout):
        #     if not l:
        #         break
        #     self.debug(1,l,end='')
        
        # while True:
        #     outlines = stdout.readlines()
        #     if not outlines:
        #         errlines = stderr.readlines()
        #         for eline in errlines:
        #             self.debug(1,eline,end='')
        #         break
        #     for line in outlines:
        #         self.debug(1,line,end='')
        #     errlines = stderr.readlines()
        #     for eline in errlines:
        #         self.debug(1,eline,end='')

        # for l in line_buffered(stdout):
        #     if not l:
        #         errlines = stderr.readlines()
        #         for eline in errlines:
        #             self.debug(1,eline,end='')
        #         break
        #     self.debug(1,l,end='')
        #     errlines = stderr.readlines()
        #     for eline in errlines:
        #         self.debug(1,eline,end='')


    async def _install_maestro(self,reset):
        # this will block for some time the first time...
        self.debug_set_prefix(bcolors.BOLD+'INSTALLING MAESTRO: '+bcolors.ENDC)
        self._instances_states = dict()        
        self._start_and_update_instance(self._maestro)
        if reset:
            await self.reset_instance(self._maestro)
        await self._deploy_maestro(reset) # deploy the maestro now !
        self.debug_set_prefix(None)       

    async def start(self,reset=False):
        # install maestro materials
        await self._install_maestro(reset)
        # triggers maestro::start
        await self._exec_maestro_command("start",reset)

    def _update_K_loaded(self,objs_result):
        for objs_key in K_OBJECTS:
            if objs_result.get(objs_key) and self._config.get(objs_key):
                for obj in objs_result[objs_key]:
                    o_uid = obj.get_config(K_CFG_UID)
                    if not o_uid:
                        continue
                    for cfg in self._config[objs_key]:
                        c_uid = cfg[K_CFG_UID]
                        if o_uid == c_uid:
                            cfg[K_LOADED] = obj.get_config(K_LOADED) 
                            break           

    async def _cfg_add_objects(self,conf,coroutine,name,**kwargs):
        # complement self._config
        await coroutine(conf,**kwargs)
        # wait for maestro to be ready
        instanceid , ssh_conn , ftp_client = await self._wait_and_connect(self._maestro)
        # config_name
        config_name = 'config_add-' + katapultutils.generate_unique_id() + '.json'
        # deploy the new config to the maestro (every time)
        # (this ensures the deployment of dependent files)
        translated_config = await self._deploy_config(ssh_conn,ftp_client,config_name,True) #True = only new stuff
        # triggers maestro::add_* : use string dump or config file name (either way)
        #await self._exec_maestro_command(name,config_name)
        args = [ translated_config , kwargs ]
        objs = await self._exec_maestro_command(name,args)

        # match loaded stuff in the light client config
        self._update_K_loaded(objs)

        return objs

    async def cfg_add_instances(self,conf,**kwargs):
        return await self._cfg_add_objects(conf,super().cfg_add_instances,"cfg_add_instances",**kwargs)

    async def cfg_add_environments(self,conf,**kwargs):
        return await self._cfg_add_objects(conf,super().cfg_add_environments,"cfg_add_environments",**kwargs)

    async def cfg_add_jobs(self,conf,**kwargs):
        return await self._cfg_add_objects(conf,super().cfg_add_jobs,"cfg_add_jobs",**kwargs)

    async def cfg_add_config(self,conf,**kwargs):
        return await self._cfg_add_objects(conf,super().cfg_add_config,"cfg_add_config",**kwargs)

    async def cfg_reset(self):
        # triggers maestro::reset
        await self._exec_maestro_command("cfg_reset") # use output - the deploy part will be skipped depending on option ...

    async def reset_instance(self,instance):
        self.debug(1,'RESETTING instance',instance.get_name())
        instanceid, ssh_conn , ftp_client = await self._wait_and_connect(instance)
        if ssh_conn is not None:
            await self.sftp_put_remote_file(ftp_client,'resetmaestro.sh')
            resetmaestro_sh = self._maestro.path_join( self._maestro.get_home_dir() , 'resetmaestro.sh' )
            commands = []
            eol_command = get_EOL_conversion(instance,resetmaestro_sh)
            if eol_command:
                commands.append({'cmd':eol_command,'out':True})
            commands.append(
               { 'cmd' : 'chmod +x '+resetmaestro_sh+' && ' + resetmaestro_sh , 'out' : True }
            )
            await self._run_ssh_commands(instance,ssh_conn,commands)
            #ftp_client.close()
            ssh_conn.close()
        self.debug(1,'RESETTING done')

    async def deploy(self,**kwargs):
        # triggers maestro::deploy
        await self._exec_maestro_command("deploy",kwargs) # use output - the deploy part will be skipped depending on option ...

    async def run(self,continue_session=False):
        # triggers maestro::run
        run_session = await self._exec_maestro_command("run",continue_session)
        self._current_session = run_session
        return self._current_session

    async def kill(self,identifier):
        # triggers maestro::kill
        await self._exec_maestro_command("kill",identifier)

    async def wakeup(self):
        await self.start()
        # triggers maestro::wakeup
        await self._exec_maestro_command("wakeup")

    async def wait(self,job_state,run_session=None):
        if run_session is not None:
            args = [ int(job_state) , run_session ]
        else:
            args = [ int(job_state) ]
        # triggers maestro::wait
        await self._exec_maestro_command("wait",args)

    async def get_jobs_states(self,run_session=None,only_ran_processes=False):
        args = [ run_session , only_ran_processes ]
        # triggers maestro::get_jobs_states
        return await self._exec_maestro_command("get_states",args)

    async def print_jobs_summary(self,run_session=None,instance=None):
        if run_session is not None:
            args = [ run_session ]
        else:
            args = []
        if instance is not None:
            args.append(instance.get_name())

        # triggers maestro::print_jobs_summary
        await self._exec_maestro_command("print_summary",args)

    async def print_aborted_logs(self,run_session=None,instance=None):
        if run_session is not None:
            args = [ run_session ]
        else:
            args = []
        if instance is not None:
            args.append(instance.get_name())
        # triggers maestro::print_aborted_logs
        await self._exec_maestro_command("print_aborted",args)

    async def print_objects(self):
        # triggers maestro::print_objects
        await self._exec_maestro_command("print_objects")

    async def clear_results_dir(self,out_dir=None) :

        if out_dir is None:
            out_dir = DIRECTORY_TMP

        if not os.path.isabs(out_dir):
            out_dir = os.path.join(os.getcwd(),out_dir)
        shutil.rmtree(out_dir, ignore_errors=True)    

        if self._maestro:
            homedir     = self._maestro.get_home_dir()
            maestro_dir = self._maestro.path_join( homedir , "katapult_tmp_fetch" )
            await self._exec_maestro_command("clear_results_dir",maestro_dir)


    async def fetch_results(self,out_dir=None,run_session=None,use_cached=True,use_normal_output=False):

        if out_dir is None:
            out_dir = DIRECTORY_TMP

        # out_dir is local
        if not os.path.isabs(out_dir):
            out_dir = os.path.join(os.getcwd(),out_dir)

        if not run_session:
            run_session = self._current_session

        if not run_session:
            self.debug(1,"No session to fetch",color=bcolors.WARNING)
            return None

        session_out_dir  = self._get_session_out_dir(out_dir,run_session)

        # we've already fetched the results (possibly from the watcher process)
        if use_cached and os.path.exists(session_out_dir):
            return session_out_dir

        if session_out_dir and session_out_dir != './':
            try:
                #os.rmdir(out_dir)
                shutil.rmtree(session_out_dir, ignore_errors=True)
            except:
                pass
            try:
                os.makedirs(session_out_dir)
            except:
                pass

        randnum          = str(random.randrange(1000))
        homedir          = self._maestro.get_home_dir()
        maestro_dir      = self._maestro.path_join( homedir , "katapult_tmp_fetch" ) #+ randnum )
        maestro_tar_file = "maestro"+randnum+".tar"
        maestro_tar_path = self._maestro.path_join( homedir , maestro_tar_file )
        session_out_dir_remote = self._get_session_out_dir(maestro_dir,run_session,self._maestro)

        # fetch the results on the maestro
        args = [ maestro_dir , run_session , use_cached , use_normal_output ]
        session_out_dir_remote = await self._exec_maestro_command("fetch_results",args)

        # get the tar file of the results
        stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(None,None,"cd " + session_out_dir_remote + " && tar -cvf "+maestro_tar_path+" .")

        stdout_str = await stdout.read()
        stderr_str = await stderr.read()
        self.debug(1,stdout_str) 
        self.debug(2,stderr_str) 
        local_tar_path = os.path.join(session_out_dir,maestro_tar_file)
        await ftp_client.chdir( homedir )
        await ftp_client.get( maestro_tar_file , local_tar_path )

        # untar
        os.system("tar -xvf "+local_tar_path+" -C "+session_out_dir)

        # cleanup
        os.remove(local_tar_path)
        stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(ssh_conn,ftp_client,"rm -rf "+session_out_dir_remote+" "+maestro_tar_path)

        # close
        #ftp_client.close()
        ssh_conn.close()

        return session_out_dir

    async def finalize(self):
        # triggers maestro::finalize
        try:
            await self._exec_maestro_command("finalize")
        # this will likely happen if auto_stop is one
        except asyncssh.misc.ConnectionLost as cle:
            pass

    # def start_instance(self,instance):
    #     await self._exec_maestro_command("start_instance",instance)

    # def stop_instance(self,instance):
    #     await self._exec_maestro_command("stop_instance",instance)

    # def terminate_instance(self,instance):
    #     await self._exec_maestro_command("terminate_instance",instance)

    # def reboot_instance(self,instance):
    #     await self._exec_maestro_command("reboot_instance",instance)

    async def get_objects(self):
        # triggers maestro::get_objects
        return await self._exec_maestro_command("get_objects")

    def _get_or_create_instance(self,instance):
        instance , created = super()._get_or_create_instance(instance)
        # dangerous !
        #self.add_maestro_security_group(instance)
        # open web server

        return instance , created 

    @abstractmethod
    def grant_admin_rights(self,instance):
        pass

    @abstractmethod
    def add_maestro_security_group(self,instance):
        pass

    @abstractmethod
    def setup_auto_stop(self,instance):
        pass

    # needed by KatapultProvider::_wait_for_instance 
    def serialize_state(self):
        pass

    def get_run_session(self,session_id):
        return KatapultRunSessionProxy( session_id )

    def get_instance(self,instance_name,**kwargs):
        return KatapultInstanceProxy( instance_name , kwargs.get('config') )

    def get_environment(self,env_hash,**kwargs):
        return KatapultEnvironmentProxy( env_hash , kwargs.get('config') )

    def get_job(self,job_id,**kwargs):
        return KatapultJobProxy( job_id , kwargs.get('config') )

    async def get_num_active_processes(self,run_session=None):
        if run_session is None:
            run_session = self._current_session
        if not run_session:
            return 0
        args = [ run_session ]
        num_processes = await self._exec_maestro_command("get_num_active_processes",args)
        return int(num_processes)

    async def get_num_instances(self):
        num_instances = await self._exec_maestro_command("get_num_instances")
        return int(num_instances)


