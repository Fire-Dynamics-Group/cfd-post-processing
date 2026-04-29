"""Group chart PNG filenames back to their source scenarios.

Charts get saved with the FDS basename (e.g.
0406_Finchley_FS1_Plot80_FSA_*.png). The naive `chart_name.split("_")[0]`
returns the project-number prefix ("0406") which collapses every scenario
in a project into one group — and only SCEN_1_* gets populated in the
report.

These tests pin the correct grouping behaviour."""
from helper_functions import fds_stem_from_scenario_folder, group_charts_by_scenario


# ---- fds_stem_from_scenario_folder ----

def test_stem_finchley_style():
    assert fds_stem_from_scenario_folder(
        '0406_Finchley_FS1_Plot80_FSA.fds_1776875134353_FDS'
    ) == '0406_Finchley_FS1_Plot80_FSA'


def test_stem_legacy_no_fds_suffix():
    assert fds_stem_from_scenario_folder('FS1') == 'FS1'


def test_stem_with_just_fds_extension():
    assert fds_stem_from_scenario_folder('FS1.fds') == 'FS1'


# ---- group_charts_by_scenario ----

def test_finchley_two_scenarios_grouped_correctly():
    chart_names = [
        '0406_Finchley_FS1_Plot80_FSA_devc_cc_pres__chart.png',
        '0406_Finchley_FS1_Plot80_FSA_hrr_chart.png',
        '0406_Finchley_FS1_Plot80_FSA_devc_stair_temp__chart.png',
        '0406_Finchley_FS2_Plot84_FSA_devc_corridor_1_pres__chart.png',
        '0406_Finchley_FS2_Plot84_FSA_hrr_chart.png',
        '0406_Finchley_FS2_Plot84_FSA_devc_lobby_1_temp__chart.png',
    ]
    scenario_names = [
        '0406_Finchley_FS1_Plot80_FSA.fds_1776875134353_FDS',
        '0406_Finchley_FS2_Plot84_FSA.fds_1776932523833_FDS',
    ]
    groups = group_charts_by_scenario(chart_names, scenario_names)
    assert len(groups) == 2
    assert len(groups[0]) == 3 and all('FS1' in c for c in groups[0])
    assert len(groups[1]) == 3 and all('FS2' in c for c in groups[1])


def test_legacy_simple_scenario_names():
    chart_names = ['FS1_devc_cc_temp_chart.png', 'FS2_devc_cc_temp_chart.png']
    scenario_names = ['FS1', 'FS2']
    groups = group_charts_by_scenario(chart_names, scenario_names)
    assert groups[0] == ['FS1_devc_cc_temp_chart.png']
    assert groups[1] == ['FS2_devc_cc_temp_chart.png']


def test_overlapping_prefixes_fs1_vs_fs10_use_underscore_boundary():
    """Without a boundary check, FS1's stem would also match FS10/FS11 charts."""
    chart_names = ['FS1_chart.png', 'FS10_chart.png', 'FS11_chart.png']
    scenario_names = ['FS1', 'FS10', 'FS11']
    groups = group_charts_by_scenario(chart_names, scenario_names)
    assert groups[0] == ['FS1_chart.png']
    assert groups[1] == ['FS10_chart.png']
    assert groups[2] == ['FS11_chart.png']


def test_empty_scenario_names_returns_empty_list():
    assert group_charts_by_scenario(['anything.png'], []) == []


def test_no_charts_returns_empty_lists_per_scenario():
    groups = group_charts_by_scenario([], ['FS1', 'FS2'])
    assert groups == [[], []]


def test_chart_order_within_group_preserved():
    chart_names = ['FS1_b.png', 'FS1_a.png', 'FS1_c.png']
    groups = group_charts_by_scenario(chart_names, ['FS1'])
    assert groups[0] == ['FS1_b.png', 'FS1_a.png', 'FS1_c.png']
