import boto3

keypair_name = 'katapult-keypair-eu-west-3'
key_pair = boto3.resource('ec2').KeyPair(keypair_name)
print(key_pair)
print(key_pair.key_pair_id)