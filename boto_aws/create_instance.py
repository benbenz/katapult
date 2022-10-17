import boto3

def create_instance():
    ec2_client = boto3.client("ec2", region_name="us-east-1")
    instances = ec2_client.run_instances(
        ImageId="ami-029536273cb04d4d9",
        MinCount=1,
        MaxCount=1,
        InstanceType="c4.8xlarge",
        KeyName="tibo2016",
        SubnetId='subnet-0ecaa08058826ec19'
    )

    print(instances["Instances"][0]["InstanceId"])


def get_public_ip(instance_id):
    ec2_client = boto3.client("ec2", region_name="us-west-2")
    reservations = ec2_client.describe_instances(InstanceIds=[instance_id]).get("Reservations")

    for reservation in reservations:
        for instance in reservation['Instances']:
            print(instance.get("PublicIpAddress"))    


def list_amis():
    ec2 = boto3.client('ec2', region_name='us-east-1')
    response = ec2.describe_instances()
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            print(instance["ImageId"])

create_instance()
