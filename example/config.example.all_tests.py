config = {

    ################################################################################
    # GLOBALS
    ################################################################################

    'project'      : 'test' ,                             # this will be concatenated with the instance (if not None) 
    #'profile'      : None,
    'profile'      : 'cloudsend_benben', 
    #'profile'      : 'cloudsend_benbenz_tlamadon' ,   
    'dev'          : False ,                              # When True, this will ensure the same instance and dev environement are being used (while working on building up the project) 
    'debug'        : 1 ,                                  # debug level (0...3)
    'maestro'      : 'local' ,                           # where the 'maestro' resides: local' | 'remote' (nano instance) | 'lambda'
    'auto_stop'    : True ,
    'provider'     : 'aws' ,                              # the provider name ('aws' | 'azure' | ...)
    'job_assign'   : 'multi_knapsack' ,
    'recover'      : False ,
    'print_deploy' : False ,                              # if True, this will cause the deploy stage to print more (and lock)
    'mutualize_uploads' : True ,                          # adjusts the directory structure of the uploads ... (per job or global)

    ################################################################################
    # INSTANCES / HARDWARE
    ################################################################################

    'instances' : [
        { 
            'region'       : None ,                       # can be None or has to be valid. Overrides AWS user region configuration.
            'cloud_id'     : None ,                       # can be None, or even wrong/non-existing - then the default one is used
            #'img_id'       : 'ami-0c882f311bc3634fe' ,
            #'img_id'       : 'ami-077fd75cd229c811b' ,    # OS image: has to be valid and available for the profile (user/region)
            #'img_username' : 'ubuntu' ,                   # the SSH user for the image
            'type'         : 't3.micro' ,                 # proprietary type spec (has to be valid)
            'cpus'         : None ,                       # number of CPU cores
            'gpu'          : None ,                       # the proprietary type of the GPU 
            'disk_size'    : None ,                       # the disk size of this instance type (in GB)
            'disk_type'    : None ,                       # the proprietary disk type of this instance type: 'standard', 'io1', 'io2', 'st1', etc
            'eco'          : False ,                       # eco == True >> SPOT e.g.
            'eco_life'     : None ,                       # lifecycle of the machine in ECO mode (datetime.timedelta object) (can be None with eco = True)
            'max_bid'      : None ,                       # max bid ($/hour) (can be None with eco = True)
            'number'       : 2 ,                          # multiplicity: the number of instance(s) to create
            'explode'      : True                         # multiplicity: can this instance type be distributed accross multiple instances, to split CPUs
        }

    ] ,

    ################################################################################
    # ENVIRONMENTS / SOFTWARE
    ################################################################################

    'environments' : [
        {
            'name'         : 'env_err' ,                       # name of the environment - should be unique if not 'None'. 'None' only when len(environments)==1

            # env_conda + env_pypi  : mamba is used to setup the env (pip dependencies included)
            # env_conda (only)      : mamba is used to setup the env
            # env_pypi  (only)      : venv + pip is used to setup the env 

            'command'      : None ,      # None, or a string: path to a bash file to execute when deploying
            'env_aptget'   : None ,        # None, an array of librarires/binaries for apt-get
            'env_conda'    : "example/environment2.yml",   # None, an array of libraries, a path to environment.yml  file, or a path to the root of a conda environment
            'env_pypi'     : None , # None, an array of libraries, a path to requirements.txt file, or a path to the root of a venv environment 
            'env_julia'    : ['WaveletsSAHJAHSAJ'] ,                       # None, a string or an array of Julia packages to install (requires julia)
        },
        {
            'name'         : 'env0' ,                       # name of the environment - should be unique if not 'None'. 'None' only when len(environments)==1

            # env_conda + env_pypi  : mamba is used to setup the env (pip dependencies included)
            # env_conda (only)      : mamba is used to setup the env
            # env_pypi  (only)      : venv + pip is used to setup the env 

            'command'      : None ,      # None, or a string: path to a bash file to execute when deploying
            'env_aptget'   : None ,        # None, an array of librarires/binaries for apt-get
            'env_conda'    : None,   # None, an array of libraries, a path to environment.yml  file, or a path to the root of a conda environment
            'env_pypi'     : "example/requirements.txt" , # None, an array of libraries, a path to requirements.txt file, or a path to the root of a venv environment 
            'env_julia'    : None ,                       # None, a string or an array of Julia packages to install (requires julia)
        },
        # INSTALL Julia with .sh
        {
            'name'         : 'env1' ,                       # name of the environment - should be unique if not 'None'. 'None' only when len(environments)==1

            # env_conda + env_pypi  : mamba is used to setup the env (pip dependencies included)
            # env_conda (only)      : mamba is used to setup the env
            # env_pypi  (only)      : venv + pip is used to setup the env 

            'command'      : 'example/install_julia.sh' ,      # None, or a string: path to a bash file to execute when deploying
            'env_aptget'   : None ,        # None, an array of librarires/binaries for apt-get
            'env_conda'    : "example/environment.yml",   # None, an array of libraries, a path to environment.yml  file, or a path to the root of a conda environment
            'env_pypi'     : "example/requirements.txt" , # None, an array of libraries, a path to requirements.txt file, or a path to the root of a venv environment 
            'env_julia'    : ["Wavelets"] ,                       # None, a string or an array of Julia packages to install (requires julia)
        },
        # INSTALL Julia with mamba
        {
            'name'         : 'env2' ,                       # name of the environment - should be unique if not 'None'. 'None' only when len(environments)==1

            # env_conda + env_pypi  : mamba is used to setup the env (pip dependencies included)
            # env_conda (only)      : mamba is used to setup the env
            # env_pypi  (only)      : venv + pip is used to setup the env 

            'env_aptget'   : None,        # None, an array of librarires/binaries for apt-get
            'env_conda'    : "example/environment2.yml",   # None, an array of libraries, a path to environment.yml  file, or a path to the root of a conda environment
            'env_pypi'     : None , # None, an array of libraries, a path to requirements.txt file, or a path to the root of a venv environment 
            'env_julia'    : ["Wavelets"]  ,                       # None, a string or an array of Julia packages to install (requires julia)
        },
        # Python env ...
        {
            'name'         : 'env3' ,                       # name of the environment - should be unique if not 'None'. 'None' only when len(environments)==1

            # env_conda + env_pypi  : mamba is used to setup the env (pip dependencies included)
            # env_conda (only)      : mamba is used to setup the env
            # env_pypi  (only)      : venv + pip is used to setup the env 

            'env_aptget'   : None,        # None, an array of librarires/binaries for apt-get
            'env_conda'    : "example/environment.yml",   # None, an array of libraries, a path to environment.yml  file, or a path to the root of a conda environment
            'env_pypi'     : "example/requirements.txt" , # None, an array of libraries, a path to requirements.txt file, or a path to the root of a venv environment 
            'env_julia'    : None  ,                       # None, a string or an array of Julia packages to install (requires julia)
        },
        # Python env ...
        {
            'name'         : 'env4' ,                       # name of the environment - should be unique if not 'None'. 'None' only when len(environments)==1

            # env_conda + env_pypi  : mamba is used to setup the env (pip dependencies included)
            # env_conda (only)      : mamba is used to setup the env
            # env_pypi  (only)      : venv + pip is used to setup the env 

            'env_aptget'   : None,        # None, an array of librarires/binaries for apt-get
            'env_conda'    : ["numpy"],   # None, an array of libraries, a path to environment.yml  file, or a path to the root of a conda environment
            'env_pypi'     : None , # None, an array of libraries, a path to requirements.txt file, or a path to the root of a venv environment 
            'env_julia'    : None  ,                       # None, a string or an array of Julia packages to install (requires julia)
        }            
    ] ,

    ################################################################################
    # JOBS / SCRIPTS
    ################################################################################

    'jobs' : [
        {
            'env_name'     : 'env0' ,                      # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                        # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'example/run_remote.py 2 15',  # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                        # the command to run
            'upload_files' : [ "uploaded.txt"] ,           # any file to upload (array or string) - will be put in the same directory
            'input_file'   : 'input.dat' ,                 # the input file name (used by the script)
            'output_file'  : 'output.dat' ,                # the output file name (used by the script)
        },
        {
            'env_name'     : 'env_err' ,                   # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                        # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'example/run_julia.jl 1 10',  # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                        # the command to run
            'upload_files' : None ,                        # any file to upload (array or string) - will be put in the same directory
            'input_file'   : 'input.dat' ,                 # the input file name (used by the script)
            'output_file'  : 'output.dat' ,                # the output file name (used by the script)
        },
        {
            'env_name'     : 'env4' ,                      # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                        # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'example/run_remote_err_mem.py',  # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                        # the command to run
            'upload_files' : None ,                        # any file to upload (array or string) - will be put in the same directory
            'input_file'   : 'input.dat' ,                 # the input file name (used by the script)
            'output_file'  : 'output.dat' ,                # the output file name (used by the script)
        },        
        {
            'env_name'     : 'env2' ,                       # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                       # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'example/run_julia_err_mem.jl',# the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                       # the command to run
            'upload_files' : None ,  # any file to upload (array or string) - will be put in the same directory
            'input_file'   : 'input.dat' ,                # the input file name (used by the script)
            'output_file'  : 'output.dat' ,               # the output file name (used by the script)
        },
        {
            'env_name'     : 'env4' ,                      # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                        # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'example/run_remote.py 2 7',  # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                        # the command to run
            'upload_files' : [ "uploaded.txt"] ,           # any file to upload (array or string) - will be put in the same directory
            'input_file'   : 'input.dat' ,                 # the input file name (used by the script)
            'output_file'  : 'output.dat' ,                # the output file name (used by the script)
        },
        {
            'env_name'     : 'env4' ,                       # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                        # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'example/run_remote.py 2 8', # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                        # the command to run
            'upload_files' : [ "uploaded.txt"] ,           # any file to upload (array or string) - will be put in the same directory
            'input_file'   : 'input.dat' ,                 # the input file name (used by the script)
            'output_file'  : 'output.dat' ,                # the output file name (used by the script)
        },
        {
            'env_name'     : 'env4' ,                      # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                        # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'example/run_remote_err.py 2 11', # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                        # the command to run
            'upload_files' : [ "uploaded.txt"] ,           # any file to upload (array or string) - will be put in the same directory
            'input_file'   : 'input.dat' ,                 # the input file name (used by the script)
            'output_file'  : 'output.dat' ,                # the output file name (used by the script)
        },
        {
            'env_name'     : 'env1' ,                       # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                       # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'example/run_julia.jl 1 10',# the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                       # the command to run
            'upload_files' : [ "/Users/ben/config.log" , "uploaded.txt"] ,  # any file to upload (array or string) - will be put in the same directory
            'input_file'   : 'input.dat' ,                # the input file name (used by the script)
            'output_file'  : 'output.dat' ,               # the output file name (used by the script)
            'repeat'       : 1
        } ,        
        {
            'env_name'     : 'env2' ,                       # the environment to use (can be 'None' if solely one environment is provided above)
            'cpus_req'     : None ,                       # the CPU(s) requirements for the process (can be None)
            'run_script'   : 'example/run_julia.jl 1 10',# the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
            'run_command'  : None ,                       # the command to run
            'upload_files' : [ "/Users/ben/config.log" , "uploaded.txt"] ,  # any file to upload (array or string) - will be put in the same directory
            'input_file'   : 'input.dat' ,                # the input file name (used by the script)
            'output_file'  : 'output.dat' ,               # the output file name (used by the script)
        } ,
        # {
        #     'env_name'     : 'env1' ,                       # the environment to use (can be 'None' if solely one environment is provided above)
        #     'cpus_req'     : None ,                       # the CPU(s) requirements for the process (can be None)
        #     'run_script'   : 'example/run_julia.jl 2 12',# the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
        #     'run_command'  : None ,                       # the command to run
        #     'upload_files' : [ "uploaded.txt"] ,          # any file to upload (array or string) - will be put in the same directory
        #     'input_file'   : 'input.dat' ,                # the input file name (used by the script)
        #     'output_file'  : 'output.dat' ,               # the output file name (used by the script)
        # },
        # {
        #     'env_name'     : 'env3' ,                      # the environment to use (can be 'None' if solely one environment is provided above)
        #     'cpus_req'     : None ,                        # the CPU(s) requirements for the process (can be None)
        #     'run_script'   : 'example/run_remote.py 2 5',  # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
        #     'run_command'  : None ,                        # the command to run
        #     'upload_files' : [ "uploaded.txt"] ,           # any file to upload (array or string) - will be put in the same directory
        #     'input_file'   : 'input.dat' ,                 # the input file name (used by the script)
        #     'output_file'  : 'output.dat' ,                # the output file name (used by the script)
        # },
        # {
        #     'env_name'     : 'env3' ,                      # the environment to use (can be 'None' if solely one environment is provided above)
        #     'cpus_req'     : None ,                        # the CPU(s) requirements for the process (can be None)
        #     'run_script'   : 'example/run_remote.py 2 7',  # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
        #     'run_command'  : None ,                        # the command to run
        #     'upload_files' : [ "uploaded.txt"] ,           # any file to upload (array or string) - will be put in the same directory
        #     'input_file'   : 'input.dat' ,                 # the input file name (used by the script)
        #     'output_file'  : 'output.dat' ,                # the output file name (used by the script)
        # },
        # {
        #     'env_name'     : 'env3' ,                       # the environment to use (can be 'None' if solely one environment is provided above)
        #     'cpus_req'     : None ,                        # the CPU(s) requirements for the process (can be None)
        #     'run_script'   : 'example/run_remote.py 2 8', # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
        #     'run_command'  : None ,                        # the command to run
        #     'upload_files' : [ "uploaded.txt"] ,           # any file to upload (array or string) - will be put in the same directory
        #     'input_file'   : 'input.dat' ,                 # the input file name (used by the script)
        #     'output_file'  : 'output.dat' ,                # the output file name (used by the script)
        # },
        # {
        #     'env_name'     : 'env3' ,                      # the environment to use (can be 'None' if solely one environment is provided above)
        #     'cpus_req'     : None ,                        # the CPU(s) requirements for the process (can be None)
        #     'run_script'   : 'example/run_remote.py 2 11', # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
        #     'run_command'  : None ,                        # the command to run
        #     'upload_files' : [ "uploaded.txt"] ,           # any file to upload (array or string) - will be put in the same directory
        #     'input_file'   : 'input.dat' ,                 # the input file name (used by the script)
        #     'output_file'  : 'output.dat' ,                # the output file name (used by the script)
        # }
    ]
}