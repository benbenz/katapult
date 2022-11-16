import json , os , stat , yaml

try:
    os.remove('environment.yml')
except:
    pass
try:    
    os.remove('requirements.txt')
except:
    pass
try:    
    os.remove('aptget.sh')
except:
    pass

with open('config.json','r') as cfg_file:
    config = json.loads(cfg_file.read())

if config['env_conda'] is not None:
    with open('environment.yml','w') as yml_file:
        yml_file.write(yaml.dump(config['env_conda'], sort_keys=False))
        yml_file.close()

if config['env_pypi'] is not None:
    with open('requirements.txt','w') as txt_file:
        for dep in config['env_pypi']:
            txt_file.write(dep+'\n')
        txt_file.close()

if config['env_aptget'] is not None:
    with open('aptget.sh','w') as sh_file:
        sh_file.write('#!/usr/bin/bash\n\nsudo apt-get install -y')
        for dep in config['env_aptget']:
            sh_file.write(' ' + dep)
        sh_file.close()
        st = os.stat('aptget.sh')
        os.chmod('aptget.sh', st.st_mode | stat.S_IEXEC)

