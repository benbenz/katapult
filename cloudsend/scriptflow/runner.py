from scriptflow.runners import AbstractRunner
from cloudsend.provider import get_client

# Runner for tlamadon/scriptflow

class CloudSendRunner(AbstractRunner):

    def __init__(self, conf, handle_task_queue=False):
        self._cloudsend         = get_client(conf)
        self._processes         = {}
        self._num_instances     = 0 
        self._handle_task_queue = handle_task_queue

    def size(self):
        return(len(self._processes))

    def available_slots(self):
        if self._handle_task_queue:
            # always available slots
            # this will cause the controller to add all the tasks at once
            # cloudsend will handle the stacking with the Batch feature ...
            return self._num_instances
        else:
            return self._num_instances - len(self._processes)

    """
        Start tasks
    """

    def add(self, task):

        self._processes[task.hash] = {
            "job":  None , # we have a one-to-one relationship between job and task (no demultiplier)
            "task": task , 
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
        # run the jobs
        await self._cloudsend.run() 

        # cache the number of instances
        self._num_instances = await self._cloudsend.get_num_instances()

        while True:
            await self._update(controller)                
            await asyncio.sleep(0.1)

    async def _update(self,controller):
        to_remove = []
        for (k,p) in self._processes.items():
            # create the job if its not there (it will append/run automatically)

            # else: check the status ...

            pass

        for k in to_remove:
            task = self._processes[k]["task"]
            del self._processes[k]       
            controller.add_completed( task )