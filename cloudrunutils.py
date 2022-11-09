import hashlib , os , subprocess , json
import jcs , yaml
import uuid
from os import path

# keys used for hash computation
# Note: we include market options (SPOT ON/OFF e.g.) for the instance because it defines how the 'hardware' will run 
#       so it's considered part of the intrinsic characteristics of the machine
cr_instance_keys       = [ 'region'  , 'cloud_id' , 'img_id' , 'size' , 'cpus' , 'gpu' , 'disk_size' , 'disk_type' , 'eco' , 'max_bid' ] 
cr_environment_keys    = [ 'env_pypi' , 'env_conda' , 'env_apt-get' ]

def compute_instance_hash(config):
    instance_config = { your_key: config[your_key] for your_key in cr_instance_keys }
    instance_config_canon = jcs.canonicalize(instance_config)
    #instance_hash = str(hash(instance_config_canon))
    hash = hashlib.md5(instance_config_canon).hexdigest()
    return hash[0:12]


def add_pip_dependency_to_conda(env_obj):
    if not 'dependencies' in env_obj['env_conda']:
        env_obj['env_conda']['dependencies'] = [] 
    added = False
    pipIndex = -1 
    for i,dep in enumerate(env_obj['env_conda']['dependencies']):
        if dep == 'pip':
            env_obj['env_conda']['dependencies'][i] = { 'pip' : ['-r __REQUIREMENTS_TXT_LINK__'] }
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
            env_obj['env_conda']['dependencies'][pipIndex]['pip'].append('-r __REQUIREMENTS_TXT_LINK__')
        else:
            env_obj['env_conda']['dependencies'].append({'pip':['-r __REQUIREMENTS_TXT_LINK__']})

def update_requirements_path(envobj,path):
    if isinstance(envobj,dict):
        for k,v in envobj.items():
            envobj[k] = update_requirements_path(v,path)
        

    elif isinstance(envobj,list):
        for i,v in enumerate(envobj):
            envobj[i] = update_requirements_path(v,path)
    
    elif isinstance(envobj,str):
        if '__REQUIREMENTS_TXT_LINK__' in envobj:
            envobj = envobj.replace('__REQUIREMENTS_TXT_LINK__',path+'/requirements.txt')
        
    return envobj

# returns a JSON object that represents lists as in requirements.txt as well as YAML format (can be parsed by YAML module)
# this object will be serialized and sent to remote host
# this is also used to compute the hash for the environment
def compute_environment_object(config):

    environment_obj = {
        'env_aptget' : None , 
        'env_conda'  : None , 
        'env_pypi'   : None , 
    }
    
    # conda+pip: https://stackoverflow.com/questions/35245401/combining-conda-environment-yml-with-pip-requirements-txt
    
    if 'env_aptget' in config and config['env_aptget'] is not None:

        env_apt_get = config['env_aptget']

        if isinstance(env_apt_get,list):

            # set dependencies as this
            env_apt_get = list(map(str.strip,env_apt_get)) # strip the strings
            environment_obj['env_aptget'] = env_apt_get


    if 'env_conda' in config and config['env_conda'] is not None:

        env_conda = config['env_conda']

        if isinstance(env_conda,list):
        
            # sort the array and set dependencies as this
            env_conda = list(map(str.strip,env_conda)) # strip the strings
            environment_obj['env_conda']['dependencies'] = env_conda
        
        elif isinstance(env_conda,str) and path.isfile(env_conda):

            with open(env_conda, "r") as ymlData:
                try:
                    ymlConda = yaml.load(ymlData,Loader=yaml.FullLoader)
                    environment_obj['env_conda'] = ymlConda
                except yaml.YAMLError as exc:
                    print(exc)
        
        elif isinstance(env_conda,str) and path.isdir(env_conda):

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


    if 'env_pypi' in config and config['env_pypi'] is not None:

        env_pypi = config['env_pypi']

        #make sure we have the extra ref in the conda env, if conda env exists ...
        if environment_obj['env_conda'] is not None:
            add_pip_dependency_to_conda( environment_obj )

        if isinstance(env_pypi,list):

            # set dependencies as this
            env_pypi = list(map(str.strip,env_pypi)) # strip the strings
            environment_obj['env_pypi'] = env_pypi

        elif isinstance(env_pypi,str) and path.isfile(env_pypi):

            with open(env_pypi, "r") as txtFile:
                pipDeps = txtFile.read().split('\n')
                environment_obj['env_pypi'] = pipDeps
            
        elif isinstance(env_pypi,str) and path.isdir(env_pypi):

            #cmd    = "source " + path.realpath(env_pypi) + path.sep + 'bin' + path.sep + 'activate && pip freeze'
            cmd = [
                path.realpath(env_pypi) + path.sep + 'bin' + path.sep + 'pip' ,
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


    return environment_obj      

def compute_environment_hash(env_obj):
    onv_obj_canon  = yaml.load(yaml.dump(env_obj, sort_keys=True),Loader=yaml.FullLoader)
    env_json_canon = jcs.canonicalize(onv_obj_canon)
    hash = hashlib.md5(env_json_canon).hexdigest()
    return hash[0:12]

def compute_job_hash(config):
    string_to_hash = ''
    if config.get('run_script'):
        script_args    = config['run_script'].split()
        scriptfile     = path.realpath(script_args[0])
        string_to_hash = 'script:' + scriptfile
    elif config.get('run_command'):
        # lets not do anything to commands ... its less known what can be in there ...
        string_to_hash = 'command:' + config['run_command']
    else:
        string_to_hash = 'unknown'

    # also add the upload files as part of the hash
    # this could mean the script will run with different multi inputs ... 
    if config.get('upload_files'):
        files = config['upload_files']
        if isinstance(files,str):
            files = [ files ]
        realfiles = []
        for f in sorted(files):
            realfiles.append( path.realpath(f) )
        string_to_hash = string_to_hash + ":" + ",".join(realfiles)

    if config.get('input_file'):
        inputpath = path.realpath(config.get('input_file'))
        string_to_hash = string_to_hash + ":" + inputpath

    # also add the input file which should be pointing to a specific file 
    # so if this is different for some reason (but with all the same python file, args, and upload files)
    # this means that we should probably run 

    # NO! 
    # this will be differentiated with the UID at run time
    # to mutualize more the upload files + script file ...
    # if 'input_files' in config and config['input_files'] is not None:
    #    string_to_hash = string_to_hash + ':' + config['input_files']

    hash = hashlib.md5(string_to_hash.encode()).hexdigest()
    return hash[0:12]

def generate_unique_filename():
    return str(uuid.uuid4())

def compute_job_command(script_dir,config):
    script_command = ''
    if 'run_script' in config and config['run_script'] is not None:
        script_args = config['run_script'].split()
        filename = os.path.basename(script_args[0])
        file_ext = os.path.splitext(filename)[1]
        script_args.pop(0)
        if file_ext.lower() == '.py':
            # -u is to skip stdout buffering (used by tail function)
            script_command = "python3 -u " + script_dir + '/' + filename + " " + " ".join(script_args)
        elif file_ext.lower() == '.jl':
            script_command = "julia " + script_dir + '/' + filename + " " + " ".join(script_args)
        else:
            script_command = "echo 'SCRIPT NOT HANDLED'"
    elif 'run_command' in config and config['run_command']:
        script_command = config['run_command'] #script_dir + '/' + config['run_command']
    else:
        script_command = "echo 'NO SCRIPT DEFINED'" 

    return script_command 

