import cloudrun_aws as craws

def get_client(provider):

    if provider == 'aws':

        return craws

    else:

        print(config['service'], " not implemented yet")
        raise CloudRunError()
