import asyncio
from datetime import datetime
from scriptflow.runners import AbstractRunner
from cloudsend.provider import get_client
from cloudsend.core import CloudSendProcessState
from cloudsend.utils import generate_unique_id

TASK_PROP_UID = 'cloudsend_uid'
JOB_CFG_T_UID = 'task_uid'
SLEEP_PERIOD_SHORT = 0.1
SLEEP_PERIOD_LONG  = 15

# Runner for tlamadon/scriptflow

class CloudSendRunner(AbstractRunner):

    def __init__(self, conf, handle_task_queue=True):
        self._cloudsend         = get_client(conf)
        self._run_session       = None
        self._processes         = {}
        self._num_instances     = 0 
        self._handle_task_queue = handle_task_queue
        self._sleep_period      = SLEEP_PERIOD_SHORT

    def size(self):
        return(len(self._processes))

    def available_slots(self):
        if self._handle_task_queue:
            # always available slots
            # this will cause the controller to add all the tasks at once
            # cloudsend will handle the stacking with its own batch_run feature ...
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

        self._processes[task.hash] = {
            "task": task , 
            "job":  None , # we have a one-to-one relationship between job and task (no demultiplier)
            "state" : CloudSendProcessState.UNKNOWN ,
            'start_time': datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        }  

    """
        Continuously checks on the tasks
    """
    async def loop(self, controller):

        # start the provider and get remote instances information
        await self._cloudsend.start()
        # delete the fetch results directory
        await self._cloudsend.clear_results_dir()
        # deploy the added jobs on the instances ...
        await self._cloudsend.deploy()

        # cache the number of instances
        self._num_instances = await self._cloudsend.get_num_instances()

        while True:
            await self._update(controller)                
            await asyncio.sleep(self._sleep_period)

    async def _update(self,controller):

        jobs_cfg = []

        for (k,p) in self._processes.items():
            # create the job if its not there (it will append/run automatically)
            if p["job"]:
                continue 

            task = p["task"]

            # let's not touch the name/uid of the task
            # and it may be empty ...
            task.set_prop(TASK_PROP_UID,generate_unique_id())

            job_cfg = {
                'input_files'  : task.inputs  ,
                'output_files' : task.outputs ,
                'run_command'  : " ".join(task.get_command()) ,
                'cpus_req'     : task.ncore ,
                'number'       : 1 ,
                JOB_CFG_T_UID  : task.get_prop(TASK_PROP_UID)
            }

            jobs_cfg.append( job_cfg )

        # add the new jobs and get jobs objects back
        if len(jobs_cfg)>0:
            objects = await self._cloudsend.cfg_add_jobs(jobs_cfg)

            # 1 task <-> 1 job
            assert( objects and len(objects['jobs']) == len(jobs_cfg) )

            # run the jobs
            if self._run_session is None:
                self._run_session = await self._cloudsend.run() 
            else:
                await self._cloudsend.run(True) # continue_session

        # associate the job objects with the tasks
        for (k,p) in self._processes.items():
            if p["job"]:
                continue
            found = False
            for job in objects['jobs']:
                if job.get_config(JOB_CFG_T_UID) == p["task"].get_prop(TASK_PROP_UID):
                    p["job"] = job
                    found = True
                    break
            if not found:
                raise Error("Internal Error: could not find job for task")

        # fetch statusses here ...
        processes_states = await self._cloudsend.get_jobs_states(self._run_session)

        # augment the period now ...
        self._sleep_period = SLEEP_PERIOD_LONG

        #update status
        to_remove = []
        for (k,p) in self._processes.items():
            job = p["job"]
            for pstatus in processes_states.values():
                if pstatus['job_config'][JOB_CFG_T_UID] == p["task"].get_prop(TASK_PROP_UID):
                    p["state"] = pstatus['state']
                    break
            
            if p["state"] & ( CloudSendProcessState.DONE | CloudSendProcessState.ABORTED):
                to_remove.append(k)

        # we got some jobs to fetch
        if len(to_remote)>0:
            await self._cloudsend.fetch_results('',self._run_session,True,True)

        # signal completed tasks
        for k in to_remove:
            task = self._processes[k]["task"]
            del self._processes[k]       
            controller.add_completed( task )