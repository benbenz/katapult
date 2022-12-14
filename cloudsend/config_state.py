
import copy
import sys
import os , signal
import json
import pickle
import math
from cloudsend.core import *
from datetime import date, datetime
import traceback

class ConfigManager():

    def __init__(self,provider,conf,instances,environments,jobs):
        
        self._provider = provider
        self._config = conf
        self._instances = instances
        self._environments = environments
        self._jobs = jobs

    def load(self):
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
                if inst_cfg.get(K_LOADED) == True:
                    continue 

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

                        self._load_other_instance_info(real_inst_cfg)

                        # starts calling the Service here !
                        # instance , created = self.start_instance( real_inst_cfg )
                        # let's put some dummy instances for now ...
                        instance = CloudSendInstance( real_inst_cfg , None, None )
                        self._instances.append( instance )
                    else:
                        total_inst_cpus = inst_cfg.get('cpus',1)
                        if type(total_inst_cpus) != int and type(total_inst_cpus) != float:
                            cpucore = self._provider.get_cpus_cores(inst_cfg)
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

                            self._load_other_instance_info(real_inst_cfg)

                            # let's put some dummy instances for now ...
                            instance = CloudSendInstance( real_inst_cfg , None, None )
                            self._instances.append( instance )

                            cpus_created = cpus_created + inst_cpus

                    inst_cfg[K_LOADED] = True
        
        self._provider.debug(3,self._instances)

        #self._environments = [ ] 
        if env_cfgs:
            for env_cfg in env_cfgs:
                if env_cfg.get(K_LOADED) == True:
                    continue

                # copy the dev global paramter to the environment configuration (will be used for names)
                env_cfg['dev']  = self._config.get('dev',False)
                env = CloudSendEnvironment(projectName,env_cfg)
                self._environments.append(env)

                env_cfg[K_LOADED] = True

        #self._jobs = [ ] 
        if job_cfgs:
            rank=0
            for i,job_cfg in enumerate(job_cfgs):
                if job_cfg.get(K_LOADED) == True:
                    continue 

                for j in range(job_cfg.get('repeat',1)):
                    job = CloudSendJob(job_cfg,rank)
                    self._jobs.append(job)
                    rank = rank + 1
                
                job_cfg[K_LOADED] = True

    def _load_other_instance_info(self,real_inst_cfg):
        # [!important!] also copy global information that are used for the name generation ...
        real_inst_cfg['dev']      = self._config.get('dev',False)
        real_inst_cfg['project']  = self._config.get('project',None)

        # let's also freeze the region
        # this is done so that we dont change the hash when sending the config to maestro
        # (because the client adds the 'region' field when translating the config)
        if not real_inst_cfg.get('region'):
            real_inst_cfg['region'] = self._provider.get_region()     

        # also set the img_id is None
        if not real_inst_cfg.get('img_id'):
            img_id , img_username , img_type = self._provider.get_suggested_image(real_inst_cfg['region'])
            real_inst_cfg['img_id']          = img_id 
            real_inst_cfg['img_username']    = img_username 

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
        if len(self._instances) > 10:
            self._provider.debug(1,"\033[91mWATCH OUT ! You are creating more than 10 instances - not allowed for now!\033[0m")
            raise Exception()

    def _get_environment(self,name):
        for env in self._environments:
            if env.get_name() == name:
                return env
        return None

# def json_get_key(obj):
#     if isinstance(obj,CloudSendInstance):
#         return "__cloudsend_instance:" + obj.get_name()
#     elif isinstance(obj,CloudSendDeployedEnvironment):
#         return "__cloudsend_environment_dpl:" + obj.get_name()
#     elif isinstance(obj,CloudSendEnvironment):
#         return "__cloudsend_environment:" + obj.get_name()
#     elif isinstance(obj,CloudSendDeployedJob):
#         return "__cloudsend_job_dpl:" + obj.get_hash() + "|" + str(obj.get_job().get_rank()) + "," + str(obj.get_rank())
#     elif isinstance(obj,CloudSendJob):
#         return "__cloudsend_job:" + obj.get_hash() + "|" + str(obj.get_rank()) 
#     elif isinstance(obj,CloudSendProcess):
#         return "__cloudsend_process:" + obj.get_uid()
#     else:
#         return str(cs_obj)

# class CloudSendJSONEncoder(json.JSONEncoder):

#     def __init__(self, *args, **kwargs):
#         kwargs['check_circular'] = False  # no need to check anymore
#         super(CloudSendJSONEncoder,self).__init__(*args, **kwargs)
#         self.proc_objs = []

#     def default(self, obj):

#         if  isinstance(obj, (CloudSendInstance, CloudSendEnvironment, CloudSendDeployedEnvironment, CloudSendJob, CloudSendDeployedJob, CloudSendProcess)):
#             if obj in self.proc_objs:
#                 return json_get_key(obj)
#             else:
#                 self.proc_objs.append(obj)
#             return { **obj.__dict__ , **{'__class__':type(obj).__name__} }
        
#         elif isinstance(obj, (datetime, date)):
#             return obj.isoformat()  # Let the base class default method raise the TypeError

#         return super(CloudSendJSONEncoder,self).default(obj) #json.JSONEncoder.default(self, obj)

# class CloudSendJSONDecoder(json.JSONDecoder):
#     def __init__(self, *args, **kwargs):
#         json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)
#         self._references = dict()
    
#     def object_hook(self, dct):
#         #print(dct)
#         if '__class__' in dct:
#             class_name = dct['__class__']
#             try :
#                 if class_name == 'CloudSendInstance':
#                     obj = CloudSendInstance(dct['_config'],dct['_id'],dct['_data'])
#                     obj.__dict__.update(dct)
#                 elif class_name == 'CloudSendEnvironment':
#                     obj = CloudSendEnvironment(dct['_project'],dct['_config'])
#                     obj.__dict__.update(dct)
#                 elif class_name == 'CloudSendDeployedEnvironment':
#                     env_ref = None #self._references[dct['_env']]
#                     ins_ref = None #self._references[dct['_instance']]
#                     obj = CloudSendDeployedEnvironment.__new__(CloudSendDeployedEnvironment) #CloudSendDeployedEnvironment(env_ref,ins_ref)
#                     obj.__dict__.update(dct)
#                 elif class_name == 'CloudSendJob':
#                     obj = CloudSendJob(dct['_config'],dct['_rank'])
#                     obj.__dict__.update(dct)
#                 elif class_name == 'CloudSendDeployedJob':
#                     job_ref = None #self._references[dct['_job']]
#                     env_ref = None #self._references[dct['_env']]
#                     obj = CloudSendDeployedJob.__new__(CloudSendDeployedJob) #CloudSendDeployedJob(job_ref,env_ref)
#                     obj.__dict__.update(dct)
#                 elif class_name == 'CloudSendProcess':
#                     job_ref = None #self._references[dct['_job']]
#                     obj = CloudSendProcess.__new__(CloudSendProcess) #CloudSendProcess(job_ref,dct['_uid'],dct['_pid'],dct['_batch_uid'])
#                     obj.__dict__.update(dct)
#                 self._references[json_get_key(obj)] = obj
#                 return obj
#             except KeyError as ke:
#                 traceback.print_exc()
#                 print("KEY ERROR while DESERIALIZATION",ke)
#                 print(self._references)
#                 return None
#         else:
#             return dct        


STATE_FILE = 'state.pickle'

class StateSerializer():

    def __init__(self,provider):
        self._provider = provider

        self._state_file = STATE_FILE
        self._loaded = None

    def reset(self):
        if os.path.isfile(self._state_file):
            try:
                os.remove(self._state_file)
            except:
                pass

    def serialize(self,provider_state,instances,environments,jobs,run_sessions,current_session):
        try:
            state = {
                'state' : provider_state ,
                'instances' : instances ,
                'environments' : environments ,
                'jobs' : jobs ,
                'run_sessions' : run_sessions ,
                'current_session' : current_session
            }
            for job in state['jobs']:
                lastp = job.get_last_process()
                self._provider.debug(3,"PROCESS TO SERIALIZE",lastp)

            #json_data = json.dumps(state,indent=4,cls=CloudSendJSONEncoder)
            with open(self._state_file,'wb') as state_file:
                pickle.dump(state,state_file)#,protocol=0) # protocol 0 = readable
                #state_file.write(json_data)
        except Exception as e:
            self._provider.debug(1,"SERIALIZATION ERROR",e)


    def load(self):
        if not os.path.isfile(self._state_file):
            self._provider.debug(2,"StateSerializer: no state serialized")
            return False
        try:
            with open(self._state_file,'rb') as state_file:
                #json_data = state_file.read()
                #objects   = json.loads(json_data,cls=CloudSendJSONDecoder)
                self._loaded = pickle.load(state_file)
        except Exception as e:
            traceback.print_exc()
            self._provider.debug(1,"DE-SERIALIZATION ERROR",e)

    # check if the state is consistent with the provider objects that have been loaded from the config...
    # TODO: do that
    def check_consistency(self,state,instances,environments,jobs,run_sessions,current_session):
        if self._loaded is None:
            self._provider.debug(2,"Seralized data not loaded. No consistency")
            return False 
        try:
            _state        = self._loaded['state']
            _instances    = self._loaded['instances']
            _environments = self._loaded['environments']
            _jobs         = self._loaded['jobs']
            # those won't be compared because they are run time memory stuff...
            _run_sessions = self._loaded['run_sessions']
            _current_session = self._loaded['current_session']
            for job in jobs:
                lastp = job.get_last_process()
                self._provider.debug(3,"DESERIALIZED PROCESS",lastp)
            # state wont be the same by definition ...
            #assert state==_state 
            assert len(instances)==len(_instances)
            assert len(environments)==len(_environments)
            assert len(jobs)==len(_jobs)
            
            for i,instance in enumerate(instances):
                assert instance.get_name() == _instances[i].get_name()
                # more general to not compare the instances 
                # this means we need to detect another way if the instance failed before 
                # and reload the new instance in the state ?
                # >> this is now done with instances_states in provider + jobs 'UNKNOWN' states detection ....
                #assert instance.get_id()   == _instances[i].get_id()
                assert instance.get_cpus() == _instances[i].get_cpus()
            for i,env in enumerate(environments):
                assert env.get_name_with_hash() == _environments[i].get_name_with_hash()
            for i,job in enumerate(jobs):
                assert job.get_hash() == _jobs[i].get_hash() # this ensures input,uploads and script are the same....
                assert job.get_config('run_script') == _jobs[i].get_config('run_script') # hash doesnt capture the args 
                assert job.get_config('run_command') == _jobs[i].get_config('run_command') # no need (dont with hash), but for symetry with run_script....
                assert job.get_config('cpus_req') == _jobs[i].get_config('cpus_req')
                assert job.get_rank() == _jobs[i].get_rank()
            return True
        except Exception as e:
            self._provider.debug(1,e)
            return False

    def transfer(self):
        return self._loaded['state'] , self._loaded['instances'] , self._loaded['environments'] , self._loaded['jobs'] , self._loaded['run_sessions'] , self._loaded['current_session']