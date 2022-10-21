import boto3
import json 

client = boto3.client('iam')

assume_role_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "ecs-tasks.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]   
}

response = client.create_role(
    RoleName='dynamodbImportRole',
    AssumeRolePolicyDocument=json.dumps(assume_role_policy)
)

client.attach_role_policy(
    RoleName=response['Role']['RoleName'],
    PolicyArn='arn:aws:iam::aws:policy/AmazonS3FullAccess'
)

client.attach_role_policy(
    RoleName=response['Role']['RoleName'],
    PolicyArn='arn:aws:iam::aws:policy/CloudWatchFullAccess'
)

print(response)