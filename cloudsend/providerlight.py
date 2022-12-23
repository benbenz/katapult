
from abc import ABC , abstractmethod
from cloudsend.provider import CloudSendProvider , line_buffered , make_client_command , STREAM_RESULT, DIRECTORY_TMP
from cloudsend.core import *
import copy , io
from zipfile import ZipFile
import os , fnmatch
import re , json
from os.path import basename
import pkg_resources
import time
import random
import shutil
import asyncssh
import asyncio

random.seed()

####################################
# Client handling MAESTRO instance #
####################################

class CloudSendLightProvider(CloudSendProvider,ABC):

    def __init__(self,conf=None):

        CloudSendProvider.__init__(self,conf)

        #self._install_maestro()

    def _init(self,conf):
        self.ssh_conn   = None
        self.ftp_client = None
        self._current_session = None
        super()._init(conf)
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
                    'region'       : region
                }
                self._maestro = CloudSendInstance(maestro_cfg,None)

    async def _deploy_maestro(self,reset):
        # deploy the maestro ...
        if self._maestro is None:
            self.debug(2,"no MAESTRO object to deploy")
            return

        # wait for maestro to be ready
        instanceid , ssh_conn , ftp_client = await self._wait_and_connect(self._maestro)

        home_dir = self._maestro.get_home_dir()
        cloudsend_dir = self._maestro.path_join( home_dir , 'cloudsend' )
        files_dir = self._maestro.path_join( cloudsend_dir , 'files' )
        ready_file = self._maestro.path_join( cloudsend_dir , 'ready' )
        maestro_file = self._maestro.path_join( home_dir , 'maestro' )
        aws_dir = self._maestro.path_join( home_dir , '.aws' )
        aws_config = self._maestro.path_join( aws_dir , 'config' )
        if self._maestro.get_platform() == CloudSendPlatform.LINUX or self._maestro.get_platform() == CloudSendPlatform.WINDOWS_WSL :
            activate_file = self._maestro.path_join( cloudsend_dir , '.venv' , 'maestro' , 'bin' , 'activate' )
        elif self._maestro.get_platform() == CloudSendPlatform.WINDOWS:
            activate_file = self._maestro.path_join( cloudsend_dir , '.venv' , 'maestro' , 'Scripts' , 'activate.bat' )
        
        re_init  = await self._test_reupload(self._maestro,ready_file, ssh_conn)

        if re_init:
            # remove the file
            stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(ssh_conn,ftp_client,'rm -f ' + ready_file )
            # make cloudsend dir
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
            # deploy CloudSend on the maestro
            await self._deploy_cloudsend(ssh_conn,ftp_client)
            # mark as ready
            stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(ssh_conn,ftp_client,'if [ -f '+activate_file+' ]; then echo "" > '+ready_file+' ; fi')

        # deploy the config to the maestro (every time)
        await self._deploy_config(ssh_conn,ftp_client)

        # let's redeploy the code every time for now ... (if not already done in re_init)
        if not re_init and reset:
            await self._deploy_cloudsend_files(ssh_conn,ftp_client)

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


    async def _deploy_cloudsend_files(self,ssh_conn,ftp_client):
        await ftp_client.chdir(self._get_cloudsend_dir())
        # CP437 is IBM zip file encoding
        await self.sftp_put_bytes(ftp_client,'cloudsend.zip',self._create_cloudsend_zip(),'CP437')
        commands = [
            { 'cmd' : 'cd '+self._get_cloudsend_dir()+' && unzip -o cloudsend.zip && rm cloudsend.zip' , 'out' : True } ,
        ]
        await self._run_ssh_commands(self._maestro,ssh_conn,commands) 
        
        filesOfDirectory = os.listdir('.')
        pattern = "cloudsend*.pem"
        for file in filesOfDirectory:
            if fnmatch.fnmatch(file, pattern):
                await ftp_client.put(os.path.abspath(file),os.path.basename(file))
        sh_files = self._get_remote_files_path( '*.sh')
        commands = [
            { 'cmd' : 'chmod +x ' + sh_files , 'out' : True } ,
        ]
        await self._run_ssh_commands(self._maestro,ssh_conn,commands) 


    async def _deploy_cloudsend(self,ssh_conn,ftp_client):

        # upload cloudsend files
        await self._deploy_cloudsend_files(ssh_conn,ftp_client)
        
        maestroenv_sh = self._get_remote_files_path( 'maestroenv.sh' )
        # unzip cloudsend files, install and run
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
        await self._exec_maestro_command("init","config.json")

    async def _deploy_config(self,ssh_conn,ftp_client,config_filename='config.json'):
        config , mkdir_cmd , files_to_upload_per_dir = self._translate_config_for_maestro()
        # serialize the config and send it to the maestro
        await ftp_client.chdir(self._get_cloudsend_dir())
        await self.sftp_put_string(ftp_client,config_filename,json.dumps(config))
        # execute the mkdir_cmd
        if mkdir_cmd:
            stdout , stderr , ssh_conn , ftp_client = await self._exec_maestro_command_simple(ssh_conn,ftp_client,mkdir_cmd)
        for remote_dir , files_infos in files_to_upload_per_dir.items():
            await ftp_client.chdir(remote_dir)
            for file_info in files_infos:
                remote_file = os.path.basename(file_info['remote'])
                try:
                    await ftp_client.put(file_info['local'],remote_file)
                except FileNotFoundError as fnfe:
                    self.debug(1,"You have specified a file that does not exist:",fnfe,color=bcolors.FAIL)
        return config 

    def _translate_config_for_maestro(self):
        config = copy.deepcopy(self._config)

        config['maestro'] = 'local' # the config is for maestro, which needs to run local

        config['region'] = self.get_region()

        for i , inst_cfg in enumerate(config.get('instances')):
            # we need to freeze the region within each instance config ...
            if not config['instances'][i].get('region'):
                config['instances'][i]['region'] = self.get_region()

        for i , env_cfg in enumerate(config.get('environments')):
            # Note: we are using a simple CloudSendEnvironment here 
            # we're not deploying at this stage
            # but this will help use re-use all the business logic in cloudsendutils envs
            # in order to standardize the environment and create an inline version 
            # through the CloudSendEnvironment::json() method
            env = CloudSendEnvironment(self._config.get('project'),env_cfg)
            config['environments'][i] = env.get_env_obj()
            config['environments'][i][K_COMPUTED] = True

        files_to_upload = dict()

        for i , job_cfg in enumerate(config.get('jobs')):
            job = CloudSendJob(job_cfg,i)
            run_script = job.get_config('run_script')  
            ref_file0  = run_script
            args       = ref_file0.split(' ')
            if args:
                ref_file0 = args[0]
            #for attr,use_ref in [ ('run_script',False) , ('upload_files',True) , ('input_file',True) , ('output_file',True) ] :
            for attr,use_ref in [ ('run_script',False) , ('upload_files',True) , ('input_file',True) ] :
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
        return cloudsendutils.resolve_paths(self._maestro,upfile,ref_file,files_path,True) # True for mutualized 

    def _get_home_dir(self):
        return self._maestro.get_home_dir()

    def _get_cloudsend_dir(self):
        return self._maestro.path_join( self._get_home_dir() , 'cloudsend' )

    def _get_remote_files_path(self,files=None):
        if not files:
            return self._maestro.path_join( self._get_cloudsend_dir() , 'cloudsend' , 'resources' , 'remote_files' )        
        else:
            return self._maestro.path_join( self._get_cloudsend_dir() , 'cloudsend' , 'resources' , 'remote_files' , files )        

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

    def _create_cloudsend_zip(self):
        zip_buffer = io.BytesIO()
        # create a ZipFile object
        with ZipFile(zip_buffer, 'w') as zipObj:    
            import cloudsend as cs
            cloudsendinit = os.path.abspath(cs.__file__) # this is the __init__.py file
            cloudsendmodu = os.path.dirname(cloudsendinit)
            cloudsendroot = os.path.dirname(cloudsendmodu)
            for otherfilepath in [ 'requirements.txt' ]:
                opened = False
                for thedir in [cloudsendmodu , cloudsendroot ]: # not sure why: Kyel bug Windows
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
            self._zip_package("cloudsend",".","cloudsend",zipObj)

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

    async def _exec_maestro_command(self,maestro_command,args=None):

        the_command = make_client_command(maestro_command,args)

        if self.ssh_conn is None:
            instanceid , self.ssh_conn , self.ftp_client = await self._wait_and_connect(self._maestro)
        
        # -u for no buffering
        waitmaestro_sh = self._get_remote_files_path( 'waitmaestro.sh' )
        venv_python    = self._maestro.path_join( self._get_cloudsend_dir() , '.venv' , 'maestro' , 'bin' , 'python3' )

        cmd = "cd "+self._get_cloudsend_dir()+ " && "+waitmaestro_sh+" && sudo "+venv_python+" -u -m cloudsend.maestroclient " + the_command

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
                            return line # result is printed last...
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

    async def _cfg_add_objects(self,conf,coroutine,name):
        # complement self._config
        await coroutine(conf)
        # wait for maestro to be ready
        instanceid , ssh_conn , ftp_client = await self._wait_and_connect(self._maestro)
        # config_name
        config_name = 'config_add-' + cloudsendutils.generate_unique_id() + '.json'
        # deploy the new config to the maestro (every time) (including dependent files)
        translated_config = await self._deploy_config(ssh_conn,ftp_client,config_name)
        # triggers maestro::add_* : use string dump or config file name (either way)
        #await self._exec_maestro_command(name,config_name)
        await self._exec_maestro_command(name,json.dumps(translated_config))

    async def cfg_add_instances(self,conf):
        await self._cfg_add_objects(conf,super().cfg_add_instances,"cfg_add_instances")

    async def cfg_add_environments(self,conf):
        await self._cfg_add_objects(conf,super().cfg_add_environments,"cfg_add_environments")

    async def cfg_add_jobs(self,conf):
        await self._cfg_add_objects(conf,super().cfg_add_jobs,"cfg_add_jobs")

    async def cfg_add_config(self,conf):
        await self._cfg_add_objects(conf,super().cfg_add_config,"cfg_add_config")

    async def cfg_reset(self):
        # triggers maestro::reset
        await self._exec_maestro_command("cfg_reset") # use output - the deploy part will be skipped depending on option ...

    async def reset_instance(self,instance):
        self.debug(1,'RESETTING instance',instance.get_name())
        instanceid, ssh_conn , ftp_client = await self._wait_and_connect(instance)
        if ssh_conn is not None:
            await self.sftp_put_remote_file(ftp_client,'resetmaestro.sh')
            resetmaestro_sh = self._maestro.path_join( self._maestro.get_home_dir() , 'resetmaestro.sh' )
            commands = [
               { 'cmd' : 'chmod +x '+resetmaestro_sh+' && ' + resetmaestro_sh , 'out' : True }
            ]
            await self._run_ssh_commands(instance,ssh_conn,commands)
            #ftp_client.close()
            ssh_conn.close()
        self.debug(1,'RESETTING done')

    async def deploy(self):
        # triggers maestro::deploy
        await self._exec_maestro_command("deploy") # use output - the deploy part will be skipped depending on option ...

    async def run(self):
        # triggers maestro::run
        run_session_number_id = await self._exec_maestro_command("run")
        if run_session_number_id is not None:
            values = run_session_number_id.split(' ')            
            run_session_number = int(values[0])
            run_session_id     = values[1]
            self._current_session = self.get_run_session(run_session_number,run_session_id)
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
            args = [ int(job_state) , run_session.get_number() , run_session.get_id() ]
        else:
            args = [ int(job_state) ]
        # triggers maestro::wait
        await self._exec_maestro_command("wait",args)

    async def get_jobs_states(self,run_session=None):
        if run_session is not None:
            args = [ run_session.get_number() , run_session.get_id() ]
        else:
            args = None
        # triggers maestro::get_jobs_states
        await self._exec_maestro_command("get_states",args)

    async def print_jobs_summary(self,run_session=None,instance=None):
        if run_session is not None:
            args = [ run_session.get_number() , run_session.get_id() ]
        else:
            args = []
        if instance is not None:
            args.append(instance.get_name())

        # triggers maestro::print_jobs_summary
        await self._exec_maestro_command("print_summary",args)

    async def print_aborted_logs(self,run_session=None,instance=None):
        if run_session is not None:
            args = [ run_session.get_number() , run_session.get_id() ]
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
            maestro_dir = self._maestro.path_join( homedir , "cloudsend_tmp_fetch" )
            await self._exec_maestro_command("clear_results_dir",maestro_dir)


    async def fetch_results(self,out_dir=None,run_session=None,use_cached=True):

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
        maestro_dir      = self._maestro.path_join( homedir , "cloudsend_tmp_fetch" ) #+ randnum )
        maestro_tar_file = "maestro"+randnum+".tar"
        maestro_tar_path = self._maestro.path_join( homedir , maestro_tar_file )
        session_out_dir_remote = self._get_session_out_dir(maestro_dir,run_session,self._maestro)

        # fetch the results on the maestro
        args = [ maestro_dir , run_session.get_number() , run_session.get_id() ]
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
        # triggers maestro::print_aborted_logs
        try:
            await self._exec_maestro_command("finalize")
        # this will likely happen if auto_stop is one
        except asyncssh.misc.ConnectionLost as cle:
            pass

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

    # needed by CloudSendProvider::_wait_for_instance 
    def serialize_state(self):
        pass

    def get_run_session(self,session_number,session_id):
        return CloudSendRunSessionProxy( session_number , session_id )

    def get_instance(self,instance_name):
        return CloudSendInstanceProxy( instance_name )


