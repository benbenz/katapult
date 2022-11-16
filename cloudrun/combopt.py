# combinatorial optimization

# bin packing
from ortools.linear_solver import pywraplp

# https://developers.google.com/optimization/bin/multiple_knapsack

def multiple_knapsack_assignation(jobs,instances):

    # FILL UP the data

    data = {}
    data['weights'] = []
    data['values']  = []
    for job in jobs:
        cpu_req = job.get_config('cpu_reqs')
        if cpu_req is None:
            cpu_req = 1
        weight = cpu_req
        value  = cpu_req
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

    if status == pywraplp.Solver.OPTIMAL:
        print(f'Total packed value: {objective.Value()}')
        total_weight = 0
        for b in data['all_bins']:
            print(f'Bin {b}')
            bin_weight = 0
            bin_value = 0
            for i in data['all_items']:
                if x[i, b].solution_value() > 0:
                    print(
                        f"Item {i} weight: {data['weights'][i]} value: {data['values'][i]}"
                    )
                    bin_weight += data['weights'][i]
                    bin_value += data['values'][i]
            print(f'Packed bin weight: {bin_weight}')
            print(f'Packed bin value: {bin_value}\n')
            total_weight += bin_weight
        print(f'Total packed weight: {total_weight}')
    else:
        print('The problem does not have an optimal solution.')    