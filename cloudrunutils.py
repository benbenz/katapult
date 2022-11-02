import hashlib , os , subprocess , json
import jcs , yaml
from os import path


cr_instance_keys       = [ 'vpc_id' , 'region'  , 'img_id' , 'min_cpu' , 'max_cpu' , 'size' ] 
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
            env_obj['env_conda']['dependencies'][i] = { 'pip' : ['-r file:/home/ubuntu/requirements.txt'] }
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
            env_obj['env_conda']['dependencies'][pipIndex]['pip'].append('-r file:/home/ubuntu/requirements.txt')
        else:
            env_obj['env_conda']['dependencies'].append({'pip':['-r file:/home/ubuntu/requirements.txt']})


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
            print("env_conda is specified but the file or directory doesnt exists")


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
            print("env_pypi is specified but the file or directory doesnt exists")


    return environment_obj      

def compute_environment_hash(env_obj):
    onv_obj_canon  = yaml.load(yaml.dump(env_obj, sort_keys=True),Loader=yaml.FullLoader)
    env_json_canon = jcs.canonicalize(onv_obj_canon)
    hash = hashlib.md5(env_json_canon).hexdigest()
    return hash[0:12]