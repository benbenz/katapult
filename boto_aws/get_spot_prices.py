import boto3

client=boto3.client('ec2',region_name='us-east-1')

prices=client.describe_spot_price_history(InstanceTypes=['m3.medium'],MaxResults=1,ProductDescriptions=['Linux/UNIX (Amazon VPC)'],AvailabilityZone='us-east-1a')



print(prices['SpotPriceHistory'][0])