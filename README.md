# Description

CloudRun is a Python package that allows you to run any script on a cloud service (for now AWS only).

## Installation

```bash
python3 -m venv .venv
source ./.venv/bin/activate
python -m pip install -r requirements.txt
```

## Usage / Test runs

First, write your config file (see exmaple/config.example.py)

```bash
# to run
python3 app.py

# to retrieve state
python3 cli.py getstate SCRIPT_HASH UID

# to wait for DONE state
python3 cli.py wait SCRIPT_HASH UID
```

## Python API

```python
class CloudRunProvider:

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