## Philosophy API

- runner = homogeneous INSTANCES by can handle multiple / can be different environments ...
- but you can use different num of CPUs within a runner 

## Features

1) tail
  - [ ] implement tail call

2) re-organize config:
  - [x] instances (plural) - cf. notes / philosophy:
    - [x] instance_types = [ instance_type ]
    - [x] instance_type  = { current hardware/instance definition + hard drive size + 'number' option + 'explode' option }
    - [x] OBJ instance   = { instance_type + rank } (rank can be > 1 when 'explode'=True )
  - [x] environments     = [ environment ]
    - [x] environments   = [ environment ]
    - [x] environment    = { current env definition + optional unique 'name' field }
  - [x] scripts: 
    - [x] scripts        = [ script_info ]
    - [x] script_info    = { existing script info + 'cpus_req' option + 'env_name' (optional) }
  - [x] new global options:
    - [x] maestro        = 'local' | 'remote' (nano) | 'lambda'
  - [x] use new instances variables:
    - [x] disk_size
    - [x] disk_type

3) Re-factorize classes / plurality / calls etc.
  - [x] improve script hash computation to use command and uploaded files list ...
  - [x] improve run.sh to wait for the environment to be bootstraped
  - [x] improve script handling to allow args after the python/julia name...
  - [x] improve structure of execution to:
    - [x] create uid directory 
    - [x] move uploaded files to script hash directory (hash now computed with script name, args + uploaded)
    - [x] move script file to to script hash directory as well (hash now computed with script name, args + uploaded)
  - [x] refactor existing code to minimize arguments (not config everywhere but exactly what it needs ...)
  - [x] preprocess environnement links: adds env_name to single environment and scripts if not there
  - [x] sanity checks:
    - [x] check that env_name links are correct in scripts 
  - [x] get_environment(name) in CloudSendProvider 
  - [x] don't forget to sort the upload_files by value !!! When computing the script hash !
  - [x] use input file name for script_hash too
  - [x] use absolute file names to be more robust (if cloudsend runs somewhere else with same relative oath .  This should give a different hash). This applies to uploaded files, script file path, NOT command path and input file
  - [x] move ALL env_obj logic to CloudSendEnvironment class. Basically only the create object in AWSProvider
  - [x] we should be able to also initialize env hash n the init method of the class _init_(self,env_config)
  - [x] rename C like AWS method to aws_create_instance() etc.
  - [x] remove script hash from ScriptRuntimeInfo
  - [x] create ClourRunJob with script hash
  - [x] change Script to Job ?
  - [x] put a lot more methods in CloudSend base class. Basically on create_objects and maybe wait_for ? But we could use class even for that ... 
  - [x] save command in process directory
  - [x] make state.sh handle multiple uid/pid
  - [ ] create a getByName state (using the command line)
  - [x] generate dynamically bash .sh file to start all the jobs ...
  - [x] save uid of scripts in a json file (statemanager)
  - [x] explode uploads between instance setup, env setup and run setup ...
  - [x] maybe we should not put the script arguments in the hash ? This is more a runtime thing 
  - [x] allocate job to instance before doing anything
  - [x] CloudSendInstance class stores the client once for all (for a region) >> it will store just the region
  - [x] use instance class
  - [x] rewrite CloudSend to handle plurality / new config
  - [x] run-dry to check CPUs settings compatibilty BEFORE job assignation >> we separated start() and deploy()
  - [ ] online vs offline bin packing >> online bin packing used by the nano instance (use yield?)
  - [x] improve handling of uploaded files: 
    - [x] keep tree structure (what to do when absolute files?)
    - [x] define 'upload_base_path' in config?
    - [x] add symbolic links under the run_dir to point to the job_dir where its uploaded (parent dir)
    - [x] if there is no directory involve we need to create a symbolic link for each file 
  - [x] fix bug with missing environment when using instance.get_environments() in _deploy_environments
  - [x] move remote_files as resources in package
  - [x] fix bug that co-routines are not concurrent in gather (visible with print_deploy = True) >> use concurrent.futures. run_in_executor OR https://stackoverflow.com/questions/28492103/how-to-combine-python-asyncio-with-threads
  - [x] check why sometimes processes are considered aborted at the very beginning - issue with env ?
  - [x] smarter recovery mode that looks at the jobs that have been completed ...
  - [x] add set_aborted_on_disconnect (to set all running states to aborted (because of disconnect))
  - [x] get_jobs_state: complement dynamically the list of processes with the current process list returned to get
  - [x] finish mark aborted function
  - [x] re-run jobs, with aborted checkups 
  - [x] factorize handle_instance_disconnect
  - [x] add batch uid to deploy job or process
  - [x] display batchuid in summary if not None
  - [x] handle also if it's a simple disconnection from SSH (remove wifi to test)
  - [ ] clean up unused functions and the get/create/find/update stuff ...
  - [x] check generous creation of deployed jobs
  - [x] move config loading stuff to a config package with ConfigManager class
  - [x] this is in preparation of config serialization and reloading to serialize state .... StateManager class in config 
  - [x] DEBUG why the state of old jobs on a newly created instance is returning as NOT ABORTED??
    - start with state serialization
    - kill the program when the first jobs are running
    - terminate one of the instance that has the script running
    - restart the program
    - Note: it will do probably whats required but the state is wrong. The latest processes should be saying "ABORTED"
  - [x] DEBUG idem as before but by kiling the program in WAIT states
  - [x] improve more paths issue (local vs remote)
  - [x] add 'env_bash' to environment so we can handle a user script during deploy ... >> 'command'
  - [x] if error with image not available for region: list the AMI for the region (Linux)
  - [x] HANDLE files separately (for all jobs):
     - [x] dictionnary with absolute local path as key
     - [x] put all of them in one place (once for all)
     - [x] have the ln_command create all the necessary links 
     Basically we're only removing the files form the jobs' dirs and moving them to a separate folder, to mutualize them better ...
  - [ ] debug regression with state recovery after terminating instances and re-running 
  - [x] debug regression with bootstraping not printing out with option
  - [x] fetch log when process has aborted, and print it
  - [ ] improve UI with Python RICH , OR https://towardsdatascience.com/a-complete-guide-to-using-progress-bars-in-python-aa7f4130cda8
  - [ ] handle when we stop an instance while its still deploying / waiting ... 
  - [x] debug why successive runs locks
  - [x] debug why remote mode prints nothing with state recovery ON
  - [x] handle KeyPair better: append the owner ID to the file name so that we can switch profile without deleting and terminating stuff 
  - [x] handle when the KeyPair is not found on file better ...
  - [x] debug:  An error occurred (InvalidParameterValue) when calling the AssociateIamInstanceProfile operation: Value (arn:aws:iam::870777542080:instance-profile/cloudsend-maestro-profile) for parameter iamInstanceProfile.arn is invalid. Invalid IAM Instance Profile ARN
  - [x] debug 'local' why when terminating an instance, the watch() AS daemon + wait() method are not stopping ... ISSUE WITH PROCESSES LIST?
  - [x] auto-stop function
  - [ ] maestro multiple projects handling
  - [ ] switch back to asyncio

4) local mode:
  - [x] handle new config 
  - [ ] Maestro feature:
    - [x] Batch feature
    - [x] Load Balancer
      - [x] tetris function: distribute according to script CPUs needs (packing algorithm)
      - [ ] adjust the number of instances running

5) nano mode:
  - [ ] same as lambda but we keep the sftp_put formalism (as with fat client)

6) lambda mode:
  - [ ] fat client setup lambda with requirements.txt
  - [ ] fat client uploads cloudsend files >> this becomes the Lambda Maestro
  - [ ] fat client uploads .sh script files to S3
  - [ ] switch to light client
  - [ ] light client will only upload config to S3
  - >> instances will pull config and script files from s3 (download instead of sftp_put)
  - >> Lambda maestro = load balancer + ducklings mom perform regular checks from Lambda

Note AWS: it is better cost wise to explode 128 CPUs in 8 instances with 16 CPUs ... (e.g.)

