import hashlib , os , subprocess , json
import jcs , yaml
import uuid
import os
from cloudsend.core import K_COMPUTED

# keys used for hash computation
# Note: we include market options (SPOT ON|OFF e.g.) for the instance because it defines how the 'hardware' will run 
#       so it's considered part of the intrinsic characteristics of the machine
cs_instance_keys       = [ 'region'  , 'cloud_id' , 'img_id' , 'type' , 'cpus' , 'gpu' , 'disk_size' , 'disk_type' , 'eco' , 'max_bid' ] 
cs_environment_keys    = [ 'command' , 'env_pypi' , 'env_conda' , 'env_aptget' , 'env_julia' ]

def compute_instance_hash(instance_cfg):
    instance_config = { your_key: instance_cfg.get(your_key) for your_key in cs_instance_keys }
    instance_config_canon = jcs.canonicalize(instance_config)
    #print("INSTANCE CONFIG CANON",instance_config_canon)
    #instance_hash = str(hash(instance_config_canon))
    hash = hashlib.md5(instance_config_canon).hexdigest()
    return hash[0:12]


def add_pip_dependency_to_conda(env_dict):
    if not 'dependencies' in env_dict['env_conda']:
        env_dict['env_conda']['dependencies'] = [] 
    added = False
    pipIndex = -1 
    for i,dep in enumerate(env_dict['env_conda']['dependencies']):
        if dep == 'pip':
            env_dict['env_conda']['dependencies'][i] = { 'pip' : ['-r __REQUIREMENTS_TXT_LINK__'] }
            added = True
            pipIndex = i 
            break
        elif isinstance(dep,dict) and 'pip' in dep and isinstance(dep['pip'],list):
            pipIndex = i 
            doBreak = False
            for pipdep in dep['pip']:
                if 'requirements.txt' in pipdep:
                    doBreak = True
                    added   = True 
                    break
            if doBreak:
                break 
    # add the requirements dependecy (it was not found)
    if added is False:
        if pipIndex != -1:
            env_dict['env_conda']['dependencies'][pipIndex]['pip'].append('-r __REQUIREMENTS_TXT_LINK__')
        else:
            env_dict['env_conda']['dependencies'].append({'pip':['-r __REQUIREMENTS_TXT_LINK__']})

def update_requirements_path(env_dict,path):
    if isinstance(env_dict,dict):
        for k,v in env_dict.items():
            env_dict[k] = update_requirements_path(v,path)
        

    elif isinstance(env_dict,list):
        for i,v in enumerate(env_dict):
            env_dict[i] = update_requirements_path(v,path)
    
    elif isinstance(env_dict,str):
        if '__REQUIREMENTS_TXT_LINK__' in env_dict:
            env_dict = env_dict.replace('__REQUIREMENTS_TXT_LINK__',path)
        
    return env_dict

# returns a JSON object that represents lists as in requirements.txt as well as YAML format (can be parsed by YAML module)
# this object will be serialized and sent to remote host
# this is also used to compute the hash for the environment
def compute_environment_object(env_config):

    # the configuration is already computed (usually by the LightProvider)
    # we just have to return this env object for deployment
    if env_config.get(K_COMPUTED) == True:
        return env_config

    environment_obj = {
        'command'    : None ,
        'env_aptget' : None , 
        'env_conda'  : None , 
        'env_pypi'   : None , 
        'env_julia'  : None ,
        'name'       : env_config.get('name')
    }
    
    if env_config.get('command'):

        env_command = env_config['command']

        if isinstance(env_command,str) and os.path.isfile(env_command):

            with open(env_command, "r") as bash_file:
                try:
                    environment_obj['command'] = bash_file.read()
                except Exception as exc:
                    print(exc)
            
    # conda+pip: https://stackoverflow.com/questions/35245401/combining-conda-environment-yml-with-pip-requirements-txt
    
    if env_config.get('env_aptget'):

        env_apt_get = env_config['env_aptget']

        if isinstance(env_apt_get,list):

            # set dependencies as this
            env_apt_get = list(map(str.strip,env_apt_get)) # strip the strings
            environment_obj['env_aptget'] = env_apt_get


    if env_config.get('env_conda'):

        env_conda = env_config['env_conda']

        if isinstance(env_conda,list):
        
            # sort the array and set dependencies as this
            env_conda = list(map(str.strip,env_conda)) # strip the strings
            environment_obj['env_conda'] = dict()
            environment_obj['env_conda']['dependencies'] = env_conda
            conda_channels = env_config.get('env_conda_channels')
            if not conda_channels:
                conda_channels = [ 'conda-forge' , 'defaults' ]
            environment_obj['env_conda']['channels'] = conda_channels
        
        elif isinstance(env_conda,str) and os.path.isfile(env_conda):

            with open(env_conda, "r") as ymlData:
                try:
                    ymlConda = yaml.load(ymlData,Loader=yaml.FullLoader)
                    environment_obj['env_conda'] = ymlConda
                except yaml.YAMLError as exc:
                    print(exc)
        
        elif isinstance(env_conda,str) and os.path.isdir(env_conda):

            cmd    = ['source activate "'+env_conda+'" && conda env export']
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE,shell=True)
                try:
                    ymlConda = yaml.load(result.stdout,Loader=yaml.FullLoader)
                    environment_obj['env_conda'] = ymlConda
                except yaml.YAMLError as exc:
                    print(exc)
            except subprocess.CalledProcessError as pex:
                print(pex)
        
        else:
            print("\033[93menv_conda is specified but the file or directory doesn't exist\033[0m")


    if env_config.get('env_pypi'):

        env_pypi = env_config['env_pypi']

        #make sure we have the extra ref in the conda env, if conda env exists ...
        if environment_obj['env_conda'] is not None:
            add_pip_dependency_to_conda( environment_obj )

        if isinstance(env_pypi,list):

            # set dependencies as this
            env_pypi = list(map(str.strip,env_pypi)) # strip the strings
            environment_obj['env_pypi'] = env_pypi

        elif isinstance(env_pypi,str) and os.path.isfile(env_pypi):

            with open(env_pypi, "r") as txtFile:
                pipDeps = txtFile.read().split('\n')
                environment_obj['env_pypi'] = pipDeps
            
        elif isinstance(env_pypi,str) and os.path.isdir(env_pypi):

            #cmd    = "source " + os.path.realpath(env_pypi) + os.path.sep + 'bin' + os.path.sep + 'activate && pip freeze'
            cmd = [
                os.path.realpath(env_pypi) + os.path.sep + 'bin' + os.path.sep + 'pip' ,
                'freeze'
            ]
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE)
                pipDeps = result.stdout.decode("utf-8").strip().split('\n')
                environment_obj['env_pypi'] = pipDeps
            except subprocess.CalledProcessError as pex:
                print(pex)

        else:
            print("\033[93menv_pypi is specified but the file or directory doesn't exist\033[0m")

    if env_config.get('env_julia'):

        env_julia = env_config['env_julia']

        if isinstance(env_julia,str):

            env_julia = [ env_julia ]

        # set dependencies as this
        env_apt_get = list(map(str.strip,env_julia)) # strip the strings
        environment_obj['env_julia'] = env_julia                


    return environment_obj      

def compute_environment_hash(env_dict):
    onv_obj_canon  = yaml.load(yaml.dump(env_dict, sort_keys=True),Loader=yaml.FullLoader)
    env_json_canon = jcs.canonicalize(onv_obj_canon)
    hash = hashlib.md5(env_json_canon).hexdigest()
    return hash[0:12]

def compute_job_hash(job_config):
    string_to_hash = ''
    if job_config.get('run_script'):
        script_args    = job_config['run_script'].split()
        scriptfile     = os.path.realpath(script_args[0])
        string_to_hash = 'script:' + scriptfile
    elif job_config.get('run_command'):
        # lets not do anything to commands ... its less known what can be in there ...
        string_to_hash = 'command:' + job_config['run_command']
    else:
        string_to_hash = 'unknown'

    # also add the upload files as part of the hash
    # this could mean the script will run with different multi inputs ... 
    if job_config.get('upload_files'):
        files = job_config['upload_files']
        if isinstance(files,str):
            files = [ files ]
        realfiles = []
        for f in sorted(files):
            realfiles.append( os.path.realpath(f) )
        string_to_hash = string_to_hash + ":" + ",".join(realfiles)

    if job_config.get('input_file'):
        inputpath = os.path.realpath(job_config.get('input_file'))
        string_to_hash = string_to_hash + ":" + inputpath

    # also add the input file which should be pointing to a specific file 
    # so if this is different for some reason (but with all the same python file, args, and upload files)
    # this means that we should probably run 

    # NO! 
    # this will be differentiated with the UID at run time
    # to mutualize more the upload files + script file ...
    # if 'input_files' in job_config and job_config['input_files'] is not None:
    #    string_to_hash = string_to_hash + ':' + job_config['input_files']

    hash = hashlib.md5(string_to_hash.encode()).hexdigest()
    return hash[0:12]

def generate_unique_id():
    return str(uuid.uuid4())

def compute_job_command(instance,script_dir,job_config):
    script_command = ''
    if 'run_script' in job_config and job_config['run_script'] is not None:
        script_args = job_config['run_script'].split()
        filename = os.path.basename(script_args[0])
        file_ext = os.path.splitext(filename)[1]
        script_args.pop(0)
        if file_ext.lower() == '.py':
            # use -u if i you want to skip stdout buffering (used by tail function)
            script_command = "python3 " + instance.path_join( script_dir , filename ) + " " + " ".join(script_args)
        elif file_ext.lower() == '.jl':
            script_command = "julia " + instance.path_join( script_dir , filename ) + " " + " ".join(script_args)
        else:
            script_command = "echo 'SCRIPT NOT HANDLED'"
    elif 'run_command' in job_config and job_config['run_command']:
        script_command = job_config['run_command']
    else:
        script_command = "echo 'NO SCRIPT DEFINED'" 

    return script_command 

def resolve_paths(instance,the_file,ref_file,remote_ref_dir,mutualize=True):

    # if we have a script
    # let's make sure we upload the right directory structure so we dont have to change the script
    if ref_file:
        ref_args        = ref_file.split()
        ref_abs_path    = os.path.abspath(ref_args[0])
        ref_abs_dir     = os.path.dirname(ref_abs_path)
        if os.path.isabs(the_file):
            local_abs_path   = the_file
        else:
            local_abs_path   = os.path.join(ref_abs_dir,the_file)
        file_abs_dir    = os.path.dirname(local_abs_path)
    else:
        ref_abs_path    = os.path.abspath(os.getcwd())
        ref_abs_dir     = ref_abs_path #os.path.dirname(ref_abs_path)
        if os.path.isabs(the_file):
            local_abs_path   = the_file
        else:
            local_abs_path   = os.path.join(ref_abs_dir,the_file)
        file_abs_dir    = os.path.dirname(local_abs_path)
    
    # this is a subdir: we have to respect the structure
    if file_abs_dir.startswith(ref_abs_dir):
        rel_path = local_abs_path.replace(ref_abs_dir,"")
        if rel_path.startswith(os.sep):
            rel_path = rel_path[1:]
        external = False
    # this is not a subdir ! we gotta create a virtual subdir that 
    else:
        #rel_path = local_abs_path.replace(os.sep,'_')
        # we gotta have to handle Windows situation here and transform the drive as a path bite
        rel_path = local_abs_path # LETS USE THE ABS PATH as a REL PATH !
        if rel_path.startswith(os.sep):
            rel_path = rel_path[1:]
        drive , path = os.path.splitdrive(rel_path)
        if drive:
            rel_path = os.path.join( drive.replace(':','') , path ) 
            if rel_path.startswith('//'): # //network_drive
                rel_path = rel_path[2:]
            elif rel_path.startswith(os.sep): # /absolute
                rel_path = rel_path[1:]
        external = True

    # use the first case if you want to leave stuff in the job's directory
    if not mutualize:
        remote_abs_path = instance.path_join(remote_ref_dir,rel_path)
        remote_rel_path = rel_path
    # use the second case if you want to mutualize uploads
    else:
        remote_abs_path = local_abs_path # always use full path in one target directory
        if remote_abs_path.startswith(os.sep):
            remote_abs_path = remote_abs_path[1:] # make relative
        remote_rel_path = remote_abs_path
        remote_abs_path = instance.path_join(remote_ref_dir,remote_abs_path)

    # local_abs_path  = the local file path
    # rel_path        = the relative path (from the job directory aka script dir)
    # remote_abs_path = the absolute remote file path
    # remote_rel_path = the relative remote path (from remote_ref_dir)
    # external        = is the file external to the script directory structure
    return local_abs_path , rel_path, remote_abs_path , remote_rel_path , external

 



