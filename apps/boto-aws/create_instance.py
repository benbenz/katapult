import boto3

region = 'eu-west-3'
amiID  = 'ami-077fd75cd229c811b' #"ami-029536273cb04d4d9"

def create_instance():
    ec2_client = boto3.client("ec2", region_name=region)
    instances = ec2_client.run_instances(
        ImageId=amiID,
        MinCount=1,
        MaxCount=1,
        InstanceType="c5a.large",
        KeyName="benoit-2022",
        SubnetId='subnet-01c48bdbf5383d175'
    )

    print(instances["Instances"][0]["InstanceId"])


def get_public_ip(instance_id):
    ec2_client = boto3.client("ec2", region_name=region)
    reservations = ec2_client.describe_instances(InstanceIds=[instance_id]).get("Reservations")

    for reservation in reservations:
        for instance in reservation['Instances']:
            print(instance.get("PublicIpAddress"))    


def list_amis():
    ec2 = boto3.client('ec2', region_name=region)
    response = ec2.describe_instances()
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            print(instance["ImageId"])

create_instance()
