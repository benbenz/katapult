
import copy
import sys
from .core import *

class ConfigManager():

    def __init__(self,provider,conf,instances,environments,jobs):
        
        self._provider = provider
        self._config = conf
        self._instances = instances
        self._environments = environments
        self._jobs = jobs

        self._load_objects()
        self._preprocess_jobs()
        self._sanity_checks()


    def _load_objects(self):
        projectName = self._config.get('project')
        inst_cfgs   = self._config.get('instances')
        env_cfgs    = self._config.get('environments')
        job_cfgs    = self._config.get('jobs')

        #self._instances = [ ]
        if inst_cfgs:
            for inst_cfg in inst_cfgs:
                # virtually demultiply according to 'number' and 'explode'
                for i in range(inst_cfg.get('number',1)):
                    rec_cpus = self._provider.get_recommended_cpus(inst_cfg)
                    if rec_cpus is None:
                        self._provider.debug(1,"WARNING: could not set recommended CPU size for instance type:",inst_cfg.get('type'))
                        cpu_split = None
                    else:
                        cpu_split = rec_cpus[len(rec_cpus)-1]

                    if cpu_split is None:
                        if inst_cfg.get('cpus') is not None:
                            oldcpu = inst_cfg.get('cpus')
                            self._provider.debug(1,"WARNING: removing CPU reqs for instance type:",inst_cfg.get('type'),"| from",oldcpu,">>> None")
                        real_inst_cfg = copy.deepcopy(inst_cfg)
                        real_inst_cfg.pop('number',None)  # provide default value to avoid KeyError
                        real_inst_cfg.pop('explode',None) # provide default value to avoid KeyError

                        real_inst_cfg['cpus'] = None
                        real_inst_cfg['rank'] = "{0}.{1}".format(i+1,1)
                        # [!important!] also copy global information that are used for the name generation ...
                        real_inst_cfg['dev']  = self._config.get('dev',False)
                        real_inst_cfg['project']  = self._config.get('project',None)

                        # starts calling the Service here !
                        # instance , created = self.start_instance( real_inst_cfg )
                        # let's put some dummy instances for now ...
                        instance = CloudRunInstance( real_inst_cfg , None, None )
                        self._instances.append( instance )
                    else:
                        total_inst_cpus = inst_cfg.get('cpus',1)
                        if type(total_inst_cpus) != int and type(total_inst_cpus) != float:
                            cpucore = self.get_cpus_cores(inst_cfg)
                            total_inst_cpus = cpucore if cpucore is not None else 1
                            self._provider.debug(1,"WARNING: setting default CPUs number to",cpucore,"for instance",inst_cfg.get('type'))
                        if not inst_cfg.get('explode') and total_inst_cpus > cpu_split:
                            self._provider.debug(1,"WARNING: forcing 'explode' to True because required number of CPUs",total_inst_cpus,' is superior to ',inst_cfg.get('type'),'max number of CPUs',cpu_split)
                            inst_cfg.set('explode',True)

                        if inst_cfg.get('explode'):
                            num_sub_instances = math.floor( total_inst_cpus / cpu_split ) # we target CPUs with 16 cores...
                            if num_sub_instances == 0:
                                cpu_inc = total_inst_cpus
                                num_sub_instances = 1
                            else:
                                cpu_inc = cpu_split 
                                num_sub_instances = num_sub_instances + 1
                        else:
                            num_sub_instances = 1
                            cpu_inc = total_inst_cpus
                        cpus_created = 0 
                        for j in range(num_sub_instances):
                            rank = "{0}.{1}".format(i+1,j+1)
                            if j == num_sub_instances-1: # for the last one we're completing the cpus with whatever
                                inst_cpus = total_inst_cpus - cpus_created
                            else:
                                inst_cpus = cpu_inc
                            if inst_cpus == 0:
                                continue 

                            if rec_cpus is not None and not inst_cpus in rec_cpus:
                                self._provider.debug(1,"ERROR: The total number of CPUs required causes a sub-number of CPUs ( =",inst_cpus,") to not be accepted by the type",inst_cfg.get('type'),"| list of valid cpus:",rec_cpus)
                                sys.exit()

                            real_inst_cfg = copy.deepcopy(inst_cfg)
                            real_inst_cfg.pop('number',None)  # provide default value to avoid KeyError
                            real_inst_cfg.pop('explode',None) # provide default value to avoid KeyError
                            real_inst_cfg['cpus'] = inst_cpus
                            real_inst_cfg['rank'] = rank
                            # [!important!] also copy global information that are used for the name generation ...
                            real_inst_cfg['dev']  = self._config.get('dev',False)
                            real_inst_cfg['project']  = self._config.get('project',None)

                            # let's put some dummy instances for now ...
                            instance = CloudRunInstance( real_inst_cfg , None, None )
                            self._instances.append( instance )

                            cpus_created = cpus_created + inst_cpus
        
        self._provider.debug(3,self._instances)

        #self._environments = [ ] 
        if env_cfgs:
            for env_cfg in env_cfgs:
                # copy the dev global paramter to the environment configuration (will be used for names)
                env_cfg['dev']  = self._config.get('dev',False)
                env = CloudRunEnvironment(projectName,env_cfg)
                self._environments.append(env)

        #self._jobs = [ ] 
        if job_cfgs:
            for i,job_cfg in enumerate(job_cfgs):
                job = CloudRunJob(job_cfg,i)
                self._jobs.append(job)

    # fill up the jobs names if not present (and we have only 1 environment defined)
    # link the jobs objects with an environment object
    def _preprocess_jobs(self):
        for job in self._jobs:
            if not job.get_config('env_name'):
                if len(self._environments)==1:
                    job.attach_env(self._environments[0])
                else:
                    print("FATAL ERROR - you have more than one environments defined and the job doesnt have an env_name defined",job)
                    sys.exit()
            else:
                env = self._get_environment(job.get_config('env_name'))
                if not env:
                    print("FATAL ERROR - could not find env with name",job.get_config('env_name'),job)
                    sys.exit()
                else:
                    job.attach_env(env)

    def _sanity_checks(self):
        pass

    def _get_environment(self,name):
        for env in self._environments:
            if env.get_name() == name:
                return env
        return None

