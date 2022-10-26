import hashlib 
import jcs , yaml

cr_instance_keys       = [ 'vpc_id' , 'region'  , 'ami_id' , 'min_cpu' , 'max_cpu' , 'size' ] 
cr_environment_keys    = [ 'env_pypi' , 'env_conda' , 'env_apt-get' ]

def compute_instance_hash(config):
    instance_config = { your_key: config[your_key] for your_key in cr_instance_keys }
    instance_config_canon = jcs.canonicalize(instance_config)
    #instance_hash = str(hash(instance_config_canon))
    return hashlib.md5(instance_config_canon).hexdigest()

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
    
    if 'env_apt-get' in config and config['env_apt-get'] is not None:

        env_apt_get = config['env_apt-get']

        if isinstance(env_apt_get,list):

            # sort the array and set dependencies as this
            environment_obj['env_apt-get'] = env_apt_get.sort()


    if 'env_conda' in config and config['env_conda'] is not None:

        env_conda = config['env_conda']

        if isinstance(env_conda,list):
        
            # sort the array and set dependencies as this
            environment_obj['env_conda']['dependencies'] = env_conda.sort()
        
        elif 

    if 'env_pypi' in config and config['env_pypi'] is not None:

        env_pypi = config['env_pypi']

        #TODO: make sure we have the extra ref in the conda env, if conda env exists ...

        if isinstance(env_pypi,list):

            # sort the array and set dependencies as this
            environment_obj['env_conda']['dependencies'] = env_conda.sort()



    # finally, update the name in the conda_obj 

    # resort all keys etc
    environment_obj = yaml.load(yaml.dump(environment_obj, sort_keys=False))

    # this is the canonical version at this point ...


    