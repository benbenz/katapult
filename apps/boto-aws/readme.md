
following [aws batch log](https://gist.github.com/doi-t/01e5241c9595e7b8e3540f0125bd4519)


```shell

# extract the vpc ID
AWS_VPCID = `aws ec2 describe-subnets | jq -r '.Subnets[0].VpcId'`

aws ec2 describe-vpc-attribute --vpc-id $AWS_VPCID --attribute enableDnsSupport 

aws ec2 describe-vpc-attribute --vpc-id $AWS_VPCID --attribute enableDnsHostnames

```
