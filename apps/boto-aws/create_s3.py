import boto3 

s3 = boto3.resource('s3')

response = s3.create_bucket(
    Bucket='scriptflow',
    # CreateBucketConfiguration={
    #     'LocationConstraint': 'us-east-1'
    # }
)

print(response)


