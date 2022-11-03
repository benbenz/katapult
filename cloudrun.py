import cloudrun_aws as craws

class CloudRunError(Exception):
    pass


def get_client(provider):

    if provider == 'aws':

        return craws

    else:

        print(config['service'], " not implemented yet")
        raise CloudRunError()


def set_debug_level(value):
    craws.set_debug_level(value)