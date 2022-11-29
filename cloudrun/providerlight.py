
from abc import ABC , abstractmethod
from cloudrun.provider import CloudRunProvider , line_buffered
from cloudrun.core import *
import copy , io
from zipfile import ZipFile
import os , fnmatch
import re
from os.path import basename
import pkg_resources

####################################
# Client handling MAESTRO instance #
####################################

class CloudRunLightProvider(CloudRunProvider,ABC):

    def __init__(self,conf):
        CloudRunProvider.__init__(self,conf)
        self._load()

        self.ssh_client = None
        self.ftp_client = None
    
    def _load(self):
        self._maestro = None
        if self._config.get('maestro')=='remote':
            if not self._config.get('instances') or len(self._config.get('instances'))==0:
                self.debug(2,"There are no instances to watch - skipping maestro creation")
                return
            else:
                img_id   = self._config.get('instances')[0].get('img_id')
                img_user = self._config.get('instances')[0].get('img_username')
                maestro_cfg = { 
                    'maestro'      : True ,
                    'img_id'       : img_id ,
                    'img_username' : img_user ,                 
                    'type'         : 't2.nano' ,  
                    'dev'          : self._config.get('dev',False) ,
                    'project'      : self._config.get('project',None)
                }
                self._maestro = CloudRunInstance(maestro_cfg,None)

    def _deploy_maestro(self):
        # deploy the maestro ...
        if self._maestro is None:
            self.debug(2,"no MAESTRO object to deploy")
            return

        # wait for maestro to be ready
        instanceid , ssh_client , ftp_client = self._wait_and_connect(self._maestro)

        re_init  = self._test_reupload(self._maestro,"$HOME/cloudrun/ready", ssh_client)

        if re_init:
            # remove the file
            self._exec_command(ssh_client,'rm -f $HOME/cloudrun/ready')
            # make cloudrun dir
            self._exec_command(ssh_client,'mkdir -p $HOME/cloudrun') 
            # grant its admin rights (we need to be (stopped or) running to be able to do that)
            self.grant_admin_rights(self._maestro)
            # deploy CloudRun on the maestro
            self._deploy_cloudrun(ssh_client,ftp_client)
            # mark as ready
            self._exec_command(ssh_client,'if [ -f $HOME/cloudrun/.venv/maestro/bin/activate ]; then echo "" > $HOME/cloudrun/ready ; fi')

        # deploy the config to the maestro
        self._deploy_config(ssh_client,ftp_client)

        # let's redeploy the code every time for now ... (if not already done in re_init)
        if not re_init:
            self._deploy_cloudrun_files(ssh_client,ftp_client)

        # start the server (if not already started)
        self._run_server(ssh_client)

        ftp_client.close()
        ssh_client.close()

        self.debug(1,"MAESTRO is READY")


    def _deploy_cloudrun_files(self,ssh_client,ftp_client):
        ftp_client.chdir(self._get_cloudrun_dir())
        ftp_client.putfo(self._create_cloudrun_zip(),'cloudrun.zip')
        commands = [
            { 'cmd' : 'cd $HOME/cloudrun && unzip -o cloudrun.zip && rm cloudrun.zip' , 'out' : True } ,
        ]
        self._run_ssh_commands(ssh_client,commands) 
        
        filesOfDirectory = os.listdir('.')
        pattern = "cloudrun-*.pem"
        for file in filesOfDirectory:
            if fnmatch.fnmatch(file, pattern):
                ftp_client.put(os.path.abspath(file),os.path.basename(file))

        commands = [
            { 'cmd' : 'chmod +x $HOME/cloudrun/cloudrun/resources/remote_files/*.sh' , 'out' : True } ,
        ]
        self._run_ssh_commands(ssh_client,commands) 


    def _deploy_cloudrun(self,ssh_client,ftp_client):

        # upload cloudrun files
        self._deploy_cloudrun_files(ssh_client,ftp_client)
        
        # unzip cloudrun files, install and run
        commands = [
            { 'cmd' : '$HOME/cloudrun/cloudrun/resources/remote_files/maestroenv.sh' , 'out' : True } ,
#            { 'cmd' : 'cd $HOME/cloudrun && curl -sSL https://install.python-poetry.org | python3 -' , 'out' : True } ,
#            { 'cmd' : 'cd $HOME/cloudrun && $HOME/.local/bin/poetry install' , 'out' : True } ,
#            { 'cmd' : 'cd $HOME/cloudrun && $HOME/.local/bin/poetry run demo' , 'out' : True }
        ]
        self._run_ssh_commands(ssh_client,commands)

    def _run_server(self,ssh_client):
        # run the server
        commands = [
            { 'cmd' : '$HOME/cloudrun/cloudrun/resources/remote_files/startmaestro.sh' , 'out' : False , 'output' : 'server.log' }
        ]
        self._run_ssh_commands(ssh_client,commands)

    def _deploy_config(self,ssh_client,ftp_client):
        config = self._translate_config_for_maestro()
        # serialize the config and send it to the maestro
        ftp_client.chdir(self._get_cloudrun_dir())
        ftp_client.putfo(io.StringIO(json.dumps(config)),'config.json')

    def _translate_config_for_maestro(self):
        config = copy.deepcopy(self._config)

        config['maestro'] = 'local' # the config is for maestro, which needs to run local

        config['region'] = self.get_user_region()

        for i , inst_cfg in enumerate(config.get('instances')):
            # we need to freeze the region within each instance config ...
            if not config['instances'][i].get('region'):
                config['instances'][i]['region'] = self.get_user_region()

        for i , env_cfg in enumerate(config.get('environments')):
            # Note: we are using a simple CloudRunEnvironment here 
            # we're not deploying at this stage
            # but this will help use re-use all the business logic in cloudrunutils / env
            # in order to standardize the environment and create an inline version 
            # through the CloudRunEnvironment::json() method
            env = CloudRunEnvironment(self._config.get('project'),env_cfg)
            config['environments'][i] = env.get_env_obj()
            config['environments'][i]['_computed_'] = True

        self.debug(2,config)

        return config


    def _get_home_dir(self):
        return '/home/' + self._maestro.get_config('img_username') 

    def _get_cloudrun_dir(self):
        return self._get_home_dir() + '/cloudrun'

    def _zip_package(self,package_name,src,dest,zipObj):
        dest = (dest + "/" + os.path.basename(src)).rstrip("/")
        if pkg_resources.resource_isdir(package_name, src):
            #if not os.path.isdir(dest):
            #    os.makedirs(dest)
            for res in pkg_resources.resource_listdir(package_name, src):
                self.debug(2,'scanning package resource',res)
                self._zip_package(package_name,src + "/" + res, dest, zipObj)
        else:
            if os.path.splitext(src)[1] not in [".pyc"]:
                #copy_resource_file(src, dest) 
                data_str = pkg_resources.resource_string(package_name, src)
                self.debug(2,"Writing",src)
                zipObj.writestr(dest,data_str)

    def _create_cloudrun_zip(self):
        zip_buffer = io.BytesIO()
        # create a ZipFile object
        with ZipFile(zip_buffer, 'a') as zipObj:    
            for otherfilepath in ['./pyproject.toml' , './requirements.txt' ]:
                with open(otherfilepath,'r') as thefile:
                    data = thefile.read()
                    zipObj.writestr(otherfilepath,data)
            # write the resources / package
            self._zip_package("cloudrun",".","cloudrun",zipObj)

        self.debug(2,"ZIP BUFFER SIZE =",zip_buffer.getbuffer().nbytes)

        # very important...
        zip_buffer.seek(0)

        # with open('C:/1.zip', 'wb') as f:
        #     f.write(zip_buffer.getvalue())            
        return zip_buffer

    def _exec_maestro_command(self,maestro_command):
        if self.ssh_client is None:
            instanceid , self.ssh_client , self.ftp_client = self._wait_and_connect(self._maestro)

        cmd = "cd $HOME/cloudrun && python3 -m cloudrun.maestroclient " + maestro_command
        stdin , stdout , stderr = self._exec_command(self.ssh_client,cmd)
        for l in line_buffered(stdout):
            if not l:
                break
            self.debug(1,l,end='')


    def start(self):
        # this will block for some time the first time...
        self._instances_states = dict()        
        self._start_and_update_instance(self._maestro)
        self._deploy_maestro() # deploy the maestro now !

        # now really start 
        self._exec_maestro_command("start")

    def assign_jobs_to_instances(self):
        # should trigger maestro::assign_jobs_to_instances
        self._exec_maestro_command("allocate")

    def deploy(self):
        # should trigger maestro::deploy
        self._exec_maestro_command("deploy")

    def run_jobs(self):
        # should trigger maestro::run_jobs
        self._exec_maestro_command("run_jobs")

    def wait_for_jobs_state(self,job_state,processes=None):
        # should trigger maestro::
        self._exec_maestro_command("wait")

    def get_jobs_states(self,processes=None):
        self._exec_maestro_command("get_states")

    def print_jobs_summary(self,instance=None):
        self._exec_maestro_command("print_summary")

    def print_aborted_logs(self,instance=None):
        self._exec_maestro_command("print_aborted")


    @abstractmethod
    def get_user_region(self):
        pass

    @abstractmethod
    def find_instance(self,config):
        pass

    @abstractmethod
    def update_instance_info(self,instance):
        pass

    @abstractmethod
    def grant_admin_rights(self,instance):
        pass

    @abstractmethod
    def create_instance_objects(self,config):
        pass

    # needed by CloudRunProvider::_wait_for_instance 
    def serialize_state(self):
        pass


