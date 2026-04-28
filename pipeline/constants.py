from docx.shared import RGBColor

growthRateObject = {
    "slow": 0.0029,
    "medium": 0.0117,
    "fast": 0.047,
    "ultraFast": 0.188 
  }

font_name_light = 'Segoe UI Light'
font_name_normal = 'Segoe UI'
light_text_color = (0.59,0.56,0.56)
rgb_light_text_color = RGBColor(59,56,56)
chart_config = {        
        "xtick.color": light_text_color,
        "ytick.color": light_text_color,
        "axes.titlecolor": light_text_color,
        "axes.labelcolor": light_text_color,
        "axes.edgecolor": light_text_color,
        "legend.labelcolor": light_text_color,
        "figure.figsize": [6, 4],
        'axes.grid': True,
        'grid.linewidth': '0.05',
        "grid.color": light_text_color
        }

devc_chart_constants = { 
    "cc_pres_": {
        "chart_name": "Pressure",
        "units_abbreviated_for_graph": "Pa",
        "tenable_limit_moe": -60,
        "worst_case": "min"
    },
    "temp_": {
        "chart_name": "Temperature",
        "units_abbreviated_for_graph": "°C",
        "tenable_limit_moe": 60,
        "worst_case": "max",
        "tenable_limit_FSA": {
            "2m": 160,
            "4m": 120,
            "15m": 100
        }
    },
    "vis_": {
        "chart_name": "Visibility",
        "units_abbreviated_for_graph": "m",
        "tenable_limit_moe": 10,
        "worst_case": "min"
    },
    "vel_": {
        "chart_name": "Velocity",
        "units_abbreviated_for_graph": "m/s",
        "tenable_limit_moe": 5, 
        "worst_case": "max"
    },
}

# TODO: use object keys in ref logic
# TODO: future bring in from central spreadshet/csv - allow for update in editions etc
reference_object = {
    "SCA" : {
        "name": "Smoke Control Association document 'Guidance on Smoke Control to Common Escape Routes in Apartment Buildings (Flats and Maisonettes)'"
        },
    "BRegs": {
        "name": "Parts B1 and B5 Building Regulations 2010"
    },
    "9991": {
        "name": "BS 9991"
    }
}