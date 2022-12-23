import boto3
import os , sys
from .utils import *
from cloudsend.core     import CloudSendError , CloudSendInstance , CloudSendInstanceState , CloudSendPlatform
from cloudsend.core     import cs_keypairName , cs_secGroupName , cs_secGroupNameMaestro , cs_bucketName , cs_vpcName , cs_maestroRoleName , cs_maestroProfileName, cs_maestroPolicyName , init_instance_name
from cloudsend.provider import debug
from cloudsend.providerfat import CloudSendFatProvider
from cloudsend.providerlight import CloudSendLightProvider
from botocore.exceptions import ClientError
from datetime import datetime , timedelta
from botocore.config import Config
from datetime import datetime
from dateutil.relativedelta import relativedelta
import asyncio

def aws_get_session(profile_name , region ):
    if profile_name and region:
        return boto3.session.Session( profile_name = profile_name , region_name = region )
    elif profile_name:
        return boto3.session.Session( profile_name = profile_name )
    elif region:
        return boto3.session.Session( region_name = region )
    else:
        return boto3.session.Session()

# def aws_get_config(region):
#     # it's best we create a session every time wihin the threads ...
#     if region is None:
#         return Config()
#     else:
#         return Config(region_name=region)

def aws_get_region(profile_name=None):
    if profile_name:
        my_session = boto3.session.Session(profile_name=profile_name)
    else:
        my_session = boto3.session.Session()
    region = my_session.region_name     
    return region  

def aws_get_account_id(profile_name=None):
    client = boto3.client("sts")
    return client.get_caller_identity()["Account"]   

def aws_retrieve_keypair(session,region,keypair_name,key_filename):
    debug(1,"Retrieving KEYPAIR ...")
    ec2_client = session.client("ec2")
    ec2 = session.resource('ec2')

    try:
        keypairs = ec2_client.describe_key_pairs(KeyNames=[keypair_name])
    except ClientError as e:
        errmsg = str(e)
        if 'InvalidKeyPair.NotFound' in errmsg:
            keypair , kcreated = aws_create_keypair(session,region,keypair_name,key_filename)
            return kcreated # created

    # delete / create instead ... 
    # ISSUE: this will invalidate clients on other computers ... 
    ec2_client.delete_key_pair(KeyName=keypair_name,KeyPairId=keypairs['KeyPairs'][0]['KeyPairId'])
    keypair , kcreated = aws_create_keypair(session,region,keypair_name,key_filename)
    return kcreated

    # this is sadly not working: ec2.KeyPair returns a KeyPairInfo and not a KeyPair ... :/
    # TODO: make code commented below work
    #
    # keypair = ec2.KeyPair(keypair_name)
    # fpath   = key_filename
    # pemfile = open(fpath, "w")
    # pemfile.write(keypair.key_material) # save the private key in the directory (we will use it with SSH client)
    # pemfile.close()
    # os.chmod(fpath, 0o600) # change permission to use with ssh (for debugging)

    return False 

def aws_create_keypair(session,region,keypair_name,key_filename):
    debug(1,"Creating KEYPAIR ...")
    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2",config=aws_get_config(region))
    ec2 = session.resource('ec2')
    #ec2 = boto3.resource('ec2',config=aws_get_config(region))

    #keypair_name = cs_keypairName + '-' + region

    if not os.path.exists(key_filename):
        debug(1,"Key not found locally. Resetting remote KeyPair first",keypair_name,key_filename)
        try:
            keypairs = ec2_client.describe_key_pairs(KeyNames=[keypair_name])
            ec2_client.delete_key_pair(KeyName=keypair_name,KeyPairId=keypairs['KeyPairs'][0]['KeyPairId'])
        except ClientError as e:
            errmsg = str(e)
            if 'InvalidKeyPair.NotFound' in errmsg:
                debug(1,"KeyPair not existing remotely. All good.",keypair_name)
        except Exception as ee:
            pass

    keypair = None
    created = False
    try:
        keypair = ec2_client.create_key_pair(
            KeyName=keypair_name,
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
            raise CloudSendError()

        elif 'DryRunOperation' in errmsg: # we are good with credentials
            try :
                keypair = ec2_client.create_key_pair(
                    KeyName=keypair_name,
                    DryRun=False,
                    KeyType='rsa',
                    KeyFormat='pem'
                )
                #if region is None:
                    # get the default user region so we know what were getting ... (if it changes later etc... could be a mess)
                #    my_session = boto3.session.Session()
                #    region = my_session.region_name                
                fpath   = key_filename
                pemfile = open(fpath, "w")
                pemfile.write(keypair['KeyMaterial']) # save the private key in the directory (we will use it with SSH client)
                pemfile.close()
                os.chmod(fpath, 0o600) # change permission to use with ssh (for debugging)
                debug(2,keypair)
                created = True

            except ClientError as e2: # the keypair probably exists already
                errmsg2 = str(e2)
                if 'InvalidKeyPair.Duplicate' in errmsg2:
                    #keypair = ec2.KeyPair(cs_keypairName)
                    keypairs = ec2_client.describe_key_pairs( KeyNames= [keypair_name] )
                    keypair  = keypairs['KeyPairs'][0] 
                    debug(2,keypair)
                    created = False
                else:
                    debug(1,"An unknown error occured while retrieving the KeyPair")
                    debug(2,errmsg2)
                    #sys.exit()
                    created = False
                    raise CloudSendError()
        else:
            debug(1,"An unknown error occured while creating the KeyPair")
            debug(2,errmsg)
            #sys.exit()
            created = False
            raise CloudSendError()
    
    return keypair , created 

def aws_find_or_create_default_vpc(session,region):
    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2", config=aws_get_config(region))
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

def aws_create_vpc(session,region,cloudId=None):
    debug(1,"Creating VPC ...")
    vpc = None
    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2", config=aws_get_config(region))

    if cloudId is not None:
        vpcID = cloudId
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
                vpc = aws_find_or_create_default_vpc(session,region) 
            else:
                debug(1,"WARNING: using default VPC. Unknown error")
                vpc = aws_find_or_create_default_vpc(session,region) 

    else:
        debug(1,"using default VPC (no VPC ID specified in config)")
        vpc = aws_find_or_create_default_vpc(session,region)
    debug(2,vpc)

    return vpc 

def aws_create_security_group(session,region,vpc):
    debug(1,"Creating SECURITY GROUP ...")
    secGroup = None
    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2", config=aws_get_config(region))

    secgroups = ec2_client.describe_security_groups(Filters=[
        {
            'Name': 'group-name',
            'Values': [
                cs_secGroupName,
            ]
        },
    ])
    if len(secgroups['SecurityGroups']) == 0: # we have no security group, lets create one
        debug(1,"Creating new security group")
        secGroup = ec2_client.create_security_group(
            VpcId = vpc['VpcId'] ,
            Description = 'Allow SSH connection' ,
            GroupName = cs_secGroupName 
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
        debug(3,'Ingress Successfully Set %s' % data)

    else:
        secGroup = secgroups['SecurityGroups'][0]
    
    if secGroup is None:
        debug(1,"An unknown error occured while creating the security group")
        #sys.exit()
        raise CloudSendError()
    
    debug(2,secGroup) 

    return secGroup

def aws_add_maestro_security_group(session,instance):
    
    region = instance.get_region()
    vpcid  = instance.get_data('VpcId')

    debug(1,"Creating MAESTRO SECURITY GROUP ...")
    secGroup = None
    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2", config=aws_get_config(region))

    secgroups = ec2_client.describe_security_groups(Filters=[
        {
            'Name': 'group-name',
            'Values': [
                cs_secGroupNameMaestro,
            ]
        },
    ])
    if len(secgroups['SecurityGroups']) == 0: # we have no security group, lets create one
        debug(1,"Creating new security group")
        secGroup = ec2_client.create_security_group(
            VpcId = vpcid ,
            Description = 'Allow Maestro Socket connection' ,
            GroupName = cs_secGroupNameMaestro 
        )

        data = ec2_client.authorize_security_group_ingress(
            GroupId=secGroup['GroupId'],
            IpPermissions=[
                {'IpProtocol': 'tcp',
                'FromPort': 5000,
                'ToPort': 5000,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ])
        debug(3,'Ingress Successfully Set %s' % data)

    else:
        secGroup = secgroups['SecurityGroups'][0]
    
    if secGroup is None:
        debug(1,"An unknown error occured while creating the security group")
        #sys.exit()
        raise CloudSendError()
    
    debug(2,secGroup) 

    #ec2_objs = boto3.resource('ec2',config=aws_get_config(region))
    ec2_objs = session.resource('ec2')
    instance_aws = ec2_objs.Instance(instance.get_id())
    all_sg_ids = [sg['GroupId'] for sg in instance_aws.security_groups]  # Get a list of ids of all securify groups attached to the instance
    if secGroup['GroupId'] not in all_sg_ids:                        # Check the SG to be removed is in the list
       all_sg_ids.append(secGroup['GroupId'])                        # Adds the SG from the list
       instance_aws.modify_attribute(Groups=all_sg_ids)                  # Attach the remaining SGs to the instance

    return secGroup    

# for now just return the first subnet present in the Vpc ...
def aws_create_subnet(session,region,vpc):
    debug(1,"Creating SUBNET ...")
    ec2 = session.resource('ec2')
    #ec2 = boto3.resource('ec2',config=aws_get_config(region))
    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2", config=aws_get_config(region))
    vpc_obj = ec2.Vpc(vpc['VpcId'])
    for subnet in vpc_obj.subnets.all():
        subnets = ec2_client.describe_subnets(SubnetIds=[subnet.id])
        subnet = subnets['Subnets'][0]
        debug(2,subnet)
        return subnet
    return None # todo: create a subnet

def aws_create_bucket(session,region):

    debug(1,"Creating BUCKET ...")
    s3_client = session.client('s3')
    #s3_client = boto3.client('s3', config=aws_get_config(region))
    s3 = session.resource('s3')
    #s3 = boto3.resource('s3', config=aws_get_config(region))

    try :

        bucket = s3_client.create_bucket(
            ACL='private',
            Bucket=cs_bucketName,
            CreateBucketConfiguration={
                'LocationConstraint': region
            },

        )

    except ClientError as e:
        errMsg = str(e)
        if 'BucketAlreadyExists' in errMsg:
            bucket = s3.Bucket(cs_bucketName)
        elif 'BucketAlreadyOwnedByYou' in errMsg:
            bucket = s3.Bucket(cs_bucketName)

    debug(2,bucket)

    return bucket 


def aws_upload_file( session , region , bucket , file_path ):
    debug(1,"uploading FILE ...")
    s3_client = session.client('s3')
    #s3_client = boto3.client('s3', config=aws_get_config(region))
    response = s3_client.upload_file( file_path, bucket['BucketName'], 'cr-run-script' )
    debug(2,response)

def aws_find_instance(session,instance_config):

    instanceName = init_instance_name(instance_config)
    region = instance_config.get('region')

    debug(1,"Searching INSTANCE",instanceName,"...")

    #ec2_client = boto3.client("ec2", config=aws_get_config(region))
    ec2_client = session.client("ec2")

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
        instance_data = existing['Reservations'][0]['Instances'][0]
        debug(1,"Found existing instance !",instance_data['InstanceId'],instanceName)
        debug(3,instance_data)
        instance = CloudSendInstance( instance_config , instance_data['InstanceId'] , instance_data )
        return instance 
    
    else:

        debug(1,"not found")

        return None 


def aws_create_instance(session,instance_config,vpc,subnet,secGroup,keypair_name):

    debug(1,"Creating INSTANCE ...")

    instanceName = init_instance_name(instance_config)

    region = instance_config.get('region')

    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2", config=aws_get_config(region))

    #keypair_name = cs_keypairName + '-' + region

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

    created = False

    if len(existing['Reservations']) > 0 and len(existing['Reservations'][0]['Instances']) >0 :
        instance_data = existing['Reservations'][0]['Instances'][0]
        debug(1,"Found existing instance !",instance_data['InstanceId'])
        debug(3,instance_data)
        instance = CloudSendInstance( instance_config, instance_data['InstanceId'] , instance_data )
        return instance , created

    if instance_config.get('cpus') is not None:
        cpus_spec = {
            'CoreCount': instance_config['cpus'],
            'ThreadsPerCore': 1
        }
    else:
        cpus_spec = { }  

    if instance_config.get('gpu'):
        gpu_spec = [ { 'Type' : instance_config['gpu'] } ]
    else:
        gpu_spec = [ ]
    
    if instance_config.get('eco') :
        market_options = {
            'MarketType': 'spot',
            'SpotOptions': {
                'SpotInstanceType': 'one-time', #one-time'|'persistent',
                'InstanceInterruptionBehavior': 'terminate' #'hibernate'|'stop'|'terminate'
            }
        }     
        if 'eco_life' in instance_config and isinstance(instance_config['eco_life'],timedelta):
            validuntil = datetime.today() + instance_config['eco_life']
            market_options['SpotOptions']['ValidUntil'] = validuntil
        if 'max_bid' in instance_config and isinstance(instance_config['max_bid'],str):
            market_options['SpotOptions']['MaxPrice'] = instance_config['max_bid']
    else:
        market_options = { } 

    if instance_config.get('disk_size'):
        #TODO: improve selection of disk_type
        disk_size = instance_config['disk_size']
        if disk_size < 1024:
            volume_type = 'standard'
        else:
            volume_type = 'st1' # sc1, io1, io2, gp2, gp3
        if 'disk_type' in instance_config and instance_config['disk_type']:
            volume_type = instance_config['disk_type']
        block_device_mapping = [
            {
                'DeviceName' : '/dev/sda' ,
                'Ebs' : {
                    "DeleteOnTermination" : True ,
                    "VolumeSize": disk_size ,
                    "VolumeType": volume_type
                }
            }
        ]
    else:
        block_device_mapping = [ ]

    try:
        instances = ec2_client.run_instances(
                ImageId = instance_config['img_id'],
                MinCount = 1,
                MaxCount = 1,
                InstanceType = instance_config['type'],
                KeyName = keypair_name,
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
    except ClientError as ce:
        errmsg = str(ce)
        if 'InsufficientInstanceCapacity' in errmsg: # Amazon doesnt have enough resources at the moment
            debug(1,"AWS doesnt have enough SPOT resources at the moment, retrying in 2 minutes ...",errmsg)
        elif 'InvalidAMIID.Malformed' in errmsg:
            debug(1,errmsg,color=bcolors.FAIL)
            images = ec2_client.describe_images(Filters=[{'Name':'name','Values':['*Ubuntu*']}]) #Owners=['self'])
            for image in images['Images']:
                debug(1,"{0} - {1}".format(image['ImageId'],image['Name']))
            sys.exit()
        elif 'InvalidAMIID.NotFound' in errmsg:
            debug(1,errmsg,color=bcolors.FAIL)
            images = ec2_client.describe_images(Filters=[{'Name':'name','Values':['*Ubuntu*']}]) #Owners=['self'])
            for image in images['Images']:
                debug(1,"{0} - {1}".format(image['ImageId'],image['Name']))
            sys.exit()
        else:
            debug(1,"An error occured while trying to create this instance",errmsg)
        raise CloudSendError()


    created = True

    debug(2,instances["Instances"][0])

    instance = CloudSendInstance( instance_config, instances["Instances"][0]["InstanceId"] , instances["Instances"][0] )

    return instance , created

def aws_create_instance_objects(session,instance_config,keypair_name,key_filename):
    region   = instance_config.get('region')
    keypair , kcreated = aws_create_keypair(session,region,keypair_name,key_filename)
    vpc      = aws_create_vpc(session,region,instance_config.get('cloud_id')) 
    secGroup = aws_create_security_group(session,region,vpc)
    subnet   = aws_create_subnet(session,region,vpc) 
    # this is where all the instance_config is actually used
    instance , created = aws_create_instance(session,instance_config,vpc,subnet,secGroup,keypair_name)

    return instance , created 


def aws_start_instance(session,instance):
    region  = instance.get_region()
    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2", config=aws_get_config(instance.get_region()))

    try:
        ec2_client.start_instances(InstanceIds=[instance.get_id()])
    except ClientError as botoerr:
        errmsg = str(botoerr)
        if 'IncorrectSpotRequestState' in errmsg:
            debug(1,"Could not start because it is a SPOT instance, waiting on SPOT ...",errmsg)
            # try reboot
            try:
                ec2_client.reboot_instances(InstanceIds=[instance.get_id()])
            except ClientError as botoerr2:
                errmsg2 = str(botoerr2)
                if 'IncorrectSpotRequestState' in errmsg2:
                    debug(1,"Could not reboot instance because of SPOT ... ",errmsg2)
                    raise CloudSendError()
                    # terminate_instance(config,instance)
                
        else:
            debug(2,botoerr)
            raise CloudSendError()

def aws_stop_instance(session,instance):
    region  = instance.get_region()
    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2", config=aws_get_config(instance.get_region()))

    ec2_client.stop_instances(InstanceIds=[instance.get_id()])

def aws_terminate_instance(session,instance):
    region  = instance.get_region()
    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2", config=aws_get_config(instance.get_region()))

    ec2_client.terminate_instances(InstanceIds=[instance.get_id()])

    if instance.get_data('SpotInstanceRequestId'):

        ec2_client.cancel_spot_instance_requests(SpotInstanceRequestIds=[instance.get_data('SpotInstanceRequestId')]) 

def aws_reboot_instance(session,instance):
    region  = instance.get_region()
    ec2_client = session.client("ec2")
    #ec2_client = boto3.client("ec2", config=aws_get_config(instance.get_region()))

    ec2_client.reboot_instances(InstanceIds=[instance.get_id()],)


def aws_update_instance_info(session,instance):
    region = instance.get_region()
    #ec2_client   = boto3.client("ec2", config=aws_get_config(region))
    ec2_client = session.client("ec2")
    instances    = ec2_client.describe_instances( InstanceIds=[instance.get_id()] )
    instance_new_data = instances['Reservations'][0]['Instances'][0]

    debug(3,instance_new_data)

    #instance = CloudSendInstance( region , instance.get_name() , instance.get_id() , instance_config, instance_new )
    # proprietary values
    instance.set_dns_addr(instance_new_data.get('PublicDnsName'))
    instance.set_ip_addr(instance_new_data.get('PublicIpAddress'))
    instance.set_dns_addr_priv(instance_new_data.get('PrivateDnsName'))
    instance.set_ip_addr_priv(instance_new_data.get('PrivateIpAddress'))
    statestr = instance_new_data.get('State').get('Name').lower()
    #'terminated' | 'shutting-down' | 'pending' | 'running' | 'stopping' | 'stopped'
    state = CloudSendInstanceState.UNKNOWN
    if statestr == "pending":
        state = CloudSendInstanceState.STARTING
    elif statestr == "running":
        state = CloudSendInstanceState.RUNNING
    elif statestr == 'stopping':
        state = CloudSendInstanceState.STOPPING
    elif statestr == 'stopped':
        state = CloudSendInstanceState.STOPPED
    elif statestr == 'shutting-down':
        state = CloudSendInstanceState.TERMINATING
    elif statestr == 'terminated':
        state = CloudSendInstanceState.TERMINATED
    instance.set_state(state)
    instance.set_data(instance_new_data)
    instance.set_reachability(False)

    # check further status
    if state == CloudSendInstanceState.RUNNING:
        status_res = ec2_client.describe_instance_status( InstanceIds=[instance.get_id()] )
        status_res = status_res['InstanceStatuses'][0]
        if status_res['InstanceStatus']['Status'] == 'ok' and status_res['SystemStatus']['Status'] == 'ok':
             instance.set_reachability(True)

    platform_details = instance_new_data.get('PlatformDetails').lower()
    if 'linux' in platform_details:
        instance.set_platform(CloudSendPlatform.LINUX)
    elif 'windows' in platform_details:
        instance.set_platform(CloudSendPlatform.WINDOWS_WSL)

    return instance


def aws_grant_admin_rights(session,instance):
    region = instance.get_region()
    iam_client = session.client('iam')
    #iam_client = boto3.client('iam', config=aws_get_config(region))
    id_client = session.client('sts')
    #id_client  = boto3.client("sts", config=aws_get_config(region))
    ec2_client = session.client('ec2')
    #ec2_client = boto3.client("ec2", config=aws_get_config(region))
    
    account_id = id_client.get_caller_identity()["Account"]
    #session    = boto3.session.Session()
    #region_flt = session.region_name if not region else region

    #Following trust relationship policy can be used to provide access to assume this role by a particular AWS service in the same account
    trust_relationship_policy_another_aws_service = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "ec2.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }

    try:
        create_role_res = iam_client.create_role(
            RoleName=cs_maestroRoleName,
            AssumeRolePolicyDocument=json.dumps(trust_relationship_policy_another_aws_service),
            Description='CloudSend Admin Role'
        )
    except ClientError as error:
        if error.response['Error']['Code'] == 'EntityAlreadyExists':
            debug(2,'Role already exists ...')
        else:
            debug(1,'Unexpected error occurred... Role could not be created', error)
            return
            
    policy_json = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "ec2:*"
            ],
            "Resource": "*",
            # "Condition": {
            #     "StringEquals": {
            #          "ec2:Region": region_flt
            #     }
            # }
        }]
    }

    policy_arn = ''

    try:
        policy_res = iam_client.create_policy(
            PolicyName=cs_maestroPolicyName,
            PolicyDocument=json.dumps(policy_json)
        )
        policy_arn = policy_res['Policy']['Arn']
    except ClientError as error:
        if error.response['Error']['Code'] == 'EntityAlreadyExists':
            debug(2,'Policy already exists... hence using the same policy')
            policy_arn = 'arn:aws:iam::' + account_id + ':policy/' + cs_maestroPolicyName
        else:
            debug(1,'Unexpected error occurred... hence cleaning up', error)
            iam_client.delete_role(
                RoleName= cs_maestroRoleName
            )
            debug(1,'Role could not be created...', error)
            return

    try:
        policy_attach_res = iam_client.attach_role_policy(
            RoleName=cs_maestroRoleName,
            PolicyArn=policy_arn
        )
    except ClientError as error:
        debug(1,'Unexpected error occurred... hence cleaning up')
        iam_client.delete_role(
            RoleName= cs_maestroRoleName
        )
        debug(1,'Role could not be created...', error)
        return

    debug(2,'Role {0} successfully got created'.format(cs_maestroRoleName))


    profile_arn = ''
    try:
        profile_response = iam_client.create_instance_profile(InstanceProfileName=cs_maestroProfileName)
        profile_arn = profile_response['InstanceProfile']['Arn']
    except ClientError as error:
        if error.response['Error']['Code'] == 'EntityAlreadyExists':
            debug(2,'Instance profile already exists ...')
            profile_response = iam_client.get_instance_profile(InstanceProfileName=cs_maestroProfileName)
            profile_arn = profile_response['InstanceProfile']['Arn']
    try:
        iam_client.add_role_to_instance_profile(InstanceProfileName=cs_maestroProfileName,RoleName=cs_maestroRoleName)
    except ClientError as error:
        if error.response['Error']['Code'] == 'LimitExceeded':
            debug(2,'Role has already been added ...')
        else:
            debug(1,error)
            return

    try:
        response = ec2_client.associate_iam_instance_profile(
            IamInstanceProfile={
                'Arn': profile_arn,
                'Name': cs_maestroProfileName
            },
            InstanceId=instance.get_id()
        )
    except ClientError as error:
        if error.response['Error']['Code'] == 'IncorrectState':
            debug(2,'Instance Profile already associated ...')
        else:
            debug(1,error)

    debug(1,"MAESTRO role added to instance",instance.get_id(),instance.get_name())


def aws_setup_auto_stop(session,instance):
    ec2_client = session.client("ec2")
    ec2_client.modify_instance_attribute(
        InstanceId=instance.get_id(),
        InstanceInitiatedShutdownBehavior={
            'Value': 'stop'
        }
    )

def aws_get_suggested_image(session,region):
    ec2_client = session.client("ec2")

    debug(2,'Getting suggested image ID')

    flt_creation = []
    for month in range(1):
        date_x_months_ago = datetime.now() - relativedelta(months=month)
        flt = str(date_x_months_ago.year) + '-' + str(date_x_months_ago.month) + '*'
        flt_creation.append(flt)
    

    results = ec2_client.describe_images(
        Filters=
        [
            {'Name':'name','Values':['AWS Deep Learning*Ubuntu*']} ,
#            {'Name':'is-public','Values':['true']} ,
#            {'Name':'architecture','Values':['x86_64']},
            {'Name':'creation-date','Values':flt_creation}
        ],
        Owners=['self','amazon']
    )
    images = results['Images']

    images = sorted(images, key=lambda d: d['Name']) 

    for image in images:
        debug(2,image['Name'],image['Description'])
    
    images = sorted(images, key=lambda d: d['CreationDate']) 

    if images and len(images)>0:
        return images[len(images)-1]['ImageId'] , 'ubuntu' , 't2.micro' # nano: pip gets killed :(

##########
# PUBLIC #
##########

class AWSCloudSendProviderImpl():

    def find_instance(self,config):
        session = self.get_session(config)
        return aws_find_instance(session,config)

    def update_instance_info(self,instance):
        session = self.get_session(instance)
        aws_update_instance_info(session,instance)

    def retrieve_keypair(self,region):
        keypair_name = self.get_keypair_name(self._profile_name,region)
        key_filename = self.get_key_filename(self._profile_name,region)
        session = self.get_session(region)
        return aws_retrieve_keypair(session,region,keypair_name,key_filename)

    def create_keypair(self,region):
        keypair_name = self.get_keypair_name(self._profile_name,region)
        key_filename = self.get_key_filename(self._profile_name,region)
        session = self.get_session(region)
        keypair , kcreated = aws_create_keypair(session,region,keypair_name,key_filename)
        return kcreated

    def create_instance_objects(self,config):
        keypair_name = self.get_keypair_name(self._profile_name,config.get('region'))
        key_filename = self.get_key_filename(self._profile_name,config.get('region'))
        session = self.get_session(config)
        return aws_create_instance_objects(session,config,keypair_name,key_filename)

    def start_instance(self,instance):
        session = self.get_session(instance)
        aws_start_instance(session,instance)

    def stop_instance(self,instance):
        session = self.get_session(instance)
        aws_stop_instance(session,instance)

    def terminate_instance(self,instance):
        session = self.get_session(instance)
        aws_terminate_instance(session,instance)

    def reboot_instance(self,instance):
        session = self.get_session(instance)
        aws_reboot_instance(session,instance)

    def get_region(self):
        return aws_get_region(self._profile_name)
    
    def get_account_id(self):
        return aws_get_account_id(self._profile_name)

    def set_profile(self,profile_name):
        boto3.setup_default_session(profile_name=profile_name)

    def get_suggested_image(self,region):
        session = self.get_session(region)
        return aws_get_suggested_image(session,region)

    def get_session(self,obj):
        if isinstance(obj,dict):
            region = obj.get('region')
        elif isinstance(obj,str):
            region = obj
        else:
            region = obj.get_region()
        return aws_get_session(self._profile_name,region)        


class AWSCloudSendFatProvider(CloudSendFatProvider,AWSCloudSendProviderImpl):

    def __init__(self, conf):
        CloudSendFatProvider.__init__(self,conf)

    def find_instance(self,config):
        return AWSCloudSendProviderImpl.find_instance(self,config)

    def update_instance_info(self,instance):
        AWSCloudSendProviderImpl.update_instance_info(self,instance)

    def retrieve_keypair(self,region):
        return AWSCloudSendProviderImpl.retrieve_keypair(self,region)

    def create_keypair(self,region):
        return AWSCloudSendProviderImpl.create_keypair(self,region)

    def create_instance_objects(self,config):
        return AWSCloudSendProviderImpl.create_instance_objects(self,config)

    def start_instance(self,instance):
        AWSCloudSendProviderImpl.start_instance(self,instance)

    def stop_instance(self,instance):
        AWSCloudSendProviderImpl.stop_instance(self,instance)

    def terminate_instance(self,instance):
        AWSCloudSendProviderImpl.terminate_instance(self,instance)

    def reboot_instance(self,instance):
        AWSCloudSendProviderImpl.reboot_instance(self,instance)

    def get_region(self):
        return AWSCloudSendProviderImpl.get_region(self)
    
    def get_account_id(self):
        return AWSCloudSendProviderImpl.get_account_id(self)

    def set_profile(self,profile_name):
        AWSCloudSendProviderImpl.set_profile(self,profile_name)     

    def get_suggested_image(self,region):
        return AWSCloudSendProviderImpl.get_suggested_image(self,region)

    def get_recommended_cpus(self,inst_cfg):
        return self._get_instancetypes_attribute(inst_cfg,"instancetypes-aws.csv","Instance type","Valid cores",list)

    def get_cpus_cores(self,inst_cfg):
        return self._get_instancetypes_attribute(inst_cfg,"instancetypes-aws.csv","Instance type","Cores",int)


class AWSCloudSendLightProvider(CloudSendLightProvider,AWSCloudSendProviderImpl):        

    def __init__(self, conf):
        CloudSendLightProvider.__init__(self,conf)

    def find_instance(self,config):
        return AWSCloudSendProviderImpl.find_instance(self,config)

    def update_instance_info(self,instance):
        AWSCloudSendProviderImpl.update_instance_info(self,instance)

    def retrieve_keypair(self,region):
        return AWSCloudSendProviderImpl.retrieve_keypair(self,region)

    def create_keypair(self,region):
        return AWSCloudSendProviderImpl.create_keypair(self,region)

    def create_instance_objects(self,config):
        return AWSCloudSendProviderImpl.create_instance_objects(self,config)

    def start_instance(self,instance):
        AWSCloudSendProviderImpl.start_instance(self,instance)

    def stop_instance(self,instance):
        AWSCloudSendProviderImpl.stop_instance(self,instance)

    def terminate_instance(self,instance):
        AWSCloudSendProviderImpl.terminate_instance(self,instance)

    def reboot_instance(self,instance):
        AWSCloudSendProviderImpl.reboot_instance(self,instance)

    def get_region(self):
        return AWSCloudSendProviderImpl.get_region(self)
    
    def get_account_id(self):
        return AWSCloudSendProviderImpl.get_account_id(self)

    def set_profile(self,profile_name):
        AWSCloudSendProviderImpl.set_profile(self,profile_name)   

    def get_suggested_image(self,region):
        return AWSCloudSendProviderImpl.get_suggested_image(self,region)

    def grant_admin_rights(self,instance):
        session = self.get_session(instance)
        aws_grant_admin_rights(session,instance)   

    def add_maestro_security_group(self,instance):
        session = self.get_session(instance)
        aws_add_maestro_security_group(session,instance)

    def setup_auto_stop(self,instance):
        session = self.get_session(instance)
        aws_setup_auto_stop(session,instance)