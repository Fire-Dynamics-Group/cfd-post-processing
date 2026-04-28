import math
from helper_functions import devc_chart_constants, round_to

# functions for both bullet points and tables for scenario results summary
def scen_results_values(scenario, scenarios_object, firefighting=False):
    
    if not firefighting:
        tenable_time = scenarios_object[scenario]['tenability']['time'] # applies to bullets # needs access to scenarios object
        max_pressure_drop = scenarios_object[scenario]['min_pressure'] # applies to bullets

        # below applies to bullets
        if tenable_time < 120 and max_pressure_drop > -60:
            meet_criteria = "Yes" 
        else:
            meet_criteria = "NO!!!!" # alert engineer
            # TODO: pop up box?? alert telling which parameters were not tenable

        return tenable_time, max_pressure_drop, meet_criteria

    if firefighting:
        tenable_object = scenarios_object[scenario]["tenability"] # applies to bullets
        tenability_keys = list(tenable_object.keys())   # this and below applies to bullets
        # for each  tenability key
        is_tenable_list = []
        text_list = []
        for index_key in range(len(tenability_keys)):
            key = tenability_keys[index_key]
            current = tenable_object[key]
            
            if not current:
                current = 'N/A'
            else:
                if current < devc_chart_constants["temp_"]["tenable_limit_FSA"][key]:
                    is_tenable_list.append(True)
                else:
                    is_tenable_list.append(False)
                current = f'{round(current)}'
            text_list.append(current)
        # worst conditions in stair
        
        worst_condition_object = scenarios_object[scenario]["worst_condition"] #applies to bullets

        worst_temp = worst_condition_object["stair_temp"] # this and below applies to bullets
        # TODO: Use global object
        if worst_temp < 60:
            is_tenable_list.append(True)
        else:
            is_tenable_list.append(False)                              

        worst_vis = worst_condition_object["stair_vis"]
        if worst_vis > 10:
            is_tenable_list.append(True)
        else:
            is_tenable_list.append(False)  # up to here applies to bullets
                    # use is_tenable_list -> final column
        if any(item is False for item in is_tenable_list): # this and below applies to bullets
            meet_criteria = "NO!!!!"
        else:
            meet_criteria = "Yes"
        max_pressure_drop = scenarios_object[scenario]['min_pressure'] # applies to bullets
        
        if math.isnan(max_pressure_drop):
            max_pressure_drop = 'N/A'
        else:
            max_pressure_drop = round_to(max_pressure_drop)

        return text_list, worst_temp, worst_vis, meet_criteria, max_pressure_drop