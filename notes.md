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

3) Re-factorize classes / plurality / calls etc.
  - [ ] improve script has to use script name / command + uploaded files  
  - [ ] improve script handling to allow args after the python/julia name...
  - [ ] improve structure of execution to:
        - [ ] create uid directory 
        - [ ] move uploaded files to uid subdirectory
        - [ ] move script file to uid subdirectory as well
  - [ ] refactor existing code to minimize arguments (not config everywhere but exactly what it needs ...)
  - [ ] CloudRunInstance class stores the client once for all (for a region)
  - [ ] use instance class ?
  - [ ] rewrite CloudRun to handle plurality / new config

4) local mode:
  - [ ] handle new config 
  - [ ] Maestro feature:
    - [ ] Batch feature
    - [ ] Load Balancer
      - [ ] tetris function: distribute according to script CPUs needs (packing algorithm)
      - [ ] adjust the number of instances running

5) nano mode:
  - [ ] same as lambda but we keep the sftp_pu formalism (as with fat client)

6) lambda mode:
  - [ ] fat client setup lambda with requirements.txt
  - [ ] fat client uploads cloudrun files >> this becomes the Lambda Maestro
  - [ ] fat client uploads .sh script files to S3
  - [ ] switch to light client
  - [ ] light client will only upload config to S3
  - >> instances will pull config and script files from s3 (download instead of sftp_put)
  - >> Lambda maestro = load balancer + ducklings mom perform regular checks from Lambda

Note AWS: it is better cost wise to explode 128 CPUs in 8 instances with 16 CPUs ... (e.g.)

