import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
import yaml
import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path

ELECTRICITY_PRICE_SCALE = 3.0
SALE_ELECTRICITY_PRICE_SCALE = 3.0
HOTMAPS_DISPATCH_DIR = "/home/morteza/projects/hotmapsDispatch"
OUTPUT_DIR = "/home/morteza/projects/TANGO/examples"
HOTMAPS_CONDA_ENV = "hotmapsDispatch"

SHEET_COLORS = {
    "Heat Generators": "DAEEF3",
    "Heat Storage": "FCE4D6",
    "Data": "FFF2CC",
    "Energy Carrier": "DDEBF7"
}

class ExcelGenerator:
    def __init__(self, yaml_file, results=None, specs=None, thermal_power=None):
        self.yaml_file = yaml_file
        self.config = self._load_yaml() if yaml_file else {}
        self.wb = openpyxl.Workbook()
        self.wb.properties.creator = "YAML Excel Generator"
        self.wb.properties.title = os.path.basename(yaml_file).split('.')[0] if yaml_file else "Generated"
        self.wb.properties.created = datetime.now()
        self.results = results
        self.specs = specs
        self.thermal_power = thermal_power

    def _load_yaml(self):
        if not self.yaml_file:
            return {}
        try:
            with open(self.yaml_file, 'r', encoding='utf-8') as file:
                content = file.read()
                # Validate YAML format before loading
                self._validate_yaml_format(content)
                config = yaml.safe_load(content)

                # Additional validation: ensure all 'values' are lists or convert None to []
                if config and 'modules' in config:
                    for module in config['modules']:
                        if 'fields' in module:
                            for field in module['fields']:
                                if 'values' in field and field['values'] is None:
                                    field['values'] = []

                return config
        except Exception as e:
            print(f"Error loading YAML file: {e}")
            sys.exit(1)

    def _validate_yaml_format(self, content):
        """Validate YAML content and detect common formatting errors"""
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.strip().count("values:") > 1:
                print(f"Warning: Line {i+1} contains multiple 'values:' entries.")
                print(f"Problematic line: {line}")
                raise ValueError(f"Invalid YAML: Line {i+1} contains multiple 'values:' entries.")

            if i > 0 and line.strip().startswith("- key:") and not line.startswith(" "):
                print(f"Warning: Line {i+1} contains a 'key:' entry without proper indentation.")
                print(f"Problematic line: {line}")
                raise ValueError(f"Invalid YAML: Line {i+1} 'key:' entry needs proper indentation.")

    def create_excel(self):
        if self.wb.active:
            self.wb.remove(self.wb.active)

        original_output_file = getattr(self.specs, 'output_file', 'fff.xlsx')
        output_file_path = os.path.join(OUTPUT_DIR, os.path.basename(original_output_file))

        for module_config in self.config.get('modules', []):
            self._create_sheet(module_config)

        if len(self.wb.worksheets) == 0:
            self.wb.create_sheet("Default Sheet")
            print("Created default sheet since no modules were specified in YAML")

        self._add_custom_rows()

        try:
            self.wb.save(output_file_path)
            print(f"Excel file '{output_file_path}' has been created successfully.")
            return output_file_path
        except Exception as e:
            print(f"Error saving Excel file: {e}")
            sys.exit(1)

    def _create_sheet(self, module_config):
        sheet_name = module_config.get('label', 'Sheet')
        sheet = self.wb.create_sheet(sheet_name)
        fields = module_config.get('fields', [])

        max_rows = 0
        if fields:
            for field in fields:
                values = field.get('values', [])
                if values is None:
                    values = []
                max_rows = max(max_rows, len(values))

        self._create_id_column(sheet, max_rows)
        self._create_columns(sheet, fields, sheet_name, max_rows)
        self._adjust_column_widths(sheet)
        sheet.freeze_panes = sheet.cell(row=2, column=1)

    def _create_id_column(self, sheet, max_rows):
        cell = sheet.cell(row=1, column=1)
        cell.value = "ID"
        self._style_header(cell, sheet.title)

        for row_idx in range(max_rows):
            cell = sheet.cell(row=row_idx+2, column=1)
            cell.value = row_idx
            self._style_data(cell)

    def _create_columns(self, sheet, fields, sheet_name, max_rows):
        col_idx = 2
        for field in fields:
            key = field.get('key')
            values = field.get('values', [])
            if values is None:
                values = []

            if key is not None:
                cell = sheet.cell(row=1, column=col_idx)
                cell.value = key
                self._style_header(cell, sheet_name)

            for row_idx, value in enumerate(values, 2):
                cell = sheet.cell(row=row_idx, column=col_idx)
                cell.value = value
                self._style_data(cell)

            col_idx += 1

    def _style_header(self, cell, sheet_name):
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        self._add_border(cell)

        # Determine fill color
        fill_color = None
        for key, color in SHEET_COLORS.items():
            if key in sheet_name:
                fill_color = color
                break

        if not fill_color:
            if any(term in sheet_name.lower() for term in ["prices", "emission"]):
                fill_color = "EBF1DE"
            else:
                fill_color = "E6F2FF"

        cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")

    def _style_data(self, cell):
        self._add_border(cell)
        if isinstance(cell.value, (int, float)):
            cell.number_format = "#,##0" if cell.value == int(cell.value) else "#,##0.00"

    def _add_border(self, cell):
        thin_border = Side(style="thin")
        cell.border = Border(top=thin_border, right=thin_border, bottom=thin_border, left=thin_border)

    def _adjust_column_widths(self, sheet):
        for column in sheet.columns:
            max_length = 0
            column_letter = column[0].column_letter

            for cell in column:
                if cell.value:
                    try:
                        max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass

            adjusted_width = max(max_length + 2, 10)
            sheet.column_dimensions[column_letter].width = adjusted_width

    def _add_custom_rows(self):
        self._add_custom_row("Heat Generators", self._get_heat_generator_values)
        self._add_custom_row("Energy Carrier", self._get_energy_carrier_values)

    def _add_custom_row(self, sheet_keyword, value_getter):
        sheet = None
        for ws in self.wb.worksheets:
            if sheet_keyword in ws.title:
                sheet = ws
                print(f"Found {sheet_keyword} sheet: {ws.title}")
                break

        if not sheet:
            print(f"WARNING: {sheet_keyword} sheet not found. Custom row not added.")
            return

        header_to_col = {sheet.cell(row=1, column=col).value: col
                        for col in range(1, sheet.max_column + 1)
                        if sheet.cell(row=1, column=col).value}

        has_data_rows = False
        for row in range(2, sheet.max_row + 1):
            for col in range(1, sheet.max_column + 1):
                if sheet.cell(row=row, column=col).value is not None:
                    has_data_rows = True
                    break
            if has_data_rows:
                break

        if has_data_rows:
            next_row = sheet.max_row + 1
        else:
            next_row = 2

        custom_values = value_getter(next_row)

        row_added = False
        for header, value in custom_values.items():
            if header in header_to_col:
                col = header_to_col[header]
                cell = sheet.cell(row=next_row, column=col)
                cell.value = value
                self._style_data(cell)
                row_added = True

        if row_added:
            print(f"Successfully added custom row to {sheet_keyword} sheet at row {next_row}")
        else:
            print(f"ERROR: Failed to add any values to the custom row in {sheet_keyword} sheet")

    def _get_heat_generator_values(self, next_row):
        net_elec_mw = self.results.get('Net_Electricity_Generated_kWe') / 1000
        net_thermal_mw = self.results.get('Net_thermal_power_Generated_kWe') / 1000
        CAPEX = self.results.get('CAPEX_total')
        print('results', self.results)
        print('CAPEX', CAPEX)
        print('net_thermal_mw', net_thermal_mw)
        print('CAPEX/net_thermal_mw', CAPEX/net_thermal_mw) 

        return {
            "ID": 0,  # Always start with ID 0 for the first/only entry
            "name": "Geothermal Heat Generator",
            "installed capacity (MW_th)": -self.thermal_power/1000000.0, # * 3.0, # 6,  # net_thermal_mw,  # net_thermal_mw + net_elec_mw,
            "efficiency th": self.specs.efficiency_thermal,
            "efficiency el": self.specs.efficiency_electric,
            "investment costs (EUR/MW_th)": CAPEX/net_thermal_mw,  # 200000, # CAPEX/100.0,
            "OPEX fix (EUR/MWa)": 2000.0, # CAPEX*0.045/net_thermal_mw/25,  # 1000,  # CAPEX*0.045/100,
            "OPEX var (EUR/MWh)": 1.1,  # 0.8,
            "Coldstart Costs (EUR/Start)": self.specs.coldstart_cost,
            "life time": self.specs.feeding_time,
            "renewable factor": self.specs.renewable_factor,
            "must run [0-1]": self.specs.must_run,
            "Maximal Available Potential [MWh]": self.specs.max_available_potential,
            "Maximal Output Power [MW]": self.specs.max_power_output,
            "Excess Heat Source Price [EUR/MWh]": self.specs.excess_heat_source_price,
            "Ramping Costs [EUR/MWh]": self.specs.ramping_cost,
            "type": self.specs.type,
            "COP source temperature sensitivity (1/°C)": self.specs.COP_source_temperature_sensitivity,
            "COP flow temperature sensitivity (1/°C)": self.specs.COP_flow_temperature_sensitivity,
            "COP return temperature sensitivity (1/°C)": self.specs.COP_return_temperature_sensitivity,
            "min shutoff source temperature (°C)": self.specs.min_shutoff_source_temperature,
            "fade out temp where power reduction starts (°C)": self.specs.fade_out_temperature,
            "Source Temperature (°C)": self.specs.source_temperature,
            "Nominal Inlet Temperature (°C)": self.specs.nominal_inlet_temperature,
            "Nominal Return Temperature (°C)": self.specs.nominal_return_temperature,
            "Refrigerants": self.specs.refrigerants,
            "Maximum Power of the Heatpump Compressor Pel (MW)": self.specs.max_power_heatpump_compressor,
            "Minimum Output Power Factor [0-1]": self.specs.min_output_power_factor,
            "Electricity price": self.specs.electricity_price,
            "Sale Electricity price": self.specs.sale_electricity_price,
        }

    def _get_energy_carrier_values(self, next_row):
        return {
            "ID": 0,  # Always start with ID 0 for the first/only entry
            "name": "Geothermal Heat Generator",
            "carrier": "electricity" # natural gas, electricity
        }

def add_row_to_excel(excel_file_path, results=None, specs=None, thermal_power=None):
    """Add row to both Heat Generators and Energy Carrier sheets"""
    try:
        wb = openpyxl.load_workbook(excel_file_path)
        success = False

        gen = ExcelGenerator(None, results, specs, thermal_power)

        for sheet_name, value_getter in [
            ("Heat Generators", gen._get_heat_generator_values),
            ("Energy Carrier", gen._get_energy_carrier_values)
        ]:
            sheet = next((ws for ws in wb.worksheets if sheet_name in ws.title), None)
            if sheet:
                next_row = max(2, sheet.max_row + 1) if sheet.max_row > 1 else 2

                values = value_getter(next_row)
                header_to_col = {sheet.cell(1, col).value: col for col in range(1, sheet.max_column + 1) if sheet.cell(1, col).value}

                for header, value in values.items():
                    if header in header_to_col:
                        cell = sheet.cell(next_row, header_to_col[header])
                        cell.value = value
                        gen._style_data(cell)
                        success = True
                print(f"Added row to {sheet_name} sheet at row {next_row}")

        if success:
            wb.save(excel_file_path)
            print(f"Successfully saved workbook with new rows at {excel_file_path}")
        return success

    except Exception as e:
        print(f"ERROR adding rows to Excel file: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_hotmaps_dispatch():
    """Run HotmapsDispatch using subprocess with conda environment"""
    print(f"Starting HotmapsDispatch from: {HOTMAPS_DISPATCH_DIR}")
    print(f"Using conda environment: {HOTMAPS_CONDA_ENV}")
    print(f"Electricity price scale: {ELECTRICITY_PRICE_SCALE}")
    print("=" * 60)
    print("HotmapsDispatch output below:")
    print("=" * 60)
    
    try:
        # Run HotmapsDispatch (single process, with browser)
        # Using Popen to stream output in real-time
        process = subprocess.Popen(
            [
                "conda", "run", "--no-capture-output", "-n", HOTMAPS_CONDA_ENV,
                "python", "-u", "-m", "app",
                "--solver", "gurobi_direct",
                "--openbrowser",
                "--num_procs", "1"
            ],
            cwd=HOTMAPS_DISPATCH_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Stream output line by line
        for line in process.stdout:
            print(f"[HotmapsDispatch] {line}", end='')
        
        process.wait()
        
        print("=" * 60)
        if process.returncode == 0:
            print("✅ HotmapsDispatch completed successfully")
        else:
            print(f"⚠️ HotmapsDispatch exited with return code: {process.returncode}")
            
        return process.returncode
        
    except FileNotFoundError:
        print("❌ Error: conda command not found. Make sure conda is in your PATH.")
        return -1
    except Exception as e:
        print(f"❌ Error running HotmapsDispatch: {e}")
        import traceback
        traceback.print_exc()
        return -1

def calculate_annual_averages(values, time_steps):
    """
    Calculate the time-weighted average value for each year.

    Parameters:
    values (list): List of values at each time step
    time_steps (list): List of time step durations (in years)

    Returns:
    dict: Dictionary with year as key and average value as value
    """
    if len(values) != len(time_steps):
        raise ValueError("Values and time_steps must have the same length")

    if not values or not time_steps:
        raise ValueError("Input lists cannot be empty")

    cumulative_times = []
    cumulative_time = 0
    for dt in time_steps:
        cumulative_times.append(cumulative_time)
        cumulative_time += dt

    # Group data by year
    annual_data = {}

    for i, (value, dt) in enumerate(zip(values, time_steps)):
        start_time = cumulative_times[i]

        start_time_rounded = round(start_time, 10)
        year = int(start_time_rounded)

        if year not in annual_data:
            annual_data[year] = {'weighted_sum': 0, 'total_time': 0}

        annual_data[year]['weighted_sum'] += value * dt
        annual_data[year]['total_time'] += dt

    annual_averages = {}
    for year, data in annual_data.items():
        annual_averages[year] = data['weighted_sum'] / data['total_time']

    return annual_averages


def process_yaml_and_setup_hotmaps(yaml_file_path, results, specs, results_over_time, dt_list):
    """Main function that processes YAML and runs Hotmaps Dispatch"""
    print('inf', results)
    print('inf', specs)
    print('results_over_time', results_over_time.get('DH_heat_transfer_real'))
    print('dt_list', dt_list)

    annual_thermal_power = calculate_annual_averages(results_over_time.get('DH_heat_transfer_real'), dt_list)
    print('annual_thermal_power', annual_thermal_power)
    print(specs.operation_year)
    thermal_power = annual_thermal_power[specs.operation_year - 1]
    print(thermal_power)

    try:
        generator = ExcelGenerator(yaml_file_path, results, specs, thermal_power)
        excel_file = generator.create_excel()

        add_row_to_excel(excel_file, results, specs, thermal_power)

        # Run HotmapsDispatch directly via subprocess
        return_code = run_hotmaps_dispatch()

        return {
            "status": "success" if return_code == 0 else "error",
            "excel_file": excel_file,
            "return_code": return_code
        }
    except Exception as e:
        print(f"Error processing YAML and running Hotmaps: {e}")
        return {"status": "error", "message": str(e)}


def generate_excel_from_yaml(yaml_file_path, results=None, specs=None):
    """Generate Excel file from YAML configuration file"""
    if not os.path.exists(yaml_file_path):
        raise FileNotFoundError(f"YAML file '{yaml_file_path}' not found.")

    print(f"Using YAML configuration from: {yaml_file_path}")
    generator = ExcelGenerator(yaml_file_path, results, specs)
    excel_file = generator.create_excel()
    print(f"Excel generation complete: {excel_file}")
    return excel_file


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python HotmapsDispatch_runner.py <yaml_config_file>")
        print("Alternatively: python HotmapsDispatch_runner.py --add-row <excel_file>")
        print(f"\nOutput directory: {OUTPUT_DIR}")
        print(f"HotmapsDispatch directory: {HOTMAPS_DISPATCH_DIR}")
        sys.exit(1)

    if sys.argv[1] == "--add-row" and len(sys.argv) >= 3:
        excel_file = sys.argv[2]
        if os.path.exists(excel_file):
            print(f"Adding rows to existing Excel file: {excel_file}")
            if add_row_to_excel(excel_file):
                print("Rows added successfully!")
            else:
                print("Failed to add rows to Excel file.")
                sys.exit(1)
        else:
            print(f"Excel file not found: {excel_file}")
            sys.exit(1)
    else:
        yaml_file = sys.argv[1]
        result = process_yaml_and_setup_hotmaps(yaml_file, None, None, None, None)

        if result["status"] == "success":
            print("Process completed successfully!")
            print(f"Excel file: {result['excel_file']}")
        else:
            print(f"Process failed: {result.get('message', 'Unknown error')}")
            sys.exit(1)
