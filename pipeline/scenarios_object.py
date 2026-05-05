from pathlib import Path
import json

from helper_functions import return_paths_to_files, read_from_csv_skip_first_row, get_worst_case_devc, compute_last_time_step_not_tenable, max_or_min_is_worse, find_worst_in_column, get_column_prefix, get_cc_columns
from scen_object_helper_functions import is_sprinklered, find_venting_from_fds, return_scenario_names
from fds_output_utils import find_door_opening_times_with_close_defaults


def _compute_per_prefix_worst_conditions(devc_df, path_to_devc_file, firefighting):
    """Discover unique area prefixes among temp/vis sensors in a devc dataframe
    and compute the worst-case value for each one.

    Returns a tuple (worst_condition, prefix_to_df) where:
      - worst_condition is a dict mapping a stable key per prefix
        (e.g. "stair_temp", "cc_temp", "Lobby_temp", "corridor_1_vis") to a
        scalar float — the worst-case (max for temp, min for vis) reduction
        across all sensors sharing that prefix.
      - prefix_to_df is a dict mapping each discovered prefix to the dataframe
        returned by get_worst_case_devc for that prefix's columns. Callers
        that need the per-prefix worst_case time series (e.g. tenability
        computation in the MoE branch) can use this without re-reading the
        CSV.

    Pressure / velocity / FSA-tagged / sprinkler-tagged columns are skipped
    so that the same logic is safe to call for both MoE and FSA scenarios.
    """
    seen_prefixes = set()
    for column_name in devc_df.columns:
        if column_name == 'Time':
            continue
        col_lower = column_name.lower()
        if not any(param in col_lower for param in ['temp', 'vis']):
            continue
        if 'fsa' in col_lower or 'sprk' in col_lower:
            continue
        seen_prefixes.add(get_column_prefix(column_name))

    worst_condition = {}
    prefix_to_df = {}
    for prefix in seen_prefixes:
        is_stair = 'stair' in prefix.lower()
        is_temp = 'temp' in prefix.lower()
        if is_stair:
            condition_key = 'stair_temp' if is_temp else 'stair_vis'
        else:
            condition_key = prefix.rstrip('_')

        prefix_cols = [c for c in devc_df.columns if c.startswith(prefix)]
        new_df_devc = get_worst_case_devc(
            path_to_file=path_to_devc_file,
            property=prefix.rstrip('_'),
            firefighting=firefighting,
            column_names=prefix_cols,
        )
        worst_condition[condition_key] = find_worst_in_column(
            df=new_df_devc, column_name="worst_case", parameter=prefix.rstrip('_')
        )
        prefix_to_df[prefix] = new_df_devc

    # Combined cc_temp / cc_vis worst-case across all non-stair areas
    # (backward-compat; matches the convenience key used downstream).
    for param in ['temp', 'vis']:
        cc_cols = get_cc_columns(devc_df, param)
        if cc_cols:
            new_df_devc = get_worst_case_devc(
                path_to_file=path_to_devc_file,
                property=param,
                firefighting=firefighting,
                column_names=cc_cols,
            )
            worst_condition[f'cc_{param}'] = find_worst_in_column(
                df=new_df_devc, column_name="worst_case", parameter=param
            )

    return worst_condition, prefix_to_df


# TODO: move below to helper_functions.py
def create_scenario_object(path_to_directory="graph_generation"):
    scenario_names = return_scenario_names(path_to_directory)

    FSA_scenarios = [f for f in scenario_names if "FSA" in f]# filter names for fsa
    MoE_scenarios = [f for f in scenario_names if "FSA" not in f]

    # TODO: move below to helper_functions page
    scenarios_object = {}
    for i in range(len(scenario_names)):
        scen_key = scenario_names[i]
        scenarios_object[scen_key] = {
            "venting": {
                "mech_extract": {"number": [], "flow": []},
                # include supply and aov
                "mech_supply": {"number": [], "flow": []},
                "stair_aov": {"area": []},
                "natural_openings": [], # list areas
                # TODO: include natural inlets to model
            },
            "is_sprinklered": [],
            # TODO: add door opening times
            "door_opening_times": [],
            "end_time": [],
            "tenability": [],
            "min_pressure": []
            # TODO: add run time for sim
        }

        # path_to_directory
        # TODO: have informative error if any of these files are not found
        path_to_hrr_file, path_to_scen_directory, path_to_fds_file, path_to_devc_file, error_list = return_paths_to_files(scenario_name=scen_key, dir_path=path_to_directory, new_folder_structure=True)

        if len(error_list) > 0:
            return scenarios_object, scenario_names, FSA_scenarios, MoE_scenarios, error_list
            # TODO: return error message
            # TODO: don't action rest of function
            # sg.popup_error("Error", '\n\n'.join(error_list))

        if "FSA" in scen_key:
            firefighting = True
        else:
            firefighting = False
        # TODO: obtain max T from devc file
        devc_df = read_from_csv_skip_first_row(path_to_file=path_to_devc_file)
        max_T = devc_df["Time"].max()


    
        extract_rate_list, supply_rate_list, aov_area, extract_count, supply_count, natural_inlet_list = find_venting_from_fds(path_to_file=path_to_fds_file)
        has_sprinklers = is_sprinklered(path_to_file=path_to_fds_file)
        scenarios_object[scen_key]["venting"]["mech_extract"]["number"] = extract_count

        if not extract_rate_list:
            extract_rate = 0
        else:
            extract_rate = float(extract_rate_list[0][0])

        if not supply_rate_list:
            supply_rate = 0
        else:
            supply_rate = float(supply_rate_list[0][0])

        scenarios_object[scen_key]["venting"]["mech_extract"]["flow"] = extract_rate
        scenarios_object[scen_key]["venting"]["mech_extract"]["number"] = extract_count
        scenarios_object[scen_key]["venting"]["mech_supply"]["number"] = supply_count
        scenarios_object[scen_key]["venting"]["mech_supply"]["flow"] = supply_rate
        scenarios_object[scen_key]["venting"]["stair_aov"]["area"] = aov_area
        scenarios_object[scen_key]["venting"]["natural_openings"] = natural_inlet_list
        scenarios_object[scen_key]["is_sprinklered"] = has_sprinklers
        scenarios_object[scen_key]["door_opening_times"] = find_door_opening_times_with_close_defaults(path_to_file=path_to_fds_file)
        scenarios_object[scen_key]["end_time"] = max_T
    #     return({"opening_apartment": opening_apartment[0], "closing_apartment":closing_apartment[-1], "opening_stair":opening_stair[0], "closing_stair":closing_stair[-1]})
        moe_list = ["vis", "temp"]
        tenability_time_list = []
        # fsa_list = ["","" ,"" ] # temp xm
        # TODO: move object creation to scenario_object
        if firefighting==False:
            scenarios_object[scen_key]["worst_condition"] = {
                "stair_temp": [],
                "stair_vis": [],
                "cc_vis": [],
                "cc_temp": []
                }

            worst_condition_map, prefix_to_df = _compute_per_prefix_worst_conditions(
                devc_df=devc_df,
                path_to_devc_file=path_to_devc_file,
                firefighting=firefighting,
            )
            scenarios_object[scen_key]["worst_condition"].update(worst_condition_map)

            # Compute tenability for each prefix's temp/vis worst_case time series
            for prefix, new_df_devc in prefix_to_df.items():
                for current in moe_list:
                    if current in prefix:
                        tenability_time = compute_last_time_step_not_tenable(df=new_df_devc, property=current, worst_case_column_name="worst_case", firefighting=firefighting)
                        tenability_time_list.append(tenability_time)
            closing_apartment = scenarios_object[scen_key]["door_opening_times"]["closing_apartment"]
            tenability_time = max(tenability_time_list) - closing_apartment  # should take-away door closing
            scenarios_object[scen_key]["tenability"] = {"time": tenability_time}
            # min pressure - needed for FSA!!
            current = "pres"
            new_df_devc = get_worst_case_devc(path_to_file=path_to_devc_file, property=current,firefighting=firefighting)
            min_pressure = new_df_devc["worst_case"].min() # 30 secs after door closes??
            scenarios_object[scen_key]["min_pressure"] = min_pressure
        # should trip below for FSA!!!
        else: # if firefighting fsa
            scenarios_object[scen_key]["tenability"] = {
                "2m": [],
                "4m": [],
                "15m": []
                }

            # Mirror the MoE branch: discover every non-stair temp/vis prefix
            # and surface a worst_condition entry per prefix (cc_temp,
            # corridor_1_temp, Lobby_temp, lobby_1_vis, ...) plus the
            # combined cc_temp/cc_vis backward-compat keys. Stair prefixes
            # collapse to the canonical 'stair_temp'/'stair_vis' keys.
            worst_condition_map, _ = _compute_per_prefix_worst_conditions(
                devc_df=devc_df,
                path_to_devc_file=path_to_devc_file,
                firefighting=firefighting,
            )
            scenarios_object[scen_key]["worst_condition"] = worst_condition_map

            door_openings = scenarios_object[scen_key]["door_opening_times"]
            time = door_openings['opening_apartment'] + 30
            temp_index = devc_df['Time'].sub(time).abs().idxmin()

            current = "pres"
            new_df_devc = get_worst_case_devc(path_to_file=path_to_devc_file, property=current,firefighting=firefighting)
            min_pressure = new_df_devc["worst_case"].min()
            scenarios_object[scen_key]["min_pressure"] = min_pressure

            # FSA distance-tagged tenability sensors (e.g. cc_FSA_temp_2m,
            # corridor_1_FSA_temp_15m) populate the 2m/4m/15m tenability
            # entries.
            for column_name in devc_df.columns:
                if 'FSA' in column_name and '_temp_' in column_name:
                    worst_temp = devc_df[column_name][temp_index:].max()
                    fsa_prefix = get_column_prefix(column_name)
                    tenability_key = column_name[len(fsa_prefix):]
                    scenarios_object[scen_key]["tenability"][tenability_key] = worst_temp
    jsonString = json.dumps(scenarios_object)
    jsonFile = open(f"{scenario_names[0]}_etal.json", "w")
    jsonFile.write(jsonString)
    jsonFile.close()
    # 
    return scenarios_object, scenario_names, FSA_scenarios, MoE_scenarios, error_list

if __name__=='__main__':
    path_to_directory = r'C:\Users\IanShaw\Fire Dynamics Group Limited\CFD - Files\Projects CFD\31. Camp Hill Gardens Corridor'
    scenarios_object, scenario_names, FSA_scenarios, MoE_scenarios = create_scenario_object(path_to_directory)