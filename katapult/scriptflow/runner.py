import asyncio
import shutil
import os
import shlex
import traceback
import fnmatch
from datetime import datetime
from scriptflow.runners import AbstractRunner
from katapult.provider import get_client
from katapult.core import KatapultProcessState
from katapult.utils import generate_unique_id

TASK_PROP_UID = 'katapult_uid'
TASK_DICT_HANDLED = '_handled'
JOB_CFG_T_UID = 'task_uid'
SLEEP_PERIOD_SHORT = 0.1
SLEEP_PERIOD_LONG  = 15

# Runner for tlamadon/scriptflow

class KatapultRunner(AbstractRunner):

    def __init__(self, conf, **kwargs):
        self._katapult         = get_client(conf)
        self._run_session       = None
        self._processes         = {}
        self._num_instances     = 0 
        self._sleep_period      = SLEEP_PERIOD_SHORT
        self._handle_task_queue = kwargs.get('handle_task_queue',True)
        self._do_reset          = kwargs.get('reset',False)
        self._upload_python     = kwargs.get('upload_python_files',False)

    def _move_results(self,results_dir):
        for root, dirs, files in os.walk(results_dir):
            for filename in files:
                moved_file = os.path.join(os.getcwd(),filename)
                if os.path.isfile(moved_file):
                    os.remove(moved_file)
                src_file = os.path.join(results_dir,filename)
                shutil.move(src_file,os.getcwd())
                #print("moved {0} to {1}".format(src_file,moved_file))

            for dirname in dirs:
                moved_dir = os.path.join(os.getcwd(),dirname)
                if os.path.isdir(moved_dir):
                    shutil.rmtree(moved_dir)
                shutil.move(os.path.join(results_dir,dirname),os.getcwd())
        
        # remove it so the next fetch_result doesnt return prematurely (we're using cached=True)
        shutil.rmtree(results_dir)
            

    def _associate_jobs_to_tasks(self,objects):
        # associate the job objects with the tasks
        for (k,p) in self._processes.items():
            if p["job"]:
                continue
            if p.get(TASK_DICT_HANDLED,False)==False:
                continue
            found = False
            for job in objects['jobs']:
                if job.get_config(JOB_CFG_T_UID) == p["task"].get_prop(TASK_PROP_UID):
                    p["job"] = job
                    found = True
                    break
            if not found:
                # this can happen due to asynchronisms
                #raise Error("Internal Error: could not find job for task")        
                pass

    def _flatten_inouts(self,obj,result):
        if isinstance(obj,list):
            for o in obj:
                self._flatten_inouts(o,result)
        elif isinstance(obj,dict):
            for v in obj.values():
                self._flatten_inouts(v,result)
        elif isinstance(obj,str):
            result.append(obj)
        return result 

    def size(self):
        return(len(self._processes))

    def available_slots(self):
        if self._handle_task_queue:
            # always available slots
            # this will cause the controller to add all the tasks at once
            # katapult will handle the stacking with its own batch_run feature ...
            return self._num_instances
        else:
            return self._num_instances - len(self._processes)

    """
        Start tasks
    """

    def add(self, task):

        # we're not doing much here because this method is not async ...
        # leave it to the update(..) method to do the work...
        # we also want to group the handling of adding jobs and running them

        # we don't want to wait as much when we are adding tasks >> lower the period
        self._sleep_period = SLEEP_PERIOD_SHORT 

        # let's not touch the name/uid of the task
        # and it may be empty ...
        task.set_prop(TASK_PROP_UID,generate_unique_id())

        self._processes[task.hash] = {
            "task": task , 
            "job":  None , # we have a one-to-one relationship between job and task (no demultiplier)
            "state" : KatapultProcessState.UNKNOWN ,
            'start_time': datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        }

    """
        Continuously checks on the tasks
    """
    async def loop(self, controller):

        # start the provider and get remote instances information
        await self._katapult.start(self._do_reset)
        # delete the fetch results directory
        await self._katapult.clear_results_dir()

        # cache the number of instances
        self._num_instances = await self._katapult.get_num_instances()

        while True:
            try:
                await self._update(controller)                
                await asyncio.sleep(self._sleep_period)
            except Exception as e:
                print("Loop Error",e)
                traceback.print_exc()
                break

    async def _update(self,controller):

        jobs_cfg = []

        job_added    = True
        while job_added:
            job_added = False
            for (k,p) in self._processes.items():
                # create the job if its not there (it will append/run automatically)
                if p["job"]:
                    continue 

                if p.get(TASK_DICT_HANDLED,False) == True:
                    continue

                task = p["task"]

                nuargs = []
                for arg in task.get_command():
                    if " " in arg:
                        #nuargs.append( "\\\"" + arg + "\\\"")
                        nuargs.append( "\"" + arg + "\"")
                        #nuargs.append(arg)
                    else:
                        nuargs.append(arg)

                job_cfg = {
                    'input_files'  : self._flatten_inouts(task.deps,[]) ,
                    'output_files' : self._flatten_inouts(task.outputs,[]),
                    #'run_command'  : shlex.join(task.get_command()) ,
                    #'run_command'  : " ".join(task.get_command()) ,
                    #'run_command'  : " ".join([shlex.quote(arg) for arg in task.get_command()]) ,
                    'run_command'  : " ".join(nuargs) ,
                    'cpus_req'     : task.ncore ,
                    'number'       : 1 ,
                    JOB_CFG_T_UID  : task.get_prop(TASK_PROP_UID)
                }

                # option to upload all python files of the directory
                # in case some defined routines are used (as in the examples)
                if self._upload_python:
                    filesOfDirectory = os.listdir('.')
                    pattern = "*.py"
                    for file in filesOfDirectory:
                        if fnmatch.fnmatch(file, pattern):
                            if not job_cfg.get('upload_files'):
                                job_cfg['upload_files'] = []
                            job_cfg['upload_files'].append(file)
                # lets upload also the sflow file
                # in case some defined routines are used (as in the examples)
                # if os.path.isfile( os.path.join(os.getcwd(),'sflow.py') ):
                #     if not job_cfg.get('upload_files'):
                #         job_cfg['upload_files'] = []
                #     job_cfg['upload_files'].append('sflow.py')

                jobs_cfg.append( job_cfg )

                job_added     = True
                p[TASK_DICT_HANDLED] = True
            
            # we've just added a task let's see if another one comes in ...
            await asyncio.sleep(.5)

        # add the new jobs and get jobs objects back
        if len(jobs_cfg)>0:

            objects = await self._katapult.cfg_add_jobs(jobs_cfg,run_session=self._run_session)

            # 1 task <-> 1 job
            assert( objects and len(objects['jobs']) == len(jobs_cfg) )

            # run the jobs
            if self._run_session is None:
                await self._katapult.deploy() # deploy the new jobs etc.
                self._run_session = await self._katapult.run() 
            else:
                await self._katapult.deploy() # deploy the new jobs etc.
                await self._katapult.run(True) # continue_session

            # associate task <-> job
            self._associate_jobs_to_tasks(objects)

        if len(self._processes)>0:
            # fetch statusses here ...
            # True stands for 'last_running_processes' meaning we will only get one process per job (the last one)
            processes_states = await self._katapult.get_jobs_states(self._run_session,True)

            # augment the period now ...
            if processes_states and len(processes_states)>0:
                self._sleep_period = SLEEP_PERIOD_LONG

        else:
            self._sleep_period = SLEEP_PERIOD_SHORT


        has_aborted_process = False

        #update status
        to_remove = []
        for (k,p) in self._processes.items():
            job = p["job"]
            if not job: # this task hadnt been handled yet
                continue 
            if p.get(TASK_DICT_HANDLED,False)==False:
                continue
            found_process = False
            for pstatus in processes_states.values():
                if pstatus['job_config'][JOB_CFG_T_UID] == p["task"].get_prop(TASK_PROP_UID):

                    # we match with runner-managed task id, but the job_id should also be right
                    # (we self manage this match in case katapult internal api changes)
                    assert pstatus['job_id'] == job.get_id() , "Internal Error: task<->job<->last_process: it looks like something is wrong ! Fix it"
                    
                    p["state"] = pstatus['state']
                    found_process = True
                    break
            
            # should not happen
            assert found_process , "Internal Error: task<->job<->last_process: We couldn't find a process in the results"

            if p["state"] & ( KatapultProcessState.DONE | KatapultProcessState.ABORTED):
                to_remove.append(k)
                has_aborted_process = has_aborted_process or p["state"] == KatapultProcessState.ABORTED

        # we got some jobs to fetch
        if len(to_remove)>0:
            results_dir = await self._katapult.fetch_results('tmp',self._run_session,True,True)
            self._move_results(results_dir)
            if has_aborted_process:
                await self._katapult.print_aborted_logs(self._run_session)

        # signal completed tasks
        for k in to_remove:
            task = self._processes[k]["task"]
            del self._processes[k]       
            controller.add_completed( task )