import boto3
import os , json
import cloudrunutils
from cloudrun import CloudRunError , CloudRunCommandState , CloudRunInstance , CloudRunEnvironment , CloudRunScriptRuntimeInfo, CloudRunProvider
from cloudrun import cr_keypairName , cr_secGroupName , cr_bucketName , cr_vpcName , init_instance_name , init_environment
import paramiko
from botocore.exceptions import ClientError
from datetime import datetime , timedelta
from botocore.config import Config
import asyncio
import re

DBG_LVL = 1

def debug(level,*args):
    if level <= DBG_LVL:
        print(*args)

def get_config(region):
    if region is None:
        return Config()
    else:
        return Config(region_name=region)

def create_keypair(region):
    debug(1,"Creating KEYPAIR ...")
    ec2_client = boto3.client("ec2",config=get_config(region))
    ec2 = boto3.resource('ec2',config=get_config(region))

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
            raise CloudRunError()

        elif 'DryRunOperation' in errmsg: # we are good with credentials
            try :
                keypair = ec2_client.create_key_pair(
                    KeyName=cr_keypairName,
                    DryRun=False,
                    KeyType='rsa',
                    KeyFormat='pem'
                )
                fpath = "cloudrun-"+str(region)+".pem"
                pemfile = open(fpath, "w")
                pemfile.write(keypair['KeyMaterial']) # save the private key in the directory (we will use it with paramiko)
                pemfile.close()
                os.chmod(fpath, 0o600) # change permission to use with ssh (for debugging)
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
                    raise CloudRunError()

        
        else:
            debug(1,"An unknown error occured while creating the KeyPair")
            debug(2,errmsg)
            #sys.exit()
            raise CloudRunError()
    
    return keypair 

def find_or_create_default_vpc(region):
    ec2_client = boto3.client("ec2", config=get_config(region))
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

def create_vpc(region,cloudId=None):
    debug(1,"Creating VPC ...")
    vpc = None
    ec2_client = boto3.client("ec2", config=get_config(region))

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
                vpc = find_or_create_default_vpc(region) 
            else:
                debug(1,"WARNING: using default VPC. Unknown error")
                vpc = find_or_create_default_vpc(region) 

    else:
        debug(1,"using default VPC (no VPC ID specified in config)")
        vpc = find_or_create_default_vpc(region)
    debug(2,vpc)

    return vpc 

def create_security_group(region,vpc):
    debug(1,"Creating SECURITY GROUP ...")
    secGroup = None
    ec2_client = boto3.client("ec2", config=get_config(region))

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
        raise CloudRunError()
    
    debug(2,secGroup) 

    return secGroup

# for now just return the first subnet present in the Vpc ...
def create_subnet(region,vpc):
    debug(1,"Creating SUBNET ...")
    ec2 = boto3.resource('ec2',config=get_config(region))
    ec2_client = boto3.client("ec2", config=get_config(region))
    vpc_obj = ec2.Vpc(vpc['VpcId'])
    for subnet in vpc_obj.subnets.all():
        subnets = ec2_client.describe_subnets(SubnetIds=[subnet.id])
        subnet = subnets['Subnets'][0]
        debug(2,subnet)
        return subnet
    return None # todo: create a subnet

def create_bucket(region):

    debug(1,"Creating BUCKET ...")

    s3_client = boto3.client('s3', config=get_config(region))
    s3 = boto3.resource('s3', config=get_config(region))

    try :

        bucket = s3_client.create_bucket(
            ACL='private',
            Bucket=cr_bucketName,
            CreateBucketConfiguration={
                'LocationConstraint': region
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


def upload_file( region , bucket , file_path ):
    debug(1,"uploading FILE ...")
    s3_client = boto3.client('s3', config=get_config(region))
    response = s3_client.upload_file( file_path, bucket['BucketName'], 'cr-run-script' )
    debug(2,response)

def find_instance(instance_config):

    debug(1,"Searching INSTANCE ...")

    instanceName = init_instance_name(instance_config)
    region = instance_config['region']

    ec2_client = boto3.client("ec2", config=get_config(region))

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
        instance = CloudRunInstance( region , instanceName , instance['InstanceId'] , instance_config, instance )
        return instance 
    
    else:

        debug(1,"not found")

        return None 


def create_instance(instance_config,vpc,subnet,secGroup):

    debug(1,"Creating INSTANCE ...")

    instanceName = init_instance_name(instance_config)

    region = instance_config['region']

    ec2_client = boto3.client("ec2", config=get_config(region))

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
        instance = CloudRunInstance( region , instanceName , instance['InstanceId'] , instance_config, instance )
        return instance , created

    if instance_config.get('cpus') is not None:
        cpus_spec = {
            'CoreCount': instance_config['cpus'],
            'ThreadsPerCore': 1
        },
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
                'SpotInstanceType': 'persistent', #one-time'|'persistent',
                'InstanceInterruptionBehavior': 'stop' #'hibernate'|'stop'|'terminate'
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
                InstanceType = instance_config['size'],
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
    except ClientError as ce:
        errmsg = str(ce)
        if 'InsufficientInstanceCapacity' in errmsg: # Amazon doesnt have enough resources at the moment
            debug(1,"AWS doesnt have enough SPOT resources at the moment, retrying in 2 minutes ...",errmsg)
        else:
            debug(1,"An error occured while trying to create this instance",errmsg)
        raise CloudRunError()


    created = True

    debug(2,instances["Instances"][0])

    instance = CloudRunInstance( region , instanceName , instances["Instances"][0]["InstanceId"] , instance_config, instances["Instances"][0] )

    return instance , created

def create_instance_objects(instance_config):
    region   = instance_config['region']
    keypair  = create_keypair(region)
    vpc      = create_vpc(region,instance_config.get('cloud_id')) 
    secGroup = create_security_group(region,vpc)
    subnet   = create_subnet(region,vpc) 
    # this is where all the instance_config is actually used
    instance , created = create_instance(instance_config,vpc,subnet,secGroup)

    return instance , created 


def start_instance(instance):
    ec2_client = boto3.client("ec2", config=get_config(instance.get_region()))

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
                    raise CloudRunError()
                    # terminate_instance(config,instance)
                
        else:
            debug(2,botoerr)
            raise CloudRunError()

def stop_instance(instance):
    ec2_client = boto3.client("ec2", config=get_config(instance.get_region()))

    ec2_client.stop_instances(InstanceIds=[instance.get_id()])

def terminate_instance(instance):

    ec2_client = boto3.client("ec2", config=get_config(instance.get_region()))

    ec2_client.terminate_instances(InstanceIds=[instance.get_id()])

    if instance.get_data('SpotInstanceRequestId'):

        ec2_client.cancel_spot_instance_requests(SpotInstanceRequestIds=[instance.get_data('SpotInstanceRequestId')]) 

def get_instance_info(instance):
    ec2_client   = boto3.client("ec2", config=get_config(instance.get_region()))
    instances    = ec2_client.describe_instances( InstanceIds=[instance.get_id()] )
    instance_new = instances['Reservations'][0]['Instances'][0]
    return instance_new

async def wait_for_instance(instance):
    # get the public DNS info when instance actually started (todo: check actual state)
    waitFor = True
    while waitFor:
        updated_instance_info = get_instance_info(instance)
        lookForDNS   = not 'PublicDnsName' in updated_instance_info or updated_instance_info['PublicDnsName'] is None
        lookForIP    = not 'PublicIpAddress' in updated_instance_info or updated_instance_info['PublicIpAddress'] is None
        instanceState =  updated_instance_info['State']['Name']

        lookForState = True
        # 'pending'|'running'|'shutting-down'|'terminated'|'stopping'|'stopped'
        if instanceState == 'stopped' or instanceState == 'stopping':
            try:
                # restart the instance
                start_instance(instance)
            except CloudRunError:
                terminate_instance(instance)
                try :
                    create_instance_objects(config)
                except:
                    return None

        elif instanceState == 'running':
            lookForState = False

        waitFor = lookForDNS or lookForState  
        if waitFor:
            if lookForDNS:
                debug(1,"waiting for DNS address and  state ...",instanceState)
            else:
                if lookForIP:
                    debug(1,"waiting for state ...",instanceState)
                else:
                    debug(1,"waiting for state ...",instanceState," IP =",updated_instance_info['PublicIpAddress'])
            
            await asyncio.sleep(10)

    debug(2,updated_instance_info)    

    instance.set_data(updated_instance_info)
    instance.set_ip_addr(updated_instance_info['PublicIpAddress'])
    instance.set_dns_addr(updated_instance_info['PublicDnsName'])

async def connect_to_instance(instance):
    # ssh into instance and run the script from S3/local? (or sftp)
    k = paramiko.RSAKey.from_private_key_file('cloudrun-'+str(instance.get_region())+'.pem')
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    debug(1,"connecting to ",instance.get_dns_addr(),"/",instance.get_ip_addr())
    while True:
        try:
            ssh_client.connect(hostname=instance.get_dns_addr(),username=instance.get_config('img_username'),pkey=k) #,password=’mypassword’)
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

    return ssh_client


def line_buffered(f):
    line_buf = ""
    doContinue = True
    try :
        while doContinue and not f.channel.exit_status_ready():
            try:
                line_buf += f.read(16).decode("utf-8")
                if line_buf.endswith('\n'):
                    yield line_buf
                    line_buf = ''
            except Exception as e:
                #errmsg = str(e)
                #debug(1,"error (1) while buffering line",errmsg)
                pass 
                #doContinue = False
    except Exception as e0:
        debug(1,"error (2) while buffering line",str(e0))
        #doContinue = False

##########
# PUBLIC #
##########

class AWSCloudRunProvider(CloudRunProvider):

    def __init__(self, conf):
        CloudRunProvider.__init__(self,conf)
        if 'debug' in conf:
            global DBG_LVL
            DBG_LVL = conf['debug']

    def get_instance(self):

        return find_instance(self.config)

    def start_instance(self):

        instance = find_instance(self.config)

        if instance is None:
            instance , created = create_instance_objects(self.config)
        else:
            created = False

        return instance , created

    def stop_instance(self):
        stop_instance(self.get_instance())

    def terminate_instance(self):
        terminate_instance(self.get_instance())

    async def run_script(self):

        if (not 'input_file' in self.config) or (not 'output_file' in self.config) or not isinstance(self.config['input_file'],str) or not isinstance(self.config['output_file'],str):
            print("\n\nConfiguration requires an input and output file names\n\n")
            raise CloudRunError() 

        # CHECK EVERY TIME !
        instance , created = self.start_instance()

        await wait_for_instance(instance)

        # init environment object
        env_obj = init_environment(self.config)
        debug(2,json.dumps(env_obj))

        ssh_client = await connect_to_instance(instance)

        files_path = env_obj['path']

        # compute script hash 
        script_hash = cloudrunutils.compute_script_hash(self.config)
        script_path = env_obj['path_abs'] + '/' + script_hash

        # generate unique PID file
        uid = cloudrunutils.generate_unique_filename() 
        
        run_path   = script_path + '/' + uid

        script_command = cloudrunutils.compute_script_command(script_path,self.config)

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
        ftp_client.put('remote_files/microrun.sh','microrun.sh')
        ftp_client.put('remote_files/state.sh','state.sh')
        ftp_client.put('remote_files/tail.sh','tail.sh')
        ftp_client.put('remote_files/getpid.sh','getpid.sh')
        
        # change to run dir
        ftp_client.chdir(script_path)
        if 'run_script' in self.config and self.config['run_script']:
            filename = os.path.basename(self.config['run_script'])
            ftp_client.put(self.config['run_script'],filename)
        if 'upload_files' in self.config and self.config['upload_files'] is not None:
            if isinstance( self.config['upload_files'],str):
                self.config['upload_files'] = [ self.config['upload_files']  ]
            for upfile in self.config['upload_files']:
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
            { 'cmd': "chmod +x "+files_path+"/*.sh ", 'out' : True },  
            # recreate pip+conda files according to config
            { 'cmd': "cd " + files_path + " && python3 "+files_path+"/config.py" , 'out' : True },
            # setup envs according to current config files state
            # NOTE: make sure to let out = True or bootstraping is not executed properly 
            # TODO: INVESTIGATE THIS
            { 'cmd': files_path+"/bootstrap.sh \"" + env_obj['name'] + "\" " + ("1" if self.config['dev'] else "0") + " &", 'out': True },  
            # execute main script (spawn) (this will wait for bootstraping)
            { 'cmd': files_path+"/run.sh \"" + env_obj['name'] + "\" \""+script_command+"\" " + self.config['input_file'] + " " + self.config['output_file'] + " " + script_hash+" "+uid, 'out' : False }
        ]
        for command in commands:
            debug(1,"Executing ",format( command['cmd'] ),"output",command['out'])
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
                    pass
                    #stdout.read()
                    #pid = int(stdout.read().strip().decode("utf-8"))
            except paramiko.ssh_exception.SSHException as sshe:
                print("The SSH Client has been disconnected!")
                print(sshe)
                raise CloudRunError()

        # retrieve PID (this will wait for PID file)
        pid_file = run_path + "/pid"
        #getpid_cmd = "tail "+pid_file #+" && cp "+pid_file+ " "+run_path+"/pid" # && rm -f "+pid_file
        getpid_cmd = files_path+"/getpid.sh \"" + pid_file + "\""
        
        debug(1,"Executing ",format( getpid_cmd ) )
        stdin , stdout, stderr = ssh_client.exec_command(getpid_cmd)
        pid = int(stdout.readline().strip())

        # try:
        #     getpid_cmd = "tail "+pid_file + "2" #+" && cp "+pid_file+ " "+run_path+"/pid && rm -f "+pid_file
        #     debug(1,"Executing ",format( getpid_cmd ) )
        #     stdin , stdout, stderr = ssh_client.exec_command(getpid_cmd)
        #     pid2 = int(stdout.readline().strip())
        # except:
        #     pid2 = 0 

        ssh_client.close()

        debug(1,"UID =",uid,", PID =",pid,", SCRIPT_HASH =",script_hash) 

        # make sure we stop the instance to avoid charges !
        #stop_instance(instance)

        return CloudRunScriptRuntimeInfo( script_hash , uid , pid )

    # this allow any external process to wait for a specific job
    async def get_script_state( self, scriptRuntimeInfo ):

        instance = self.get_instance()

        if instance is None:
            print("get_command_state: instance is not available!")
            return CloudRunCommandState.UNKNOWN

        await wait_for_instance(instance)

        env_obj    = self.init_environment()
        files_path = env_obj['path']

        ssh_client = await connect_to_instance(instance)

        shash = scriptRuntimeInfo.get_hash()
        uid   = scriptRuntimeInfo.get_uid()
        pid   = scriptRuntimeInfo.get_pid()

        cmd = files_path + "/state.sh " + env_obj['name'] + " " + str(shash) + " " + str(uid) + " " + str(pid) + " " + self.config['output_file']
        debug(1,"Executing command",cmd)
        stdin, stdout, stderr = ssh_client.exec_command(cmd)

        statestr = stdout.read().decode("utf-8").strip()
        debug(1,"State=",statestr)
        statestr = re.sub(r'\([0-9]+\)','',statestr)
        try:
            state = CloudRunCommandState[statestr.upper()]
        except:
            print("\nUnhandled state received by state.sh!!!\n")
            state = CloudRunCommandState.UNKNOWN

        ssh_client.close()

        return state

    async def wait_for_script_state( self, script_state , scriptRuntimeInfo ):    
        instance = self.get_instance()

        if instance is None:
            print("get_command_state: instance is not available!")
            return CloudRunCommandState.UNKNOWN

        await wait_for_instance(instance)

        env_obj    = init_environment(self.config)
        files_path = env_obj['path']

        ssh_client = await connect_to_instance(instance)

        shash = scriptRuntimeInfo.get_hash()
        uid   = scriptRuntimeInfo.get_uid()
        pid   = scriptRuntimeInfo.get_pid()

        while True:

            cmd = files_path + "/state.sh " + env_obj['name'] + " " + str(shash) + " " + str(uid) + " " + str(pid) + " " + self.config['output_file']
            debug(1,"Executing command",cmd)
            stdin, stdout, stderr = ssh_client.exec_command(cmd)

            statestr = stdout.read().decode("utf-8").strip()
            debug(1,"State=",statestr)
            statestr = re.sub(r'\([0-9]+\)','',statestr)

            try:
                state = CloudRunCommandState[statestr.upper()]
            except:
                print("\nUnhandled state received by state.sh!!!",statestr,"\n")
                state = CloudRunCommandState.UNKNOWN

            if state & script_state:
                break 

            await asyncio.sleep(2)

        ssh_client.close()

        return state

    def _tail_execute_command(self,ssh,files_path,uid,line_num):
        run_log = files_path + '/' + uid + '-run.log'
        command = "cat -n %s | tail --lines=+%d" % (run_log, line_num)
        stdin, stdout_i, stderr = ssh.exec_command(command)
        #stderr = stderr.read()
        #if stderr:
        #    print(stderr)
        return stdout_i.readlines()    

    def _tail_get_last_line_number(self,lines_i, line_num):
        return int(lines_i[-1].split('\t')[0]) + 1 if lines_i else line_num            


    async def tail( self, scriptRuntimeInfo ):    
        instance = self.get_instance()

        if instance is None:
            print("tail: instance is not available!")

        await wait_for_instance(instance)

        env_obj    = self.init_environment()
        files_path = env_obj['path']

        shash = scriptRuntimeInfo.get_hash()
        uid   = scriptRuntimeInfo.get_uid()
        pid   = scriptRuntimeInfo.get_pid()

        ssh_client = await connect_to_instance(instance)

        cmd = files_path + "/tail.sh " + env_obj['name'] + " " + str(shash) + " " + str(uid) 
        debug(1,"Executing command",cmd)
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        return line_buffered(stdout) 

        # https://stackoverflow.com/questions/17137859/paramiko-read-from-standard-output-of-remotely-executed-command
        # https://stackoverflow.com/questions/7680055/python-to-emulate-remote-tail-f

        # lines = self._tail_execute_command(ssh_client,files_path,uid,0)
        # last_line_num = self._tail_get_last_line_number(lines, 0)
        # while True:
        #     for l in lines:
        #         yield l #'\t'.join(t.replace('\n', '') for t in l.split('\t')[1:]) 
        #     last_line_num = self._tail_get_last_line_number(lines, last_line_num)
        #     lines = self._tail_execute_command(ssh_client,files_path,uid,last_line_num)
        #     await asyncio.sleep(1)
