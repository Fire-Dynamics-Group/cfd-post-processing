import re
import pandas as pd
import numpy as np
from constants import devc_chart_constants
from pathlib import Path
# from scen_object_helper_functions import find_all_files_of_type
import os
from os import listdir, scandir
from pathlib import Path

def get_column_prefix(column_name):
    """Strip trailing device number to get column prefix.
    e.g. corridor_1_temp_1 -> corridor_1_temp_
         cc_FSA_temp_2m -> cc_FSA_temp_
         stair_temp_1 -> stair_temp_
    """
    return re.sub(r'_\d+m?$', '_', column_name)


def get_cc_columns(devc_df, param):
    """Return all non-stair, non-FSA column names for a given parameter type (temp/vis/pres/vel).
    These are the common corridor/lobby columns used for MOE worst-case."""
    results = []
    for col in devc_df.columns:
        if col == 'Time':
            continue
        col_lower = col.lower()
        if f'_{param}' not in col_lower and not col_lower.startswith(f'{param}_'):
            # Check if param appears as a segment: e.g. _temp_ in corridor_1_temp_1
            if f'{param}_' not in col_lower:
                continue
        if 'stair' in col_lower or 'fsa' in col_lower:
            continue
        results.append(col)
    return results


def return_all_subfolders(path_to_dir):
    return [ f.name for f in scandir(path_to_dir) if f.is_dir() ]

    return [ item for item in os.listdir(path_to_dir) if os.path.isdir(os.path.join(path_to_dir, item)) ]

def return_paths_to_files(scenario_name, dir_path='graph_generation', new_folder_structure=False):
    error_list = []
    if new_folder_structure == False:
        path_to_scen_directory = f'./{dir_path}/{scenario_name}/Graph_{scenario_name}'
        path_to_fds_file = f'{path_to_scen_directory}/Graph_{scenario_name}.fds'
        path_to_devc_file = f'{path_to_scen_directory}/Graph_{scenario_name}_devc.csv'
        path_to_hrr_file = f'graph_generation\{scenario_name}\Graph_{scenario_name}\Graph_{scenario_name}_hrr.csv'

    else:
        # check if any nested folders; if not don't add scenario_name
        trial_path = f'{dir_path}/{scenario_name}'
        if os.path.exists(trial_path):
            path_to_scen_directory = trial_path
        else:
            # checks if pointed directly towards the folder with one run only, no subfolders
            path_to_scen_directory = dir_path
        # TODO: check if intermediate folder
        has_nested_folder = return_all_subfolders(path_to_scen_directory)
        if len(has_nested_folder) > 0: # should error if more than one folder
            path_to_scen_directory += f'/{has_nested_folder[0]}'
            if len(has_nested_folder) > 1:
                error_list.append(f"More than one folder found in {path_to_scen_directory} for scenario:{scenario_name}. Please remove non relevant folders.") 

        fds_name = find_all_files_of_type(path_to_directory=path_to_scen_directory, suffix=".fds")
        if len(fds_name) == 0:
            error_list.append(f"No fds file found in {path_to_scen_directory} for scenario:{scenario_name}. Please add fds file.")
            fds_name = 'error'
        else:
            fds_name = fds_name[0]
        devc_name = find_all_files_of_type(path_to_directory=path_to_scen_directory, suffix="devc.csv")
        if len(devc_name) > 0 :
            devc_name = devc_name[0]
        else:
            error_list.append(f"No devc file found in {path_to_scen_directory} for scenario:{scenario_name}. Please add devc file.")
            devc_name = 'error'
        hrr_name = find_all_files_of_type(path_to_directory=path_to_scen_directory, suffix="hrr.csv")
        if len(hrr_name) > 0 :
            hrr_name = hrr_name[0]
        else:
            error_list.append(f"No hrr file found in {path_to_scen_directory} for scenario:{scenario_name}. Please add hrr file.")
            hrr_name = 'error'

        # find all files - ones with x and y ending
        path_to_hrr_file = f'{path_to_scen_directory}/{hrr_name}'
        path_to_fds_file = f'{path_to_scen_directory}/{fds_name}'
        path_to_devc_file = f'{path_to_scen_directory}/{devc_name}'

    return path_to_hrr_file, path_to_scen_directory, path_to_fds_file, path_to_devc_file, error_list

def find_all_files_of_type(path_to_directory, suffix=".csv"):
    filenames = listdir(path_to_directory)
    return [ f for f in filenames if f.endswith( suffix )]

# TODO: move to misc utils
def round_to(value, closest_to=0.1):
        return round(value, 1) 

def filter_dataframe_by_column_starting_with_string(df, string):
    return df.loc[:, df.columns.str.startswith(string)]

def filter_dataframe_by_column_contains_string(df, string):
    return df.loc[:, df.columns.str.contains(string)]

def find_worst_case_column_name(worst_case_max_or_min, column_names, df, is_stair=False, firefighting=False):
    # "Stair mode" produces TWO worst_case columns (worst_case + worst_case_b)
    # by sorting the stair sensors by their trailing device number and
    # bisecting them into a lower-stair / upper-stair safety zone pair.
    # It engages ONLY when *all* columns are stair sensors; mixed sets fall
    # through to a single worst_case computation.
    column_names = list(column_names)
    new_df = df.copy()

    if len(column_names) == 0:
        return new_df

    is_stair = all("stair" in c for c in column_names)

    def return_worst_case_column(worst_case_label, new_df, cols):
        if worst_case_max_or_min == "min":
            new_df[worst_case_label] = new_df[cols].min(axis=1)
        else:
            new_df[worst_case_label] = new_df[cols].max(axis=1)
        return new_df

    if is_stair:
        # Sort by the trailing integer device number, tolerant of leading
        # zeros (stair_temp_01) and gaps in numbering (01, 02, 03, 05, 06, 08).
        def trailing_int(name):
            m = re.search(r'_(\d+)m?$', name)
            return int(m.group(1)) if m else float('inf')
        ordered = sorted(column_names, key=trailing_int)
        half = len(ordered) // 2
        new_df = return_worst_case_column("worst_case",   new_df, ordered[:half])
        new_df = return_worst_case_column("worst_case_b", new_df, ordered[half:])
    else:
        new_df = return_worst_case_column("worst_case", new_df, column_names)
    return new_df


def get_worst_case_devc(path_to_file, property="temp", firefighting=False, column_names=None):
    devc_df = read_from_csv_skip_first_row(path_to_file)
    devc_keys = devc_chart_constants.keys()
    current = property
    if column_names is None:
        data_columns = filter_dataframe_by_column_contains_string(devc_df, current)
        column_names = list(data_columns.columns)
    if any(current in x for x in devc_keys):
        current_key = [f for f in devc_keys if current in f][0]
    else:
    # do temp and vis for moe
        current_key = [f for f in devc_keys if f[:-1] in current][0]

    column_config = devc_chart_constants[current_key]
    new_df = find_worst_case_column_name(
    worst_case_max_or_min=column_config["worst_case"],
    column_names=column_names,
    df=devc_df
)
    return new_df
def find_current_devc_key(current):
    devc_keys = devc_chart_constants.keys()
    if any(current in x for x in devc_keys):
        current_key = [f for f in devc_keys if current in f][0]
    else:
    # do temp and vis for moe
        current_key = [f for f in devc_keys if f[:-1] in current][0]
    return current_key

def find_column_config(parameter):
    key = find_current_devc_key(current=parameter)
    column_config = devc_chart_constants[key]
    return column_config

def max_or_min_is_worse(parameter):
    column_config = find_column_config(parameter)
    max_or_min = column_config["worst_case"]
    return max_or_min

def find_worst_in_column(df, column_name, parameter):
    max_or_min = max_or_min_is_worse(parameter)
    if max_or_min == "max":
        return df[column_name].max()
    else:
        return df[column_name].min()

def compute_last_time_step_not_tenable(df, property="temp",worst_case_column_name="worst_case", firefighting=False):
    column_config = find_column_config(property)
    # get tenable limit
    if firefighting:
        return 0
    # only for moe
    tenable_limit = column_config["tenable_limit_moe"]

    # use max or min
    max_or_min = column_config[worst_case_column_name]
    if max_or_min == "max":
       df["is_worse"] = np.where(df[worst_case_column_name] > tenable_limit,
       True,
       False) 
    if max_or_min == "min":
       df["is_worse"] = np.where(df[worst_case_column_name] < tenable_limit,
       True,
       False) 
    print(df["is_worse"])
    # find last true
    # scope if only false
    last_time_step_untenable = df.where(df["is_worse"]).last_valid_index()
    if last_time_step_untenable and last_time_step_untenable < (len(df["is_worse"])-1):

        tenability_step = last_time_step_untenable + 1
        time_tenable = df["Time"][tenability_step]
        return time_tenable
    else:
        return 0
    # then return last time step when true + 1 timestep
        # df["is_worse"] = df.worst_case.apply(lambda x: True if x >= tenable_limit)
    # get from last entry forwards first worse than that
    # add 1 timestep

    # print(df)
def read_from_csv_skip_first_row(path_to_file, rows_to_skip=[0]):
    return pd.read_csv(path_to_file, skiprows=rows_to_skip)





# \graph_generation\FSA_Test\Graph_FSA_Test\
