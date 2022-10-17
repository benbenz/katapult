import boto3

session=boto3.session.Session()

ec2instances = session.resource('ec2',region_name="us-east-1")

new_instance = ec2instances.create_instances(
        ImageId = 'ami-029536273cb04d4d9',
        MinCount = 1,
        MaxCount = 1,
        InstanceType = 't2.micro',
        KeyName ='tibo2016',
        SecurityGroupIds=['sg-004faa446a7788d7d'],
        SubnetId = 'subnet-0ecaa08058826ec19'
)
print(new_instance)