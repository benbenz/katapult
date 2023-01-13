
config_aws_one_instance_local = {
    'project'      : 'test' ,                             
    'maestro'      : 'local',
    'profile'      : 'mock' ,

    'instances' : [
        {
            'type' : 't3.micro' ,
            'number'       : 1
        }
    ]
}

