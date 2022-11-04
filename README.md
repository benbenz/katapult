# Description

CloudRun is a Python package that allows you to run any script on a cloud service (for now AWS only).

## Installation

```bash
python3 -m venv .venv
source ./.venv/bin/activate
python -m pip install -r requirements.txt
```

## Usage / Test runs

```bash
# copy the example file
cp example/config.example.py config.py
#
# EDIT THE FILE
#

# to run
python3 app.py

# to retrieve state
python3 cli.py getstate SCRIPT_HASH UID

# to wait for DONE state
python3 cli.py wait SCRIPT_HASH UID
```

## Check config example

```python
from datetime import timedelta

config = {
    'project'      : 'test' ,                     # this will be concatenated with the instance & env hashes (if not None) 
    'dev'          : False ,                      # When True, this will ensure the same instance and dev environement are being used (while working on building up the project) 
    'debug'        : 1 ,                          # debug level (0...3)

    # "provider"
    'provider'     : 'aws' ,                      # the provider name ('aws' | 'azure' | ...)

    # "instance" section
    'cloud_id'     : 'vpc-0babc28485f6730bc' ,    # can be None, or even wrong/non-existing - then the default one is used
    'region'       : 'eu-west-3' ,                # has to be valid
    'img_id'       : 'ami-077fd75cd229c811b' ,    # OS image: has to be valid and available for the profile (user/region)
    'img_username' : 'ubuntu' ,                   # the SSH user for the image
    'size'         : 't2.micro' ,                 # proprietary size spec (has to be valid)
    'cpus'         : None ,                       # number of CPU cores
    'gpu'          : None ,                       # the proprietary type of the GPU 
    'eco'          : True ,                       # eco == True >> SPOT e.g.
    'eco_life'     : timedelta(days=30) ,         # lifecycle of the machine in ECO mode (timedelta) (can be None with eco = True)
    'max_bid'      : None ,                       # max bid ($/hour) (can be None with eco = True)

    # "environment" section
    # env_conda + env_pypi   >> mamba is used to setup the env (pip dependencies included)
    # env_conda (only)       >> mamba is used to setup the env
    # env_pypi  (only)       >> venv + pip is used to setup the env 
    'env_aptget'   : [ "openssh-client"] ,        # None, an array of librarires/binaries for apt-get
    'env_conda'    : "example/environment.yml",   # None, an array of libraries, a path to environment.yml  file, or a path to the root of a conda environment
    'env_pypi'     : "example/requirements.txt" , # None, an array of libraries, a path to requirements.txt file, or a path to the root of a venv environment 

    # "script"/"command" section
    'run_script'   : 'example/run_remote.py' ,    # the script to run (Python (.py) or Julia (.jl) for now) (prioritised vs 'run_command')
    'run_command'  : None ,                       # the command to run
    'upload_files' : [ "example/uploaded.txt"] ,  # any file to upload (array or string) - will be put in the same directory
    'input_file'   : 'input.dat' ,                # the input file name (used by the script)
    'output_file'  : 'output.dat' ,               # the output file name (used by the script)
}
```

## Python API

```python
class CloudRunProvider:

    def __init__(config):
       pass

    def get_instance():
       pass

    def start_instance():
       pass

    def stop_instance():
       pass

    def terminate_instance():
       pass

    async def run_script():
       pass

    async def get_script_state( script_hash , uid , pid = None ):
       pass

    async def wait_for_script_state( script_state , script_hash , uid , pid = None ):
       pass

    async def tail( self, script_hash , uid , pid = None ):
       pass
 
```

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License
[MIT](https://choosealicense.com/licenses/mit/)