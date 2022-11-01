import boto3
import time , os , json
import cloudrunutils
import paramiko
from botocore.exceptions import ClientError

config = {
    'project'      : 'test' ,                  # this will be concatenated in the hash (if not None) 
    'dev'          : False ,                    # When True, this will ensure the same instance and dev environement are being used (while working on building up the project) 

    # "instance" section
    'vpc_id'       : 'vpc-0babc28485f6730bc' , # can be None, or even wrong/non-existing - then the default one is used
    'region'       : 'eu-west-3' ,             # has to be valid
    'ami_id'       : 'ami-077fd75cd229c811b' , # has to be valid and available for the profile (user/region)
    'min_cpu'      : None ,                    # number of min CPUs (not used yet)
    'max_cpu'      : None ,                    # number of max CPUs (not used yet)
    'max_bid'      : None ,                    # max bid ($) (not used yet)
    'size'         : None ,                    # size (ECO = SPOT , SMALL , MEDIUM , LARGE) (not used yet)
    'username'     : 'ubuntu' ,                # the SSH use for the image

    # "environment" section
    'env_aptget'   : None ,                    # None, an array of librarires/binaries for apt-get
    'env_conda'    : "environment_example.yml" ,                    # None, an array of libraries, a path to environment.yml  file, or a path to the root of a conda environment
    'env_pypi'     : "requirements.txt" ,      # None, an array of libraries, a path to requirements.txt file, or a path to the root of a venv environment 

    # "script" section
    'script_file'  : 'run_remote.py' ,         # the script to run (Python (.py) or Julia (.jl) for now)
}

cr_keypairName         = 'cloudrun-keypair'
cr_secGroupName        = 'cloudrun-sec-group-allow-ssh'
cr_bucketName          = 'cloudrun-bucket'
cr_instanceNameRoot    = 'cloudrun-instance'
cr_environmentNameRoot = 'cloudrun-env'

class CloudRunError(Exception):
    pass

def create_keypair():
    print("Creating KeyPair ...")
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
            print("The account is not authorized to create a keypair, please specify an existing keypair in the configuration or add Administrator privileges to the account")
            keypair = None
            #sys.exit()
            raise CloudRunError()

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
                print(keypair)

            except ClientError as e2: # the keypair probably exists already
                errmsg2 = str(e2)
                if 'InvalidKeyPair.Duplicate' in errmsg2:
                    #keypair = ec2.KeyPair(cr_keypairName)
                    keypairs = ec2_client.describe_key_pairs( KeyNames= [cr_keypairName] )
                    keypair  = keypairs['KeyPairs'][0] 
                    print(keypair)
                else:
                    print("An unknown error occured while retrieving the KeyPair")
                    print(errmsg2)
                    #sys.exit()
                    raise CloudRunError()

        
        else:
            print("An unknown error occured while creating the KeyPair")
            print(errmsg)
            #sys.exit()
            raise CloudRunError()
    
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

def create_vpc():
    print("Creating VPC ...")
    vpc = None
    ec2_client = boto3.client("ec2", region_name=config['region'])

    if 'vpc_id' in config:
        vpcID = config['vpc_id']
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
                print("WARNING: using default VPC. "+vpcID+" is unavailable")
                vpc = find_or_create_default_vpc() 
            else:
                print("WARNING: using default VPC. Unknown error")
                vpc = find_or_create_default_vpc() 

    else:
        print("using default VPC (no VPC ID specified in config)")
        vpc = find_or_create_default_vpc()
    print(vpc)

    return vpc 

def create_security_group(vpc):
    print("Creating SECURITY GROUP ...")
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
        print("Creating new security group")
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
        print('Ingress Successfully Set %s' % data)

    else:
        secGroup = secgroups['SecurityGroups'][0]
    
    if secGroup is None:
        print("An unknown error occured while creating the security group")
        #sys.exit()
        raise CloudRunError()
    
    print(secGroup) 

    return secGroup

# for now just return the first subnet present in the Vpc ...
def create_subnet(vpc):
    print("Creating SUBNET ...")
    ec2 = boto3.resource('ec2')
    ec2_client = boto3.client("ec2", region_name=config['region'])
    vpc_obj = ec2.Vpc(vpc['VpcId'])
    for subnet in vpc_obj.subnets.all():
        subnets = ec2_client.describe_subnets(SubnetIds=[subnet.id])
        subnet = subnets['Subnets'][0]
        print(subnet)
        return subnet
    return None # todo: create a subnet

def create_bucket():

    print("Creating BUCKET ...")

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

    print(bucket)

    return bucket 


def upload_file( bucket , file_path ):
    print("Uploading FILE ...")
    s3_client = boto3.client('s3', region_name=config['region'])
    response = s3_client.upload_file( file_path, bucket['BucketName'], 'cr-run-script' )
    print(response)

def init_instance_name():
    if ('dev' in config) and (config['dev'] == True):
        return cr_instanceNameRoot
    else:
        instance_hash = cloudrunutils.compute_instance_hash(config)

        if 'project' in config:
            return cr_instanceNameRoot + '-' + config['project'] + '-' + instance_hash
        else:
            return cr_instanceNameRoot + '-' + instance_hash    

def create_instance(vpc,subnet,secGroup):

    print("Creating INSTANCE ...")

    instanceName = init_instance_name()

    ec2_client = boto3.client("ec2", region_name=config['region'])
    # instances = ec2_client.run_instances(
    #     ImageId=amiID,
    #     MinCount=1,
    #     MaxCount=1,
    #     InstanceType="t2.micro",
    #     KeyName=cr_keypairName,
    #     SubnetId='subnet-01c48bdbf5383d175'
    # )
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
        print("Found EXISTING !")
        print(instance)
        return instance , created

    instances = ec2_client.run_instances(
            ImageId = config['ami_id'],
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
    )    

    created = True

    print(instances["Instances"][0])

    return instances["Instances"][0] , created

def start_instance(instance):
    ec2_client = boto3.client("ec2", region_name=config['region'])

    ec2_client.start_instances(InstanceIds=[instance['InstanceId']])

def stop_instance(instance):
    ec2_client = boto3.client("ec2", region_name=config['region'])

    ec2_client.stop_instances(InstanceIds=[instance['InstanceId']])

def init_environment(conf):
    env_obj  = cloudrunutils.compute_environment_object(conf)
    env_hash = cloudrunutils.compute_environment_hash(env_obj)

    env_name = cr_instanceNameRoot

    if ('dev' in config) and (config['dev'] == True):
        env_name = cr_instanceNameRoot
    else:
        if 'project' in config:
            env_name = cr_environmentNameRoot + '-' + config['project'] + '-' + env_hash
        else:
            env_name = cr_environmentNameRoot + '-' + env_hash    

    # overwrite name in conda config as well
    if env_obj['env_conda'] is not None:
        env_obj['env_conda']['name'] = env_name 
    env_obj['name'] = env_name
    env_obj['hash'] = env_hash

    return env_obj 


def run_instance_script(vpc,subnet,secGroup,script):

    print("Creating INSTANCE ...")

    ec2_client = boto3.client("ec2", region_name=config['region'])

    instanceName = cr_instanceNameRoot

    instances = ec2_client.run_instances(
            ImageId = config['ami_id'],
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

    print(instances["Instances"][0])

    return instances["Instances"][0]    

def update_instance_info(instance):
    ec2_client   = boto3.client("ec2", region_name=config['region'])
    instances    = ec2_client.describe_instances( InstanceIds=[instance['InstanceId']] )
    instance_new = instances['Reservations'][0]['Instances'][0]
    return instance_new

def get_public_ip(instance_id):
    ec2_client = boto3.client("ec2", region_name=config['region'])
    reservations = ec2_client.describe_instances(InstanceIds=[instance_id]).get("Reservations")

    for reservation in reservations:
        for instance in reservation['Instances']:
            print(instance.get("PublicIpAddress"))    


def list_amis():
    ec2 = boto3.client('ec2', region_name=config['region'])
    response = ec2.describe_instances()
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            print(instance["ImageId"])

def line_buffered(f):
    line_buf = ""
    while not f.channel.exit_status_ready():
        try:
            line_buf += f.read(1).decode("utf-8")
            if line_buf.endswith('\n'):
                yield line_buf
                line_buf = ''
        except:
            pass

#######
#
# MAIN
#
#######

#print(json.dumps(cloudrunutils.compute_environment_object(config)))

keypair  = create_keypair()
vpc      = create_vpc() 
secGroup = create_security_group(vpc)
subnet   = create_subnet(vpc) 

# OPTION 1: with separate SSH command
if 1==1:
    instance , created = create_instance(vpc,subnet,secGroup)

    # get the public DNS info when instance actually started (todo: check actual state)
    waitFor = True
    while waitFor:
        updated_instance_info = update_instance_info(instance)
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
                print("waiting for DNS address + State ...",instanceState)
            else:
                print("waiting for State ...",instanceState)
            
            time.sleep(10)
    
    time.sleep(5) # avoids SSH connection error ?
    
    print(updated_instance_info)

    # init environment object
    env_obj = init_environment(config)
    print(json.dumps(env_obj))
    
    # ssh into instance and run the script from S3/local? (or sftp)
    k = paramiko.RSAKey.from_private_key_file('cloudrun.pem')
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print("connecting to ",updated_instance_info['PublicDnsName'],updated_instance_info['PublicIpAddress'])
    while True:
        try:
            ssh_client.connect(hostname=updated_instance_info['PublicDnsName'],username=config['username'],pkey=k) #,password=’mypassword’)
            break
        except paramiko.ssh_exception.NoValidConnectionsError as cexc:
            print(cexc)
            time.sleep(2)
            print("Retrying ...")

    print("connected")

    # upload the install file, the env file and the script file
    ftp_client = ssh_client.open_sftp()
    with open('remote_config.json','w') as cfg_file:
        cfg_file.write(json.dumps(env_obj))
        cfg_file.close()
        ftp_client.put('remote_config.json','config.json')
    ftp_client.put('bootstrap.sh','bootstrap.sh')
    ftp_client.put('config.py','config.py')
    ftp_client.put('run_remote.py','run_remote.py')
    ftp_client.close()

    if created:
        print("Installing PyYAML for newly created instance ...")
        stdin , stdout, stderr = ssh_client.exec_command("pip install pyyaml")
        print(stdout.read())
        print( "Errors")
        print(stderr.read())

    # run
    commands = [ 
        "chmod +x $HOME/bootstrap.sh" ,                               # make bootstrap executable
        "python3 $HOME/config.py",                                    # recreate pip+conda files according to config
#        "bash -l -c /home/ubuntu/bootstrap.sh " + env_obj['name'],
        "$HOME/bootstrap.sh " + env_obj['name'],                      # setup envs according to current config files state
#        "python3 $HOME/run_remote.py"                                 # execute main script
    ]
    for command in commands:
        print("Executing ",format( command ) )
        stdin , stdout, stderr = ssh_client.exec_command(command)
        #print(stdout.read())
        for l in line_buffered(stdout):
            print(l)
        print( "Errors")
        print(stderr.read())
    
    ssh_client.close()

    # make sure we stop the instance to avoid charges !
    # stop_instance(instance)

# OPTION 2: "execute and kill" mode (dont use)
else:
    with open(config['script_file'], 'r') as f:
        script = '\n'.join(f)    
        #TODO: add install scripts if needed (Julia etc)
        instance = run_instance_script(vpc,subnet,secGroup,script)
    
