import boto3
import sys
from botocore.exceptions import ClientError

config = {
    'vpc_id'       : 'vpc-0babc28485f6730bc' ,
    'region'       : 'eu-west-3' ,
    'ami_id'       : 'ami-077fd75cd229c811b' , #"ami-029536273cb04d4d9"
    'keypair_name' : 'cloudrun-keypair'
}

secGroupName = 'cloudrun-sec-group-allow-ssh'

def create_keypair():
    print("Creating KeyPair ...")
    ec2_client = boto3.client("ec2", region_name=config['region'])
    keypair = None
    try:
        keypair = ec2_client.create_key_pair(
            KeyName=config['keypair_name'],
            DryRun=True,
            KeyType='rsa',
            KeyFormat='pem'
        )
    except ClientError as e: #DryRun=True >> always an "error"
        errmsg = str(e)
        
        if 'UnauthorizedOperation' in errmsg:
            print("The account is not authorized to create a keypair, please specify an existing keypair in the configuration or add Administrator privileges to the account")
            keypair = None
            sys.exit()

        elif 'DryRunOperation' in errmsg: # we are good with credentials
            try :
                keypair = ec2_client.create_key_pair(
                    KeyName=config['keypair_name'],
                    DryRun=False,
                    KeyType='rsa',
                    KeyFormat='pem'
                )
                pemfile = open("cloudrun.pem", "w")
                pemfile.write(keypair['KeyMaterial']) # save the private key in the directory (we will use it with paramiko)
                pemfile.close()
                print(keypair)

            except ClientError as e2: # the keypair probably exists already
                errmsg2 = str(e2)
                if 'InvalidKeyPair.Duplicate' in errmsg2:
                    ec2 = boto3.resource('ec2')
                    keypair = ec2.KeyPair(config['keypair_name'])
                    print(keypair.key_fingerprint)
                else:
                    print("An unknown error occured while retrieving the KeyPair")
                    print(errmsg2)
                    sys.exit()

        
        else:
            print("An unknown error occured while creating the KeyPair")
            print(errmsg)
            sys.exit()
    
    return keypair 

def create_vpc():
    print("Creating VPC ...")
    vpc = None
    ec2_client = boto3.client("ec2", region_name=config['region'])
    if 'vpc_id' in config:
        vpcID = config['vpc_id']
        ec2 = boto3.resource('ec2')
        vpc = ec2.Vpc(vpcID)    
        if vpc is None: # this ID doesn't exist
            print("WARNING: using default VPC. "+vpcID+" is unavailable")
            vpc = ec2_client.create_default_vpc()
    else:
        print("using default VPC (no VPC ID specified in config)")
        vpc = ec2_client.create_default_vpc()
    print(vpc)
    return vpc 

def create_security_group(vpc):
    secGroup = None
    ec2_client = boto3.client("ec2", region_name=config['region'])
    secgroups = ec2_client.describe_security_groups(Filters=[
        {
            'Name': 'string',
            'Values': [
                secGroupName,
            ]
        },
    ])
    if len(secgroups['SecurityGroups']) === 0: # we have no security group, lets create one
        print("Creating new security group")
    else:
        ec2 = boto3.resource('ec2')
        secGroup = ec2.SecurityGroup(secgroups['SecurityGroups'][0].group_id)



def create_instance():

    ec2_client = boto3.client("ec2", region_name=config['region'])
    instances = ec2_client.run_instances(
        ImageId=amiID,
        MinCount=1,
        MaxCount=1,
        InstanceType="t2.micro",
        KeyName=config['keypair_name'],
        SubnetId='subnet-01c48bdbf5383d175'
    )

    print(instances["Instances"][0]["InstanceId"])


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

keypair = create_keypair()
vpc     = create_vpc() 
#create_instance()

