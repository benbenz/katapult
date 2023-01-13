# http://docs.getmoto.org/en/latest/docs/services/patching_other_services.html

# http://docs.getmoto.org/en/2.2.13/ (oldest doc)

import botocore
from botocore import client

# Original botocore _make_api_call function
orig = client.BaseClient._make_api_call

# Mocked botocore _make_api_call function
def mock_make_api_call(self, operation_name, kwarg):
    # For example for the Access Analyzer service
    # As you can see the operation_name has the list_analyzers snake_case form but
    # we are using the ListAnalyzers form.
    # Rationale -> https://github.com/boto/botocore/blob/develop/botocore/client.py#L810:L816
    if operation_name == 'ListAnalyzers':
        return { "analyzers":
            [{
                "arn": "ARN",
                "name": "Test Analyzer" ,
                "status": "Enabled",
                "findings": 0,
                "tags":"",
                "type": "ACCOUNT",
                "region": "eu-west-1"
                }
            ]}
    elif operation_name == 'DescribeInstances':
        result = orig(self, operation_name, kwarg)
        if result.get('Reservations') and len(result.get('Reservations'))>0:
            instances = result['Reservations'][0]['Instances']
            for instance in instances:
                for attr in ['PublicDnsName','PublicIpAddress','PrivateDnsName','PrivateIPAddress']:
                    instance[attr] = 'localhost'
        return result

    # If we don't want to patch the API call
    return orig(self, operation_name, kwarg)
