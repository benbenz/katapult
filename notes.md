## Philosophy API

- runner = homogeneous INSTANCES by can handle multiple / can be different environments ...
- but you can use different num of CPUs within a runner 

## Features

1) tail

2) re-organize config:
  - instances (plural) - cf. notes / philosophy:
    - instance_types = [ instance ]
    - instance = { current hardware/instance definition + 'explode' option }
  - environments = [ environment ]
    - environments = [ environment ]
    - environment = { current env definition + 'name' field }
  - jobs: 
    - jobs = [ script ]
    - script = { existing script info + 'cpu' option + 'env_name' }
  - new options:
    - maestro = 'local' | 'lambda' | 'nano'

3) local mode:
  - handle new config
  - Maestro feature:
    - Batch feature
    - Load Balancer
      - tetris function: distribute according to script CPUs needs (packing algorithm)
      - adjust the number of instances running



3) lambda mode:
  - fat client setup lambda with requirements.txt
  - fat client uploads cloudrun files >> this becomes the Lambda Maestro
  - fat client uploads .sh script files to S3
  - switch to light client
  - light client will only upload config to S3
  >> instances will pull config and script files from s3 (download instead of sftp_put)
  >> Lambda maestro = load balancer + ducklings mom perform regular checks from Lambda

4) nano mode:
  - same as lambda but we keep the sftp_pu formalism (as with fat client)

Note AWS: it is better cost wise to explode 128 CPUs in 8 instances with 16 CPUs ... (e.g.)

