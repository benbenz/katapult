config = {

    ################################################################################
    # GLOBALS
    ################################################################################

    'project'      : 'test' ,                             # this will be concatenated with the instance hashes (if not None) 
    'profile'      : None ,                               # if you want to use a specific profile (user/region), specify its name here
    'dev'          : False ,                              # When True, this will ensure the same instance and dev environement are being used (while working on building up the project) 
    'debug'        : 1 ,                                  # debug level (0...3)
    'maestro'      : 'local' ,                            # where the 'maestro' resides: local' | 'remote' (nano instance) | 'lambda'
    'auto_stop'    : True ,                               # will automatically stop the instances and the maestro, once the jobs are done
    'provider'     : 'aws' ,                              # the provider name ('aws' | 'azure' | ...)
    'job_assign'   : None ,                               # algorithm used for job assignation / task scheduling ('random' | 'multi_knapsack')
    'recover'      : True ,                               # if True, Katapult will always save the state and try to recover this state on the next execution
    'print_deploy' : False ,                              # if True, this will cause the deploy stage to print more (and lock)
    'mutualize_uploads' : True ,                          # adjusts the directory structure of the uploads ... (False = per job or True = global/mutualized)

    ################################################################################
    # INSTANCES / HARDWARE
    ################################################################################

    'instances' : [
        { 
            'region'       : None ,                       # can be None or has to be valid. Overrides AWS user region configuration.
            'cloud_id'     : None ,                       # can be None, or even wrong/non-existing - then the default one is used
            'img_id'       : 'ami-077fd75cd229c811b' ,    # OS image: can be None or has to be valid and available for the profile (user/region)
            'img_username' : 'ubuntu' ,                   # the SSH user for the image (can be None if image is None)
            'type'         : 't2.micro' ,                 # proprietary size spec (has to be valid)
            'cpus'         : None ,                       # number of CPU cores
            'gpu'          : None ,                       # the proprietary type of the GPU 
            'disk_size'    : None ,                       # the disk size of this instance type (in GB)
            'disk_type'    : None ,                       # the proprietary disk type of this instance type: 'standard', 'io1', 'io2', 'st1', etc
            'eco'          : True ,                       # eco == True >> SPOT e.g.
            'eco_life'     : None ,                       # lifecycle of the machine in ECO mode (datetime.timedelta object) (can be None with eco = True)
            'max_bid'      : None ,                       # max bid ($/hour) (can be None with eco = True)
            'number'       : 1 ,                          # multiplicity: the number of instance(s) to create
            'explode'      : True                         # multiplicity: can this instance type be distributed accross multiple instances, to split CPUs
        }

    ] ,

    ################################################################################
    # ENVIRONMENTS / SOFTWARE
    ################################################################################

    'environments' : [
        {
            'name'         : None ,                       # name of the environment - should be unique if not 'None'. 'None' only when len(environments)==1

            # env_conda + env_pypi  : mamba is used to setup the env (pip dependencies included)
            # env_conda (only)      : mamba is used to setup the env
            # env_pypi  (only)      : venv + pip is used to setup the env 

            'command'      : 'examples/install_julia.sh' ,      # None, or a string: path to a bash file to execute when deploying
            'env_aptget'   : [ "openssh-client"] ,        # None, an array of librarires/binaries for apt-get
            'env_conda'    : "examples/environment.yml",   # None, an array of libraries, a path to environment.yml  file, or a path to the root of a conda environment
            'env_conda_channels' : None ,                 # None, an array of channels. If None, defaults and conda-forge will be used
            'env_pypi'     : "examples/requirements.txt" , # None, an array of libraries, a path to requirements.txt file, or a path to the root of a venv environment 
            'env_julia'    : ["Wavelets"] ,                       # None, a string or an array of Julia packages to install (requires julia)
        }
    ] ,

    ################################################################################
    # JOBS / SCRIPTS
    ################################################################################

    'jobs' : [
        {
            'env_name'     : None ,                       # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                       # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'examples/run_remote.py 1 10',# the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                       # the command to run
            'upload_files' : [ "uploaded.txt"] ,  # any file to upload (array or string) - will be put in the same directory
            'input_files'   : 'input.dat' ,                # the input file name (used by the script)
            'output_files'  : 'output.dat' ,               # the output file name (used by the script)
            'repeat'       : 2                            # the number of times this job can be repeated
        } ,
        {
            'env_name'     : None ,                       # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                       # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'examples/run_remote.py 2 12',# the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                       # the command to run
            'upload_files' : [ "uploaded.txt"] ,  # any file to upload (array or string) - will be put in the same directory
            'input_files'   : 'input.dat' ,                # the input file name (used by the script)
            'output_files'  : 'output.dat' ,               # the output file name (used by the script)
        }
    ]
}