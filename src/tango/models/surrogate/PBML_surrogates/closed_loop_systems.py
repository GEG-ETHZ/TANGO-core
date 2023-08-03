import numpy as np
import matplotlib.pyplot as plt
import joblib
import CoolProp
import CoolProp.CoolProp as CP
import os
import numpy as np

# Get the current working directory
current_directory = os.getcwd()

# Define the relative path to the training data folder from the current directory
training_data_folder = "../../../../PBML_surrogates"
basis_models_folder = "Basis_fts_and_models"

# Create the full absolute path to the training parameters file
parameters_file = os.path.join(current_directory, training_data_folder, "CO2-AGS", "training_parameters.npy")

# Load unscaled parameters
training_parameters = np.load(parameters_file)[:,:]
mean = np.mean(training_parameters, axis=0)
var = np.var(training_parameters, axis=0)

# Define the relative paths to the training data files from the current directory
h2o_ags_folder = os.path.join(current_directory, training_data_folder, "H2O-AGS")
co2_ags_folder = os.path.join(current_directory, training_data_folder, "CO2-AGS")
basis_models_path = os.path.join(current_directory, training_data_folder, basis_models_folder)


# Load training data for H2O-AGS
heat_AGS = np.load(os.path.join(h2o_ags_folder, "Heat_production_Training.npy"))
ProdPress_AGS = np.load(os.path.join(h2o_ags_folder, "Production_pressure_Training.npy"))
ProdTemp_AGS = np.load(os.path.join(h2o_ags_folder, "Production_temperature_Training.npy"))

# Load training data for CO2-AGS
heat_CO2_AGS = np.load(os.path.join(co2_ags_folder, "Heat_production_Training.npy"))
ProdPress_CO2_AGS = np.load(os.path.join(co2_ags_folder, "Production_pressure_Training.npy"))
ProdTemp_CO2_AGS = np.load(os.path.join(co2_ags_folder, "Production_temperature_Training.npy"))


# BASIS FUNCTIONS AND MODELS
# H2O-AGS: Heat production, Production pressure and Production Temperature
heat_AGS_basis_fts = np.load(os.path.join(basis_models_path, "HeatProduction_AGS_Surrogate_BasisFunctions.npy"))
heat_AGS_model = joblib.load(os.path.join(basis_models_path, "GPR_HeatProduction_H2O-AGS.joblib"))

ProdPress_AGS_basis_fts = np.load(os.path.join(basis_models_path,"ProductionPressure_AGS_Surrogate_BasisFunctions.npy"))
ProdPress_AGS_model = joblib.load(os.path.join(basis_models_path, "GPR_ProductionPressure_H2O-AGS.joblib"))

ProdTemp_AGS_basis_fts = np.load(os.path.join(basis_models_path,"ProductionTemperature_AGS_Surrogate_BasisFunctions.npy"))
ProdTemp_AGS_model = joblib.load(os.path.join(basis_models_path, "GPR_ProductionTemperature_H2O-AGS.joblib"))

# CO2-AGS: Heat production and Production pressure
heat_CO2_AGS_basis_fts = np.load(os.path.join(basis_models_path,"HeatProduction_CO2-AGS_Surrogate_BasisFunctions.npy"))
heat_CO2_AGS_model =  joblib.load(os.path.join(basis_models_path, "GPR_HeatProduction_CO2-AGS.joblib"))

ProdPress_CO2_AGS_basis_fts = np.load(os.path.join(basis_models_path,"ProductionPressure_CO2-AGS_Surrogate_BasisFunctions.npy"))
ProdPress_CO2_AGS_model =  joblib.load(os.path.join(basis_models_path, "GPR_ProductionPressure_CO2-AGS.joblib"))

ProdTemp_CO2_AGS_basis_fts = np.load(os.path.join(basis_models_path,"ProductionTemperature_CO2-AGS_Surrogate_BasisFunctions.npy"))
ProdTemp_CO2_AGS_model =  joblib.load(os.path.join(basis_models_path, "GPR_ProductionTemperature_CO2-AGS.joblib"))


# Import time array from the Matlab script (originally in seconds = 30 years)
times_SBT_surrogates = np.array([0,100,200,300,400,500,600,700,800,900,1000,1100,1200,1300,1400,1500,1600,1700,1800,1900,2000,2100,2200,2300,2400,2500,2600,2700,2800,2900,3000,3100,3200,3300,3400,3500,3600,3700,3800,3900,4000,4100,4200,4300,4400,4500,4600,4700,4800,4900,5000,5100,5200,5300,5400,5500,5600,5700,5800,5900,6000,6100,6200,6300,6400,6500,6600,6700,6800,6900,7000,7100,7200,7300,7400,7500,7600,7700,7800,7900,8000,8100,8200,8300,8400,8500,8600,8700,8800,8900,9000,9100,9200,9300,9400,9500,9600,9700,9800,9900,10000,11226.95282,12604.44696,14150.95314,15887.20832,17836.49383,20024.94747,22481.91405,25240.33884,28337.20933,31814.05122,35717.48521,40099.85213,45019.91479,50543.64594,56745.11283,63707.47045,71524.07651,80299.74325,90152.14289,101213.3855,113631.7904,127573.8749,143226.5875,160799.8141,180529.1926,202679.2728,227547.0633,255466.0145,286810.4892,322000.783,361508.7599,405864.1792,455661.7991,511569.352,574336.498,644804.8766,723919.3928,812740.8869,912460.3592,1024414.94,1150105.82,1291218.378,1449644.781,1627509.357,1827197.076,2051385.537,2303080.864,2585658.02,2902906.06,3259078.938,3658952.548,4107888.762,4611907.333,5177766.604,5813054.137,6526288.454,7327033.257,8226025.669,9235320.208,10368450.43,11640610.38,13068858.35,14672345.61,16472573.19,18493680.21,20762767.52,23310261.13,26170320.2,29381295.01,32986241.29,37033497.47,41577332.89,46678675.47,52405928.72,58835888.93,66054774.92,74159384.15,83258390.71,93473802.44,104942597,117818558.5,132274339.8,148503777.2,166724490.1,187180798.4,210146999.2,235931044.6,264878670.6,297378033.8,333864915.6,374828565.6,420818262.1,472450677.5,530418146.6,595497950.7,668562739.7,750592233.6,842686359.5,946080000])
times_SBT_years = times_SBT_surrogates/3.14e7

def surrogate_solution(mu_online, model, basis_fts_matrix):
    """This function executes the online stage of the non-instrusive RB method.
#
#    Args:
#        mu_online = parameters for the online solve
#        number_of_variables = number_of_variables
#
#    """
    #print('Predicting the reduced coefficients:')
    # Compute reduced coefficients
    rb_coeff = model.predict(mu_online)

    #print('Projecting the reduced solution onto the high-dimensional space...')
    # Project to full space
    full_solutions = np.dot(rb_coeff, basis_fts_matrix)

    return full_solutions[:,0,:]


def store_surrogate_solutions(variable="heat", fluid="H2O", depth=4000, GeoGrad=40, NumLaterals=5, Well_spacing=1000,
                              m_dot=80, P_inj=100, k_r=3.0, Cp_r=1000, rho_r=2700, T_surf=20,
                              T_inj=20, Well_diam=0.27, Grid=True):
    model_heat = None
    basis_fts_heat = None
    model_ProdPress = None
    basis_fts_ProdPress = None

    if fluid == "H2O":
        text = "AGS"
        fluid_color = "dodgerblue"
        data_heat = globals()["heat_" + text]
        min_heat = np.min(data_heat)
        max_heat = np.max(data_heat)
        basis_fts_heat = globals()["heat_" + text + "_basis_fts"]
        model_heat = globals()["heat_" + text + "_model"]

        data_ProdPress = globals()["ProdPress_" + text]
        min_PP = np.min(data_ProdPress)
        max_PP = np.max(data_ProdPress)
        basis_fts_ProdPress = globals()["ProdPress_" + text + "_basis_fts"]
        model_ProdPress = globals()["ProdPress_" + text + "_model"]

        data_ProdTemp = globals()["ProdTemp_" + text]
        min_ProdTemp = np.min(data_ProdTemp)
        max_ProdTemp = np.max(data_ProdTemp)
        basis_fts_ProdTemp = globals()["ProdTemp_" + text + "_basis_fts"]
        model_ProdTemp = globals()["ProdTemp_" + text + "_model"]

    elif fluid == "CO2":
        text = "CO2_AGS"
        fluid_color = "darkgreen"
        data_heat = globals()["heat_" + text]
        min_heat = np.min(data_heat)
        max_heat = np.max(data_heat)
        basis_fts_heat = globals()["heat_" + text + "_basis_fts"]
        model_heat = globals()["heat_" + text + "_model"]

        data_ProdPress = globals()["ProdPress_" + text]
        min_PP = np.min(data_ProdPress)
        max_PP = np.max(data_ProdPress)
        basis_fts_ProdPress = globals()["ProdPress_" + text + "_basis_fts"]
        model_ProdPress = globals()["ProdPress_" + text + "_model"]

        data_ProdTemp = globals()["ProdTemp_" + text]
        min_ProdTemp = np.min(data_ProdTemp)
        max_ProdTemp = np.max(data_ProdTemp)
        basis_fts_ProdTemp = globals()["ProdTemp_" + text + "_basis_fts"]
        model_ProdTemp = globals()["ProdTemp_" + text + "_model"]

    # CALCULATING THE SOLUTION
    # Assign parameters locally from function's input
    params = [[depth, GeoGrad, NumLaterals, Well_spacing, m_dot, P_inj, k_r, Cp_r, rho_r, T_surf, T_inj, Well_diam]]
    # Perform normal scaling on the online parameters based on training parameters.
    scaled_params = (params - mean) / (np.sqrt(var))
    # Calculate surrogate solutions
    heat_sol = surrogate_solution(scaled_params, model_heat, basis_fts_heat)
    ProdPress_sol = surrogate_solution(scaled_params, model_ProdPress, basis_fts_ProdPress)
    ProdTemp_sol = surrogate_solution(scaled_params, model_ProdTemp, basis_fts_ProdTemp)

    heat_unscaled_sol = heat_sol[0, :] * (max_heat - min_heat) + min_heat
    ProdPress_unscaled_sol = ProdPress_sol[0, :] * (max_PP - min_PP) + min_PP
    ProdTemp_unscaled_sol = ProdTemp_sol[0, :] * (max_ProdTemp - min_ProdTemp) + min_ProdTemp

    full_solution = locals()[variable + "_unscaled_sol"]

    if variable == "heat":
        units = "MWth"

    elif variable == "ProdTemp":
        units = "degC"

    elif variable == "ProdPress":
        units = "bar"

    print("Success")
    print("PB-ML surrogate solution for " + variable + " in " + units + " using "+fluid+ " as the subsurface working fluid has been saved")
    #print(full_solution)
    return full_solution


# ----------------------------------------------

# prod_temperatures = store_surrogate_solutions(variable = "ProdTemp", fluid = "CO2", depth = 4000, GeoGrad = 40, NumLaterals = 5, Well_spacing = 1000,
#                              m_dot = 80, P_inj = 100, k_r = 3.0 , Cp_r = 1000, rho_r = 2700, T_surf = 20,
#                              T_inj = 20, Well_diam = 0.27)
#
# prod_pressures = store_surrogate_solutions(variable = "ProdPress", fluid = "CO2", depth = 4000, GeoGrad = 40, NumLaterals = 5, Well_spacing = 1000,
#                              m_dot = 80, P_inj = 100, k_r = 3.0 , Cp_r = 1000, rho_r = 2700, T_surf = 20,
#                              T_inj = 20, Well_diam = 0.27)
#
# prod_enthalpies = []
# for T, P in zip(prod_temperatures, prod_pressures):
#     enthalpy = CP.PropsSI("HMASS", "T", T+273.15, "P", P*1e5, "CO2")
#     prod_enthalpies.append(enthalpy)
#


# ---------------------


def plot_electricity_output(fluid, depth, GeoGrad, NumLaterals, Well_spacing,
                            m_dot, P_inj, k_r, Cp_r, rho_r, T_surf,
                            T_inj, Well_diam):

    ## CONSTANT (REINJECTION) BOUNDARY CONDITIONS
    m_dot = m_dot  # kg/s             Mass flow rate
    T_inj_K = T_inj + 273.15  # K     Reinjection temperature
    P_inj_Pa = P_inj * 1e5  # Pa    Reinjection pressure

    inj_enthalpy = CP.PropsSI("HMASS", "T", T_inj_K, "P", P_inj_Pa, "CO2")  # Reinjection enthalpy

    prod_temperatures = store_surrogate_solutions(variable="ProdTemp", fluid=fluid, depth=depth, GeoGrad=GeoGrad,
                                                  NumLaterals=NumLaterals, Well_spacing=Well_spacing,
                                                  m_dot=m_dot, P_inj=P_inj, k_r=k_r, Cp_r=Cp_r, rho_r=rho_r,
                                                  T_surf=T_surf,
                                                  T_inj=T_inj, Well_diam=Well_diam)

    prod_pressures = store_surrogate_solutions(variable="ProdPress", fluid=fluid, depth=depth, GeoGrad=GeoGrad,
                                               NumLaterals=NumLaterals, Well_spacing=Well_spacing,
                                               m_dot=m_dot, P_inj=P_inj, k_r=k_r, Cp_r=Cp_r, rho_r=rho_r, T_surf=T_surf,
                                               T_inj=T_inj, Well_diam=Well_diam)

    prod_enthalpies = []
    for T, P in zip(prod_temperatures, prod_pressures):
        enthalpy = CP.PropsSI("HMASS", "T", T + 273.15, "P", P * 1e5, "CO2")
        prod_enthalpies.append(enthalpy)

    enthalpy_drop = np.array(prod_enthalpies) - inj_enthalpy


    if fluid == "CO2":
        print("CO2-based electricity generation calculated using an direct CO2 turbine with isentropic expansion")

        turbine_eff = 0.78  # (-) Efficiency of an isentropic CO2 turbine  (Adams et al, 2015)

        electricity_output = m_dot * enthalpy_drop * turbine_eff  # in We
        electricity_output_MWe = electricity_output / 1e6  # in MWe

        plt.ylabel("Electricity production (MWe)")
        plt.xlabel("Time (years)")
        plt.plot(times_SBT_years, electricity_output_MWe)
        plt.show()

    elif fluid == "H2O":
        # TODO Implement water-based electricity generation via a binary cycle (ORC power plant)
        print("Water-based electricity generation calculated using an idealized ORC plant")


plot_electricity_output(fluid = "CO2", depth = 7000, GeoGrad = 50, NumLaterals = 5, Well_spacing = 1000,
                             m_dot = 30, P_inj = 100, k_r = 3.0 , Cp_r = 1000, rho_r = 2700, T_surf = 20,
                             T_inj = 20, Well_diam = 0.27)




# LIST OF PARAMETERS AND UNITS

# fluid = H2O or CO2
# depth = Reservoir's central depth [m],
# GeoGradient = Geothermal gradient [degC/km],
# NumLaterals = Number of laterals [-],
# Well_spacing = Separation distance of vertical well segments [m],
# m_dot = Mass flow rate [kg/s],
# P_inj = Injection pressure [bar]
# k_r = Thermal conductivity [W / m K],
# Cp_r = Specific Heat capacity [J / kg K] ,
# rho_r = Rock density [kg / m3],
# T_surf = Surface temperature [degC],
# T_inj = Reinjection temperature [degC],
# Well_diam = Well pipe diameter of both vertical and horizontal segments [m]
