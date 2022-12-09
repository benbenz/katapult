# combinatorial optimization

# bin packing
from ortools.linear_solver import pywraplp
from ortools.sat.python import cp_model

# https://developers.google.com/optimization/bin/multiple_knapsack

def multiple_knapsack_assignation(jobs,instances,method='mip'):

    assigned = [False]*len(jobs)

    for i,job in enumerate(jobs):
        if job.get_instance() is not None:
            assigned[i] = True

    while True:

        if method == 'mip':
            res , indexmap = _multiple_knapsack_assignation_pass_MIP(jobs,instances,assigned)

        elif method == 'cp_sat':
            res , indexmap = _multiple_knapsack_assignation_pass_CP_SAT(jobs,instances,assigned)

        for b in range(len(instances)):
            for i in range(len(indexmap)):
                if res[i,b]:
                    assigned[indexmap[i]] = True
                    print("job",indexmap[i],">>>> instance",b)
                    jobs[indexmap[i]].set_instance(instances[b])

        num_assigned = sum(assigned)

        if num_assigned == len(jobs):
            break


def _multiple_knapsack_fill_up_data(jobs,instances,assigned):
    data = {}
    data['weights'] = []
    data['values']  = []
    indexmap = []
    for i,job in enumerate(jobs):
        # the job has already been assigned in a previous pass
        if assigned[i]:
            continue

        cpu_req = job.get_config('cpu_reqs')
        if cpu_req is None:
            cpu_req = 1
        weight = cpu_req
        value  = cpu_req
        # record the mapping
        indexmap.append(i)
        data['weights'].append(weight)
        data['values'].append(value)

    assert len(data['weights']) == len(data['values'])
    data['num_items'] = len(data['weights'])
    data['all_items'] = range(data['num_items'])

    data['bin_capacities'] = []
    for instance in instances:
        cpus = instance.get_config('cpus')
        if cpus is None:
            cpus = 1 #TODO: use the spec from the type ....
        data['bin_capacities'].append(cpus)

    data['num_bins'] = len(data['bin_capacities'])
    data['all_bins'] = range(data['num_bins'])
    return data , indexmap

# THIS ONE is Seg Faulting ???

def _multiple_knapsack_assignation_pass_MIP(jobs,instances,assigned):

    # FILL UP the data

    data , indexmap = _multiple_knapsack_fill_up_data(jobs,instances,assigned)

   
    # DECLARE the Solver

    solver = pywraplp.Solver.CreateSolver('SCIP')
    if solver is None:
        print('SCIP solver unavailable.')
        return 

    
    # CREATE the variables

    # x[i, b] = 1 if item i is packed in bin b.
    x = {}
    for i in data['all_items']:
        for b in data['all_bins']:
            x[i, b] = solver.BoolVar(f'x_{i}_{b}')

    
    # DEFINE the constraints

    # Each item is assigned to at most one bin.
    for i in data['all_items']:
        solver.Add(sum(x[i, b] for b in data['all_bins']) <= 1)

    # The amount packed in each bin cannot exceed its capacity.
    for b in data['all_bins']:
        solver.Add(
            sum(x[i, b] * data['weights'][i]
                for i in data['all_items']) <= data['bin_capacities'][b])    


    # DEFINE the objective

    # Maximize total value of packed items.
    objective = solver.Objective()
    for i in data['all_items']:
        for b in data['all_bins']:
            objective.SetCoefficient(x[i, b], data['values'][i])
    objective.SetMaximization()    

    status = solver.Solve()

    # PRINT the solution 

    result = {}

    if status == pywraplp.Solver.OPTIMAL:
        #print(f'Total packed value: {objective.Value()}')
        total_weight = 0
        for b in data['all_bins']:
            #print(f'Bin {b}')
            bin_weight = 0
            bin_value = 0
            for i in data['all_items']:
                if x[i, b].solution_value() > 0:
                    #print(
                    #    f"Item {i} weight: {data['weights'][i]} value: {data['values'][i]}"
                    #)
                    bin_weight += data['weights'][i]
                    bin_value += data['values'][i]
                    result[i,b] = True
                else:
                    result[i,b] = False
            #print(f'Packed bin weight: {bin_weight}')
            #print(f'Packed bin value: {bin_value}\n')
            total_weight += bin_weight
        #print(f'Total packed weight: {total_weight}')
    else:
        print('The problem does not have an optimal solution.')    

    return result , indexmap 

def _multiple_knapsack_assignation_pass_CP_SAT(jobs,instances,assigned):

    # DECLARE the model

    model = cp_model.CpModel()

    # CREATE the data

    data , indexmap = _multiple_knapsack_fill_up_data(jobs,instances,assigned)

    # CREATE the variables

    # x[i, b] = 1 if item i is packed in bin b.
    x = {}
    for i in data['all_items']:
        for b in data['all_bins']:
            x[i, b] = model.NewBoolVar(f'x_{i}_{b}')

    # ADD constraints 
    # Each item is assigned to at most one bin.
    for i in data['all_items']:
        model.AddAtMostOne(x[i, b] for b in data['all_bins'])

    # The amount packed in each bin cannot exceed its capacity.
    for b in data['all_bins']:
        model.Add(
            sum(x[i, b] * data['weights'][i]
                for i in data['all_items']) <= data['bin_capacities'][b])

    # Objective.
    # Maximize total value of packed items.
    objective = []
    for i in data['all_items']:
        for b in data['all_bins']:
            objective.append(
                cp_model.LinearExpr.Term(x[i, b], data['values'][i]))
    model.Maximize(cp_model.LinearExpr.Sum(objective))

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    result = {}

    if status == cp_model.OPTIMAL:
        #print(f'Total packed value: {solver.ObjectiveValue()}')
        total_weight = 0
        for b in data['all_bins']:
            #print(f'Bin {b}')
            bin_weight = 0
            bin_value = 0
            for i in data['all_items']:
                if solver.Value(x[i, b]) > 0:
                    #print(
                    #    f"Item {i} weight: {data['weights'][i]} value: {data['values'][i]}"
                    #)
                    bin_weight += data['weights'][i]
                    bin_value += data['values'][i]
                    result[i,b] = True
                else:
                    result[i,b] = False
            #print(f'Packed bin weight: {bin_weight}')
            #print(f'Packed bin value: {bin_value}\n')
            total_weight += bin_weight
        #print(f'Total packed weight: {total_weight}')
    else:
        print('The problem does not have an optimal solution.')

    return result , indexmap
