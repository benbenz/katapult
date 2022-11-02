config = {
    'project'      : 'test' ,                     # this will be concatenated with the hash (if not None) 
    'dev'          : False ,                      # When True, this will ensure the same instance and dev environement are being used (while working on building up the project) 
    'debug'        : 1 ,                          # debug level (0...3)

    # "instance" section
    'vpc_id'       : 'vpc-0babc28485f6730bc' ,    # can be None, or even wrong/non-existing - then the default one is used
    'region'       : 'eu-west-3' ,                # has to be valid
    'img_id'       : 'ami-077fd75cd229c811b' ,    # OS image: has to be valid and available for the profile (user/region)
    'img_username' : 'ubuntu' ,                   # the SSH user for the image
    'min_cpu'      : None ,                       # number of min CPUs (not used yet)
    'max_cpu'      : None ,                       # number of max CPUs (not used yet)
    'max_bid'      : None ,                       # max bid ($) (not used yet)
    'size'         : None ,                       # size (ECO = SPOT , SMALL , MEDIUM , LARGE) (not used yet)

    # "environment" section
    # env_conda + env_pypi   >> mamba is used to setup the env (pip dependencies included)
    # env_conda (only)       >> mamba is used to setup the env
    # env_pypi  (only)       >> venv + pip is used to setup the env 
    'env_aptget'   : [ "openssh-client"] ,        # None, an array of librarires/binaries for apt-get
    'env_conda'    : "example/environment.yml",   # None, an array of libraries, a path to environment.yml  file, or a path to the root of a conda environment
    'env_pypi'     : "example/requirements.txt" , # None, an array of libraries, a path to requirements.txt file, or a path to the root of a venv environment 

    # "script"/"command" section
    'run_script'   : 'example/run_remote.py' ,    # the script to run (Python (.py) or Julia (.jl) for now)
    'run_command'  : None ,                       # the command to run (either script_file or command will be used)
    'upload_files' : [ "example/uploaded.txt"] ,  # any file to upload (array or string) - will be put in the same (home) directory
}