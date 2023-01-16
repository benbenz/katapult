import json , os , stat , yaml , shutil , re
from yaml.loader import FullLoader
import subprocess


def run(command_line):
    result = subprocess.run(command_line, shell=True, stdout=subprocess.PIPE)
    output = result.stdout.decode('utf-8')
    return output

bootstraped = True 
errors = []

env_name = os.path.basename(os.getcwd())
#print(env_name)
HOME = os.environ['HOME']

has_mamba = False

mambadir = os.path.join(HOME,'micromamba')
menvsdir = os.path.join(mambadir,'envs')
menvdir  = os.path.join(menvsdir,env_name)

print("\nENV_CHECK",env_name,"\n----------------------------")

if os.path.isfile('environment.yml'):
    history  = os.path.join(menvdir,'conda-meta','history')
    with open(history,'r') as history_file:
        history = history_file.read()
        #print(history)
        with open('environment.yml','r') as yml_file:
            has_mamba = True
            conda_cfg = yaml.load(yml_file, Loader=FullLoader)
            if 'dependencies' in conda_cfg:
                for dependency in conda_cfg.get('dependencies'):
                    if isinstance(dependency,str):
                        dependency = re.sub('[=<>].*', '', dependency)
                        if dependency not in history:
                            dependency = dependency.strip()
                            if not dependency:
                                continue
                            bootstraped = False
                            errors.append("dependency missing in mamba configuration: " + dependency+ " " + env_name)
                    elif isinstance(dependency,dict):
                        for dep in dependency.keys():
                            dep = dep.strip()
                            if not dep:
                                continue
                            dep = re.sub('[=<>].*', '', dep)
                            if dep not in history:
                                bootstraped = False
                                errors.append("dependency missing in mamba configuration ("+env_name+"): " + dep)

if os.path.isfile('requirements.txt'):
    piplist = ""
    pipsrc  = ""
    if has_mamba:
        pip = os.path.join(menvdir,'bin','pip')
        piplist = run(pip + " list")
        #print("piplist mamba",piplist)
        pipsrc = "mamba"
    else:
        venvpip = os.path.join(HOME,'run','.'+env_name,'bin','pip')
        piplist = run(venvpip + " list")
        #print("piplist venv",piplist)
        pipsrc = "venv"
    with open('requirements.txt','r') as txt_file:
        reqs = txt_file.read().split('\n')
        for req in reqs:
            req = req.strip()
            if not req:
                continue
            req = re.sub('\s*[=<>].*', '', req)
            if req not in piplist:
                bootstraped = False
                errors.append("dependency missing in pip configuration ("+pipsrc+" "+env_name+"): " + req)

if os.path.isfile('aptget.sh'):
    with open('aptget.sh','r') as sh_file:
        app_list = sh_file.read().replace('#!/usr/bin/bash\n\nsudo apt-get install -y','')
        app_list = app_list.split(' ')
        for app in app_list:
            app = app.strip()
            if not app:
                continue
            if shutil.which(app) is None:
                bootstraped = False
                errors.append("application not installed with apt-get: " + app + " " + env_name)

if os.path.isfile('env_julia.jl'):
    julia_pkgs = run("julia -e 'using Pkg; println(Pkg.dependencies())'")
    with open('env_julia.jl','r') as julia_file:
        pkg_content = julia_file.read()
        pkg_content = pkg_content.replace("using Pkg\n","")
        pkgs = pkg_content.split('\n')
        for pkg in pkgs:
            pkg = pkg.strip()
            if not pkg:
                continue
            pkg = re.sub(r'Pkg\.add\("([^\)]+)"\)', r'\g<1>', pkg)
            julia_script  = "using Pkg; if \"{0}\" in keys(Pkg.dependencies()) println(\"OK\") else print(\"NOT_OK\") end".format(pkg)
            julia_command = "julia -e '{0}'".format(julia_script)
            # julia_out = run(julia_command)
            # if julia_out != "OK":
            #      bootstraped = False
            #      errors.append("julia package not installed: "+pkg + " " + env_name)
            if pkg not in julia_pkgs:
                bootstraped = False
                errors.append("julia package not installed: "+pkg + " " + env_name)

if bootstraped:
    print('\nALL OK')
    with open('state','w') as file_state:
        file_state.write('bootstraped')
    with open('ready','w') as file_ready:
        file_ready.write("")
else:
    print(env_name+" bootstraping FAILED with errors:")
    for error in errors:
        print(error)
    with open('state','w') as file_state:
        file_state.write('failed')
    with open('errors','w') as file_errors:
        json.dump( errors , file_errors )