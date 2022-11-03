import boto3
import os , json
import cloudrunutils
import paramiko
from botocore.exceptions import ClientError
from datetime import datetime , timedelta
import asyncio

cr_keypairName         = 'cloudrun-keypair'
cr_secGroupName        = 'cloudrun-sec-group-allow-ssh'
cr_bucketName          = 'cloudrun-bucket'
cr_vpcName             = 'cloudrun-vpc'
cr_instanceNameRoot    = 'cloudrun-instance'
cr_environmentNameRoot = 'cloudrun-env'

DBG_LVL = 1

class CloudRunAWSError(Exception):
    pass

def debug(level,*args):
    if level <= DBG_LVL:
        print(*args)

def create_keypair(config):
    debug(1,"Creating KEYPAIR ...")
    ec2_client = boto3.client("ec2", region_name=config['region'])
    ec2 = boto3.resource('ec2')

    keypair = None
    try:
        keypair = ec2_client.create_key_pair(
            KeyName=cr_keypairName,
            DryRun=True,
            KeyType='rsa',
            KeyFormat='pem'
        )
    except ClientError as e: #DryRun=True >> always an "error"
        errmsg = str(e)
        
        if 'UnauthorizedOperation' in errmsg:
            debug(1,"The account is not authorized to create a keypair, please specify an existing keypair in the configuration or add Administrator privileges to the account")
            keypair = None
            #sys.exit()
            raise CloudRunAWSError()

        elif 'DryRunOperation' in errmsg: # we are good with credentials
            try :
                keypair = ec2_client.create_key_pair(
                    KeyName=cr_keypairName,
                    DryRun=False,
                    KeyType='rsa',
                    KeyFormat='pem'
                )
                pemfile = open("cloudrun.pem", "w")
                pemfile.write(keypair['KeyMaterial']) # save the private key in the directory (we will use it with paramiko)
                pemfile.close()
                os.chmod(path, 0o600) # change permission to use with ssh (for debugging)
                debug(2,keypair)

            except ClientError as e2: # the keypair probably exists already
                errmsg2 = str(e2)
                if 'InvalidKeyPair.Duplicate' in errmsg2:
                    #keypair = ec2.KeyPair(cr_keypairName)
                    keypairs = ec2_client.describe_key_pairs( KeyNames= [cr_keypairName] )
                    keypair  = keypairs['KeyPairs'][0] 
                    debug(2,keypair)
                else:
                    debug(1,"An unknown error occured while retrieving the KeyPair")
                    debug(2,errmsg2)
                    #sys.exit()
                    raise CloudRunAWSError()

        
        else:
            debug(1,"An unknown error occured while creating the KeyPair")
            debug(2,errmsg)
            #sys.exit()
            raise CloudRunAWSError()
    
    return keypair 

def find_or_create_default_vpc():
    ec2_client = boto3.client("ec2", region_name=config['region'])
    vpcs = ec2_client.describe_vpcs(
        Filters=[
            {
                'Name': 'is-default',
                'Values': [
                    'true',
                ]
            },
        ]
    )
    defaultvpc = ec2_client.create_default_vpc() if len(vpcs['Vpcs'])==0 else vpcs['Vpcs'][0] 
    return defaultvpc

def create_vpc(config):
    debug(1,"Creating VPC ...")
    vpc = None
    ec2_client = boto3.client("ec2", region_name=config['region'])

    if 'cloud_id' in config:
        vpcID = config['cloud_id']
        try :
            vpcs = ec2_client.describe_vpcs(
                VpcIds=[
                    vpcID,
                ]
            )
            vpc = vpcs['Vpcs'][0]
        except ClientError as ce:
            ceMsg = str(ce)
            if 'InvalidVpcID.NotFound' in ceMsg:
                debug(1,"WARNING: using default VPC. "+vpcID+" is unavailable")
                vpc = find_or_create_default_vpc() 
            else:
                debug(1,"WARNING: using default VPC. Unknown error")
                vpc = find_or_create_default_vpc() 

    else:
        debug(1,"using default VPC (no VPC ID specified in config)")
        vpc = find_or_create_default_vpc()
    debug(2,vpc)

    return vpc 

def create_security_group(config,vpc):
    debug(1,"Creating SECURITY GROUP ...")
    secGroup = None
    ec2_client = boto3.client("ec2", region_name=config['region'])

    secgroups = ec2_client.describe_security_groups(Filters=[
        {
            'Name': 'group-name',
            'Values': [
                cr_secGroupName,
            ]
        },
    ])
    if len(secgroups['SecurityGroups']) == 0: # we have no security group, lets create one
        debug(1,"Creating new security group")
        secGroup = ec2_client.create_security_group(
            VpcId = vpc['VpcId'] ,
            Description = 'Allow SSH connection' ,
            GroupName = cr_secGroupName 
        )

        data = ec2_client.authorize_security_group_ingress(
            GroupId=secGroup['GroupId'],
            IpPermissions=[
                {'IpProtocol': 'tcp',
                'FromPort': 80,
                'ToPort': 80,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},
                {'IpProtocol': 'tcp',
                'FromPort': 22,
                'ToPort': 22,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ])
        debug(1,'Ingress Successfully Set %s' % data)

    else:
        secGroup = secgroups['SecurityGroups'][0]
    
    if secGroup is None:
        debug(1,"An unknown error occured while creating the security group")
        #sys.exit()
        raise CloudRunAWSError()
    
    debug(2,secGroup) 

    return secGroup

# for now just return the first subnet present in the Vpc ...
def create_subnet(config,vpc):
    debug(1,"Creating SUBNET ...")
    ec2 = boto3.resource('ec2')
    ec2_client = boto3.client("ec2", region_name=config['region'])
    vpc_obj = ec2.Vpc(vpc['VpcId'])
    for subnet in vpc_obj.subnets.all():
        subnets = ec2_client.describe_subnets(SubnetIds=[subnet.id])
        subnet = subnets['Subnets'][0]
        debug(2,subnet)
        return subnet
    return None # todo: create a subnet

def create_bucket():

    debug(1,"Creating BUCKET ...")

    s3_client = boto3.client('s3', region_name=config['region'])
    s3 = boto3.resource('s3')

    try :

        bucket = s3_client.create_bucket(
            ACL='private',
            Bucket=cr_bucketName,
            CreateBucketConfiguration={
                'LocationConstraint': config['region']
            },

        )

    except ClientError as e:
        errMsg = str(e)
        if 'BucketAlreadyExists' in errMsg:
            bucket = s3.Bucket(cr_bucketName)
        elif 'BucketAlreadyOwnedByYou' in errMsg:
            bucket = s3.Bucket(cr_bucketName)

    debug(2,bucket)

    return bucket 


def upload_file( bucket , file_path ):
    debug(1,"uploading FILE ...")
    s3_client = boto3.client('s3', region_name=config['region'])
    response = s3_client.upload_file( file_path, bucket['BucketName'], 'cr-run-script' )
    debug(2,response)

def init_instance_name(config):
    if ('dev' in config) and (config['dev'] == True):
        return cr_instanceNameRoot
    else:
        instance_hash = cloudrunutils.compute_instance_hash(config)

        if 'project' in config:
            return cr_instanceNameRoot + '-' + config['project'] + '-' + instance_hash
        else:
            return cr_instanceNameRoot + '-' + instance_hash    

def find_instance(config):

    debug(1,"Searching INSTANCE ...")

    instanceName = init_instance_name(config)

    ec2_client = boto3.client("ec2", region_name=config['region'])

    existing = ec2_client.describe_instances(
        Filters = [
            {
                'Name': 'tag:Name',
                'Values': [
                    instanceName
                ]
            },
            {
                'Name': 'instance-state-name' ,
                'Values' : [ # everything but 'terminated' and 'shutting down' ?
                    'pending' , 'running' , 'stopping' , 'stopped'
                ]
            }
        ]
    )

    if len(existing['Reservations']) > 0 and len(existing['Reservations'][0]['Instances']) >0 :
        instance = existing['Reservations'][0]['Instances'][0]
        debug(1,"Found exisiting instance !",instance['InstanceId'])
        debug(2,instance)
        return instance 
    
    else:

        return None 


def create_instance(config,vpc,subnet,secGroup):

    debug(1,"Creating INSTANCE ...")

    instanceName = init_instance_name(config)

    ec2_client = boto3.client("ec2", region_name=config['region'])

    existing = ec2_client.describe_instances(
        Filters = [
            {
                'Name': 'tag:Name',
                'Values': [
                    instanceName
                ]
            },
            {
                'Name': 'instance-state-name' ,
                'Values' : [ # everything but 'terminated' and 'shutting down' ?
                    'pending' , 'running' , 'stopping' , 'stopped'
                ]
            }
        ]
    )

    #print(existing)

    created = False

    if len(existing['Reservations']) > 0 and len(existing['Reservations'][0]['Instances']) >0 :
        instance = existing['Reservations'][0]['Instances'][0]
        debug(1,"Found exisiting instance !",instance['InstanceId'])
        debug(2,instance)
        return instance , created

    if 'cpus' in config and config['cpus'] is not None:
        cpus_spec = {
            'CoreCount': config['cpus'],
            'ThreadsPerCore': 1
        },
    else:
        cpus_spec = { }  

    if 'gpu' in config and config['gpu']:
        gpu_spec = [ { 'Type' : config['gpu'] } ]
    else:
        gpu_spec = [ ]
    
    if 'eco' in config and config['eco'] :
        market_options = {
            'MarketType': 'spot',
            'SpotOptions': {
                'SpotInstanceType': 'persistent', #one-time'|'persistent',
                'InstanceInterruptionBehavior': 'stop' #'hibernate'|'stop'|'terminate'
            }
        }     
        if 'eco_life' in config and isinstance(config['eco_life'],timedelta):
            validuntil = datetime.today() + config['eco_life']
            market_options['SpotOptions']['ValidUntil'] = validuntil
        if 'max_bid' in config and isinstance(config['max_bid'],str):
            market_options['SpotOptions']['MaxPrice'] = config['max_bid']
    else:
        market_options = { } 

    instances = ec2_client.run_instances(
            ImageId = config['img_id'],
            MinCount = 1,
            MaxCount = 1,
            InstanceType = config['size'],
            KeyName = cr_keypairName,
            SecurityGroupIds=[secGroup['GroupId']],
            SubnetId = subnet['SubnetId'],
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': instanceName
                        },
                    ]
                },
            ],
            ElasticGpuSpecification = gpu_spec ,
            InstanceMarketOptions = market_options,
            CpuOptions = cpus_spec,
            HibernationOptions={
                'Configured': False
            },            
    )    

    created = True

    debug(2,instances["Instances"][0])

    return instances["Instances"][0] , created

def start_instance(instance):
    ec2_client = boto3.client("ec2", region_name=config['region'])

    ec2_client.start_instances(InstanceIds=[instance['InstanceId']])

def stop_instance(instance):
    ec2_client = boto3.client("ec2", region_name=config['region'])

    ec2_client.stop_instances(InstanceIds=[instance['InstanceId']])

def terminate_instance(instance):

    ec2_client = boto3.client("ec2", region_name=config['region'])

    ec2_client.terminate_instances(InstanceIds=[instance['InstanceId']])

    if instance['SpotInstanceRequestId']:

        ec2_client.cancel_spot_instance_requests(SpotInstanceRequestIds=[instance['SpotInstanceRequestId']])

def run_instance_script(config,vpc,subnet,secGroup,script):

    debug(1,"Creating INSTANCE ...")

    ec2_client = boto3.client("ec2", region_name=config['region'])

    instanceName = cr_instanceNameRoot

    instances = ec2_client.run_instances(
            ImageId = config['img_id'],
            MinCount = 1,
            MaxCount = 1,
            InstanceType = 't2.micro',
            KeyName = cr_keypairName,
            SecurityGroupIds=[secGroup['GroupId']],
            SubnetId = subnet['SubnetId'],
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'Name',
                            'Value': instanceName
                        },
                    ]
                },
            ],
            InstanceInitiatedShutdownBehavior='terminate',
            UserData=script
    )    

    debug(2,instances["Instances"][0])

    return instances["Instances"][0]    

def get_instance_info(config,instance):
    ec2_client   = boto3.client("ec2", region_name=config['region'])
    instances    = ec2_client.describe_instances( InstanceIds=[instance['InstanceId']] )
    instance_new = instances['Reservations'][0]['Instances'][0]
    return instance_new

def get_public_ip(config,instance_id):
    ec2_client = boto3.client("ec2", region_name=config['region'])
    reservations = ec2_client.describe_instances(InstanceIds=[instance_id]).get("Reservations")

    for reservation in reservations:
        for instance in reservation['Instances']:
            print(instance.get("PublicIpAddress"))    


def list_amis(config):
    ec2 = boto3.client('ec2', region_name=config['region'])
    response = ec2.describe_instances()
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            print(instance["ImageId"])

def init_environment(conf):
    env_obj  = cloudrunutils.compute_environment_object(conf)
    env_hash = cloudrunutils.compute_environment_hash(env_obj)

    env_name = cr_environmentNameRoot

    if ('dev' in conf) and (conf['dev'] == True):
        env_name = cr_environmentNameRoot
    else:
        if 'project' in conf:
            env_name = cr_environmentNameRoot + '-' + conf['project'] + '-' + env_hash
        else:
            env_name = cr_environmentNameRoot + '-' + env_hash    

    # overwrite name in conda config as well
    if env_obj['env_conda'] is not None:
        env_obj['env_conda']['name'] = env_name 
    env_obj['name'] = env_name
    env_obj['hash'] = env_hash
    env_obj['path'] = "$HOME/run/" + env_name
    env_obj['path_abs'] = "/home/" + conf['img_username'] + '/run/' + env_name

    # replace __REQUIREMENTS_TXT_LINK__ with the actual requirements.txt path (dependent of config and env hash)
    # the file needs to be absolute
    env_obj = cloudrunutils.update_requirements_path(env_obj,env_obj['path_abs'])

    return env_obj             

def line_buffered(f):
    line_buf = ""
    try :
        while not f.channel.exit_status_ready():
            try:
                line_buf += f.read(16).decode("utf-8")
                if line_buf.endswith('\n'):
                    yield line_buf
                    line_buf = ''
            except:
                pass
    except:
        pass

####################
#                  #
# PUBLIC FUNCTIONS #
#                  #
####################

def set_debug_level(value):
    DBG_LVL = value

def start(config):

    instance = find_instance(config)

    if instance is None:
        keypair  = create_keypair(config)
        vpc      = create_vpc(config) 
        secGroup = create_security_group(config,vpc)
        subnet   = create_subnet(config,vpc) 
        instance , created = create_instance(config,vpc,subnet,secGroup)
    else:
        created = False

    return instance , created

def stop(instance):
    stop_instance(instance)

def terminate(instance):
    terminate_instance(instance)

async def run(config):

    if (not 'input_file' in config) or (not 'output_file' in config) or not isinstance(config['input_file'],str) or not isinstance(config['output_file'],str):
        print("\n\nConfiguration requires an input and output file names\n\n")
        raise CloudRunAWSError() 

    # CHECK EVERY TIME !
    instance , created = start(config)

    # get the public DNS info when instance actually started (todo: check actual state)
    waitFor = True
    while waitFor:
        updated_instance_info = get_instance_info(config,instance)
        lookForDNS   = not 'PublicDnsName' in updated_instance_info or updated_instance_info['PublicDnsName'] is None
        instanceState =  updated_instance_info['State']['Name']

        lookForState = True
        # 'pending'|'running'|'shutting-down'|'terminated'|'stopping'|'stopped'
        if instanceState == 'stopped' or instanceState == 'stopping':
            # restart the instance
            start_instance(instance)

        elif instanceState == 'running':
            lookForState = False

        waitFor = lookForDNS or lookForState  
        if waitFor:
            if lookForDNS:
                debug(1,"waiting for DNS address and  state ...",instanceState)
            else:
                debug(1,"waiting for state ...",instanceState)
            
            await asyncio.sleep(10)

    debug(2,updated_instance_info)    

    # init environment object
    env_obj = init_environment(config)
    debug(2,json.dumps(env_obj))

    # ssh into instance and run the script from S3/local? (or sftp)
    k = paramiko.RSAKey.from_private_key_file('cloudrun.pem')
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    debug(1,"connecting to ",updated_instance_info['PublicDnsName'],"/",updated_instance_info['PublicIpAddress'])
    while True:
        try:
            ssh_client.connect(hostname=updated_instance_info['PublicDnsName'],username=config['img_username'],pkey=k) #,password=’mypassword’)
            break
        except paramiko.ssh_exception.NoValidConnectionsError as cexc:
            print(cexc)
            await asyncio.sleep(4)
            debug(1,"Retrying ...")
        except OSError as ose:
            print(ose)
            await asyncio.sleep(4)
            debug(1,"Retrying ...")

    debug(1,"connected")

    files_path = env_obj['path']

    run_hash = cloudrunutils.compute_script_hash(config)

    run_path   = env_obj['path_abs'] + '/' + run_hash

    script_command = cloudrunutils.compute_script_command(run_path,config)

    debug(1,"creating directories ...")
    stdin0, stdout0, stderr0 = ssh_client.exec_command("mkdir -p "+files_path+" "+run_path)
    debug(1,"directories created")


    debug(1,"uploading files ... ")

    # upload the install file, the env file and the script file
    ftp_client = ssh_client.open_sftp()

    # change to env dir
    ftp_client.chdir(env_obj['path_abs'])
    remote_config = 'config-'+env_obj['name']+'.json'
    with open(remote_config,'w') as cfg_file:
        cfg_file.write(json.dumps(env_obj))
        cfg_file.close()
        ftp_client.put(remote_config,'config.json')
        os.remove(remote_config)
    ftp_client.put('remote_files/config.py','config.py')
    ftp_client.put('remote_files/bootstrap.sh','bootstrap.sh')
    ftp_client.put('remote_files/run.sh','run.sh')
    
    # change to run dir
    ftp_client.chdir(run_path)
    if 'run_script' in config and config['run_script']:
        filename = os.path.basename(config['run_script'])
        ftp_client.put(config['run_script'],filename)
    if 'upload_files' in config and config['upload_files'] is not None:
        if isinstance( config['upload_files'],str):
            config['upload_files'] = [ config['upload_files']  ]
        for upfile in config['upload_files']:
            try:
                ftp_client.put(upfile,os.path.basename(upfile))
            except Exception as e:
                print("Error while uploading file",upfile)
                print(e)

    ftp_client.close()

    debug(1,"uploaded.")

    if created:
        debug(1,"Installing PyYAML for newly created instance ...")
        stdin , stdout, stderr = ssh_client.exec_command("pip install pyyaml")
        debug(2,stdout.read())
        debug(2, "Errors")
        debug(2,stderr.read())

    # run
    commands = [ 
        # make bootstrap executable
        { 'cmd': "chmod +x "+files_path+"/bootstrap.sh"+" "+files_path+"/run.sh" , 'out' : True },  
        # recreate pip+conda files according to config
        { 'cmd': "cd " + files_path + " && python3 "+files_path+"/config.py" , 'out' : True },
        # setup envs according to current config files state
        { 'cmd': files_path+"/bootstrap.sh \"" + env_obj['name'] + "\" " + ("1" if config['dev'] else "0") , 'out': True },  
        # execute main script (spawn)
        { 'cmd': files_path+"/run.sh \"" + env_obj['name'] + "\" \""+script_command+"\" " + config['input_file'] + " " + config['output_file']+" "+run_hash, 'out' : False }                    
    ]
    for command in commands:
        debug(1,"Executing ",format( command['cmd'] ) )
        try:
            stdin , stdout, stderr = ssh_client.exec_command(command['cmd'])
            #print(stdout.read())
            if command['out']:
                for l in line_buffered(stdout):
                    debug(1,l)
                errmsg = stderr.read()
                dbglvl = 1 if errmsg else 2
                debug(dbglvl,"Errors")
                debug(dbglvl,errmsg)
            else:
                pid = int(stdout.read().strip().decode("utf-8"))
                print("PID =",pid)
        except paramiko.ssh_exception.SSHException as sshe:
            print("The SSH Client has been disconnected!")
            print(sshe)
            # TODO: handle re-trys etc.... 

    ssh_client.close()

    # make sure we stop the instance to avoid charges !
    #stop_instance(instance)

    return instance , run_hash , pid    