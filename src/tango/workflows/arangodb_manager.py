import logging
import math
import os
import yaml
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from arango import ArangoClient

def _sanitize_numeric_value(value):
    """
    Sanitize numeric values for ArangoDB VPack serialization.
    Handles NaN, inf, and other problematic values.
    """
    if value is None:
        return None
    
    # Handle NaN
    if isinstance(value, float) and math.isnan(value):
        return None
    
    # Handle infinity
    if isinstance(value, float) and math.isinf(value):
        return None
    
    # Handle very large numbers that might cause VPack issues
    if isinstance(value, (int, float)):
        if abs(value) > 1e15:  # Very large numbers
            return None
        if abs(value) < 1e-15 and value != 0:  # Very small numbers close to zero
            return 0.0
    
    return value

def _sanitize_economic_data(data):
    """
    Recursively sanitize economic data structure for ArangoDB compatibility.
    """
    if isinstance(data, dict):
        return {key: _sanitize_economic_data(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_sanitize_economic_data(item) for item in data]
    else:
        return _sanitize_numeric_value(data)




class ArangoDBManager:
    """
    Manages all ArangoDB operations for TANGO workflows.
    Handles connection, collection setup, data writing, and multi-tenancy.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize ArangoDB manager with configuration.
        
        Args:
            config (Dict[str, Any]): ArangoDB configuration from YAML
        """
        self.config = config
        self.client = None
        self.db = None
        self._current_user_id = None
        self._current_simulation_id = None
        
        if self.config.get('enabled', 'no') == 'yes':
            self._init_connection()
            self._setup_collections()
    
    def _load_config_from_file(self) -> None:
        """Load ArangoDB configuration from config file."""
        try:
            possible_paths = [
                'config/arangodb.conf',  
                os.path.join(os.path.dirname(__file__), '..', '..', '..', 'config', 'arangodb.conf'),  
                os.path.join(os.getcwd(), 'config', 'arangodb.conf'),  
            ]
            
            config_file = None
            for path in possible_paths:
                if os.path.exists(path):
                    config_file = path
                    break
            
            if config_file:
                logging.info(f"Loading ArangoDB configuration from {config_file}")
                with open(config_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if '=' in line:
                                key, value = line.split('=', 1)
                                key = key.strip()
                                value = value.strip()
                                if value.startswith("'") and value.endswith("'"):
                                    value = value[1:-1]
                                elif value.startswith('"') and value.endswith('"'):
                                    value = value[1:-1]
                                value = value.rstrip()
                                self.config[key] = value
                                logging.debug(f"Loaded config: {key} = {value}")
                
                logging.info(f"Successfully loaded {len([k for k in self.config.keys() if k.startswith('ARANGODB_')])} configuration values from file")
            else:
                logging.warning(f"Configuration file not found in any of these locations: {possible_paths}")
                logging.warning("Using default configuration values")
        except Exception as e:
            logging.error(f"Failed to load configuration from file: {e}")
            logging.info("Using default configuration values")
    
    def _init_connection(self) -> None:
        """Initialize ArangoDB connection."""
        try:
            self._load_config_from_file()
            
            host = self.config.get('ARANGODB_HOST', 'http://localhost:8529')
            username = self.config.get('ARANGODB_USERNAME', 'root')
            password = self.config.get('ARANGODB_PASSWORD', '')
            database = self.config.get('ARANGODB_DATABASE', 'tango_geothermal')
            
            logging.info(f"Connecting to ArangoDB at {host}")
            self.client = ArangoClient(hosts=host)
            
            sys_db = self.client.db('_system', username=username, password=password)
            
            if not sys_db.has_database(database):
                logging.info(f"Creating database: {database}")
                sys_db.create_database(database)
            
            self.db = self.client.db(database, username=username, password=password)
            logging.info(f"Successfully connected to ArangoDB database: {database}")
            
        except Exception as e:
            logging.error(f"Failed to connect to ArangoDB: {e}")
            self.client = None
            self.db = None
    
    def _setup_collections(self) -> None:
        """Setup ArangoDB collections and indexes."""
        if not self.db:
            return
            
        try:
            collections = [
                'users',
                'simulations', 
                'main_graph_data',
                'power_plant_data',
                'economic_data',
                'physics_data'
            ]
            
            for collection_name in collections:
                if not self.db.has_collection(collection_name):
                    logging.info(f"Creating collection: {collection_name}")
                    self.db.create_collection(collection_name)
            
            # Create indexes for efficient querying
            self._create_indexes()
            
            logging.info("ArangoDB collections and indexes setup complete")
            
        except Exception as e:
            logging.error(f"Failed to setup ArangoDB collections: {e}")
    
    def _create_indexes(self) -> None:
        """Create indexes for efficient querying."""
        try:
            main_graph = self.db.collection('main_graph_data')
            if not main_graph.has_index(['user_id', 'simulation_id', 'timestep']):
                main_graph.ensure_index(['user_id', 'simulation_id', 'timestep'], 
                                      name='idx_main_graph_user_sim_timestep')
            
            power_plant = self.db.collection('power_plant_data')
            if not power_plant.has_index(['user_id', 'simulation_id', 'timestep']):
                power_plant.ensure_index(['user_id', 'simulation_id', 'timestep'], 
                                       name='idx_power_plant_user_sim_timestep')
            
            economic = self.db.collection('economic_data')
            if not economic.has_index(['user_id', 'simulation_id']):
                economic.ensure_index(['user_id', 'simulation_id'], 
                                    name='idx_economic_user_sim')
            
            physics = self.db.collection('physics_data')
            if not physics.has_index(['user_id', 'simulation_id']):
                physics.ensure_index(['user_id', 'simulation_id'], 
                                   name='idx_physics_user_sim')
            
            users = self.db.collection('users')
            if not users.has_index(['email']):
                users.ensure_index(['email'], name='idx_users_email')
            
            simulations = self.db.collection('simulations')
            if not simulations.has_index(['user_id']):
                simulations.ensure_index(['user_id'], name='idx_simulations_user')
            
            logging.info("ArangoDB indexes created successfully")
            
        except Exception as e:
            logging.error(f"Failed to create indexes: {e}")
    
    
    def create_or_get_user(self, email: str, name: str = "Default User", 
                          organization: str = "Default Organization") -> str:
        """
        Create or get existing user.
        
        Args:
            email (str): User email
            name (str): User name
            organization (str): User organization
            
        Returns:
            str: User ID
        """
        if not self.db:
            return None
            
        try:
            users_collection = self.db.collection('users')
            
            # Check if user exists
            user_query = 'FOR user IN users FILTER user.email == @email RETURN user'
            cursor = self.db.aql.execute(user_query, bind_vars={'email': email})
            existing_user = list(cursor)
            
            if existing_user:
                user_id = existing_user[0]['_key']
                logging.info(f"User already exists: {email} (ID: {user_id})")
                return user_id
            
            # Create new user
            user_doc = {
                'email': email,
                'name': name,
                'organization': organization,
                'created_at': datetime.now().isoformat(),
                'last_login': datetime.now().isoformat()
            }
            
            result = users_collection.insert(user_doc)
            user_id = result['_key']
            
            logging.info(f"Created new user: {email} (ID: {user_id})")
            return user_id
            
        except Exception as e:
            logging.error(f"Failed to create/get user: {e}")
            return None
    
    def create_simulation_record(self, user_id: str, yaml_content: str, 
                                yaml_file_path: str) -> str:
        """
        Create a new simulation record.
        
        Args:
            user_id (str): User ID
            yaml_content (str): Raw YAML content
            yaml_file_path (str): Path to YAML file
            
        Returns:
            str: Simulation ID
        """
        if not self.db:
            return None
            
        try:
            simulations_collection = self.db.collection('simulations')
            
            try:
                yaml_data = yaml.safe_load(yaml_content)
                yaml_content_json = yaml_data
            except yaml.YAMLError:
                yaml_content_json = None
                logging.warning("Failed to parse YAML content")
            
            fluid_name = None
            if yaml_data:
                fluid_name = (yaml_data.get('fluid_name') or 
                            yaml_data.get('props', {}).get('fluid_name') or
                            yaml_data.get('common', {}).get('fluid_name'))
            
            simulation_doc = {
                'user_id': user_id,
                'yaml_file_path': yaml_file_path,
                'yaml_content_json': yaml_content_json,
                'created_at': datetime.now().isoformat()
            }
            
            result = simulations_collection.insert(simulation_doc)
            simulation_id = result['_key']
            
            logging.info(f"Created simulation record: {simulation_id}")
            return simulation_id
            
        except Exception as e:
            logging.error(f"Failed to create simulation record: {e}")
            return None
    
    def get_current_user_and_simulation(self, workflow_instance, modified_specs=None) -> Tuple[str, str]:
        """
        Get or create current user and simulation.
        
        Args:
            workflow_instance: The workflow instance to get YAML content from
            modified_specs: Modified specifications with parameter overrides applied
            
        Returns:
            Tuple[str, str]: (user_id, simulation_id)
        """
        # Create default user
        user_id = self.create_or_get_user("emorteza@ethz.ch", "Morteza Esmaeilpour", "ETH Zurich")
        
        simulation_id = None
        if modified_specs is not None:
            # Use the modified specs that include parameter overrides
            try:
                import yaml
                yaml_content = yaml.dump(modified_specs, default_flow_style=False, sort_keys=False)
                simulation_id = self.create_simulation_record(user_id, yaml_content, workflow_instance._input_file)
            except Exception as e:
                logging.error(f"Failed to create YAML from modified specs: {e}")
        elif hasattr(workflow_instance, '_input_file'):
            # Fallback to reading original file if no modified specs provided
            try:
                with open(workflow_instance._input_file, 'r') as f:
                    yaml_content = f.read()
                simulation_id = self.create_simulation_record(user_id, yaml_content, workflow_instance._input_file)
            except Exception as e:
                logging.error(f"Failed to read YAML file for simulation record: {e}")
        
        self._current_user_id = user_id
        self._current_simulation_id = simulation_id
        
        return user_id, simulation_id
    
    def write_timestep_data(self, step_index: int, table_type: str, 
                           data_type: str, workflow_instance) -> None:
        """
        Write timestep data to ArangoDB.
        
        Args:
            step_index (int): Timestep index
            table_type (str): Type of table (main_graph, power_plant)
            data_type (str): Type of data to write
            workflow_instance: Reference to the workflow instance for data access
        """
        if not self.db or not self._current_user_id or not self._current_simulation_id:
            return
            
        try:
            if data_type == "main_graph":
                self._write_main_graph_data(step_index, workflow_instance)
            elif data_type == "power_plant":
                self._write_power_plant_data(step_index, workflow_instance)
            else:
                logging.warning(f"Unknown data type for timestep writing: {data_type}")
                
        except Exception as e:
            logging.error(f"Failed to write timestep data to ArangoDB: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
    
    def _write_main_graph_data(self, step_index: int, workflow_instance) -> None:
        """Write main graph data for a timestep."""
        try:
            graph_nodes = workflow_instance.orchestrator.graph._node
            graph_edges = workflow_instance.orchestrator.graph.edges
            
            main_graph_doc = {
                'user_id': self._current_user_id,
                'simulation_id': self._current_simulation_id,
                'timestep': step_index,
                'timestamp': datetime.now().isoformat(),
                'data_type': 'main_graph',
                'rows': []
            }
            
            for node_name, node_data in graph_nodes.items():
                node_unit = node_data['unit']
                
                try:
                    inlet_fluid = getattr(node_unit, 'inlet_fluid', None)
                    outlet_fluid = getattr(node_unit, 'outlet_fluid', None)
                    mass_rate = getattr(node_unit, 'mass_rate', None)
                    
                    if inlet_fluid:
                        inlet_row = {
                            'unit': node_name,
                            'port': 'Inlet',
                            'pressure_mpa': getattr(inlet_fluid, 'P', None) / 1000000.0 if hasattr(inlet_fluid, 'P') and getattr(inlet_fluid, 'P') is not None else None,
                            'temperature_c': getattr(inlet_fluid, 'T', None) - 273.15 if hasattr(inlet_fluid, 'T') and getattr(inlet_fluid, 'T') is not None else None,
                            'enthalpy_kj_kg': getattr(inlet_fluid, 'H', None) / 1000.0 if hasattr(inlet_fluid, 'H') and getattr(inlet_fluid, 'H') is not None else None,
                            'mass_rate_kg_s': mass_rate
                        }
                        main_graph_doc['rows'].append(inlet_row)
                    
                    if outlet_fluid:
                        outlet_row = {
                            'unit': node_name,
                            'port': 'Outlet',
                            'pressure_mpa': getattr(outlet_fluid, 'P', None) / 1000000.0 if hasattr(outlet_fluid, 'P') and getattr(outlet_fluid, 'P') is not None else None,
                            'temperature_c': getattr(outlet_fluid, 'T', None) - 273.15 if hasattr(outlet_fluid, 'T') and getattr(outlet_fluid, 'T') is not None else None,
                            'enthalpy_kj_kg': getattr(outlet_fluid, 'H', None) / 1000.0 if hasattr(outlet_fluid, 'H') and getattr(outlet_fluid, 'H') is not None else None,
                            'mass_rate_kg_s': mass_rate
                        }
                        main_graph_doc['rows'].append(outlet_row)
                        
                except AttributeError:
                    logging.warning(f"Could not extract data from node: {node_name}")
            
            logging.debug(f"Main graph data for timestep {step_index}: {len(main_graph_doc['rows'])} rows")
            if main_graph_doc['rows']:
                logging.debug(f"Sample row: {main_graph_doc['rows'][0]}")
            
            collection = self.db.collection('main_graph_data')
            result = collection.insert(main_graph_doc)
            
            logging.debug(f"Successfully wrote main graph timestep {step_index} data to ArangoDB, document ID: {result['_key']}")
            
        except Exception as e:
            logging.error(f"Failed to write main graph timestep data to ArangoDB: {e}")
            logging.error(f"Exception details: {type(e).__name__}: {str(e)}")
    
    def _write_power_plant_data(self, step_index: int, workflow_instance) -> None:
        """Write power plant data for a timestep."""
        try:
            if not hasattr(workflow_instance.orchestrator.unit.surface, 'power_plant'):
                return
            
            power_plant = workflow_instance.orchestrator.unit.surface.power_plant
            
            power_plant_doc = {
                'user_id': self._current_user_id,
                'simulation_id': self._current_simulation_id,
                'timestep': step_index,
                'timestamp': datetime.now().isoformat(),
                'data_type': 'power_plant',
                'rows': []
            }
            
            if hasattr(power_plant, 'nodes') and hasattr(power_plant, 'connections'):
                graph_nodes = power_plant.nodes
                graph_edges = [(conn.source.label, conn.target.label) for conn in power_plant.connections]
                processed_ports = set()
                
                logging.debug(f"Power plant has {len(graph_nodes)} nodes and {len(graph_edges)} edges")
                logging.debug(f"Node types: {[type(node).__name__ for node in graph_nodes.values()]}")
                logging.debug(f"Edge connections: {graph_edges}")
                
                for edge in graph_edges:
                    source, target = edge
                    source_unit = graph_nodes[source]
                    target_unit = graph_nodes[target]
                    
                    outl_ports = getattr(source_unit, 'outl', [])
                    logging.debug(f"Source unit {source} has {len(outl_ports)} outlet ports")
                    for idx, outlet in enumerate(outl_ports):
                        port_key = (source, f"Outlet-{idx + 1}")
                        if port_key not in processed_ports:
                            processed_ports.add(port_key)
                            
                            try:
                                x_attr = getattr(outlet, 'x', None)
                                x_val = x_attr.val if x_attr is not None and hasattr(x_attr, 'val') else None
                                
                                row_data = {
                                    'unit': source,
                                    'port': f"Outlet-{idx + 1}",
                                    'pressure_mpa': outlet.p.val / 10 if hasattr(outlet, 'p') and hasattr(outlet.p, 'val') and outlet.p.val is not None else None,
                                    'temperature_c': outlet.T.val if hasattr(outlet, 'T') and hasattr(outlet.T, 'val') and outlet.T.val is not None else None,
                                    'enthalpy_kj_kg': outlet.h.val / 1000.0 if hasattr(outlet, 'h') and hasattr(outlet.h, 'val') and outlet.h.val is not None else None,
                                    'mass_rate_kg_s': outlet.m.val if hasattr(outlet, 'm') and hasattr(outlet.m, 'val') and outlet.m.val is not None else None,
                                    'vapor_mass_fraction': x_val
                                }
                                power_plant_doc['rows'].append(row_data)
                                
                            except Exception as e:
                                logging.debug(f"Could not extract outlet data from {source}: {e}")
                    
                    inl_ports = getattr(target_unit, 'inl', [])
                    logging.debug(f"Target unit {target} has {len(inl_ports)} inlet ports")
                    for idx, inlet in enumerate(inl_ports):
                        port_key = (target, f"Inlet-{idx + 1}")
                        if port_key not in processed_ports:
                            processed_ports.add(port_key)
                            
                            try:
                                x_attr = getattr(inlet, 'x', None)
                                x_val = x_attr.val if x_attr is not None and hasattr(x_attr, 'val') else None
                                
                                row_data = {
                                    'unit': target,
                                    'port': f"Inlet-{idx + 1}",
                                    'pressure_mpa': inlet.p.val / 10 if hasattr(inlet, 'p') and hasattr(inlet.p, 'val') and inlet.p.val is not None else None,
                                    'temperature_c': inlet.T.val if hasattr(inlet, 'T') and hasattr(inlet.T, 'val') and inlet.T.val is not None else None,
                                    'enthalpy_kj_kg': inlet.h.val / 1000.0 if hasattr(inlet, 'h') and hasattr(inlet.h, 'val') and inlet.h.val is not None else None,
                                    'mass_rate_kg_s': inlet.m.val if hasattr(inlet, 'm') and hasattr(inlet.m, 'val') and inlet.m.val is not None else None,
                                    'vapor_mass_fraction': x_val
                                }
                                power_plant_doc['rows'].append(row_data)
                                
                            except Exception as e:
                                logging.debug(f"Could not extract inlet data from {target}: {e}")
                
                if power_plant_doc['rows']:
                    last_row = power_plant_doc['rows'].pop()
                    power_plant_doc['rows'].insert(0, last_row)
            
            logging.debug(f"Power plant data for timestep {step_index}: {len(power_plant_doc['rows'])} rows")
            if power_plant_doc['rows']:
                logging.debug(f"Sample row: {power_plant_doc['rows'][0]}")
            
            collection = self.db.collection('power_plant_data')
            result = collection.insert(power_plant_doc)
            
            logging.debug(f"Successfully wrote power plant data for timestep {step_index} to ArangoDB, document ID: {result['_key']}")
            
        except Exception as e:
            logging.error(f"Failed to write power plant data to ArangoDB: {e}")
            logging.error(f"Exception details: {type(e).__name__}: {str(e)}")
    
    def write_economic_data(self, workflow_instance) -> None:
        """Write economic data at the end of simulation."""
        if not self.db or not self._current_user_id or not self._current_simulation_id:
            return
            
        try:
            economic_results = {}
            
            if hasattr(workflow_instance, 'economic') and workflow_instance.economic:
                if hasattr(workflow_instance.economic, '_results'):
                    economic_results = workflow_instance.economic._results.copy()
            
            if economic_results:
                # Sanitize economic data to handle NaN, inf, and other problematic values
                sanitized_results = _sanitize_economic_data(economic_results)
                
                collection = self.db.collection('economic_data')
                doc = {
                    'user_id': self._current_user_id,
                    'simulation_id': self._current_simulation_id,
                    'timestamp': datetime.now().isoformat(),
                    'economic_results': sanitized_results
                }
                
                result = collection.insert(doc)
                logging.info(f"Successfully wrote economic data to ArangoDB, document ID: {result['_key']}")
            else:
                logging.warning("No economic results available")
                
        except Exception as e:
            logging.error(f"Failed to write economic data to ArangoDB: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
    
    def write_physics_data(self, workflow_instance) -> None:
        """Write physics data at the end of simulation."""
        if not self.db or not self._current_user_id or not self._current_simulation_id:
            return
            
        try:
            physics_results = {}
            
            if hasattr(workflow_instance, '_results') and workflow_instance._results:
                for key, value in workflow_instance._results.items():
                    if isinstance(value, list):
                        physics_results[f"result_{key}"] = value
                    else:
                        physics_results[f"result_{key}"] = value
            
            if (hasattr(workflow_instance.orchestrator, 'unit') and
                hasattr(workflow_instance.orchestrator.unit, 'surface') and
                workflow_instance.orchestrator.unit.surface):
                
                surface_unit = workflow_instance.orchestrator.unit.surface
                
                if hasattr(surface_unit, 'power_plant') and hasattr(surface_unit.power_plant, 'funcs'):
                    power_plant = surface_unit.power_plant
                    for key, value in power_plant.funcs.items():
                        if hasattr(value, 'val') and value.val is not None:
                            physics_results[f"power_plant_{key}"] = value.val
            
            if hasattr(workflow_instance.orchestrator, 'unit') and workflow_instance.orchestrator.unit:
                if hasattr(workflow_instance.orchestrator.unit, 'inlet_fluid'):
                    inlet = workflow_instance.orchestrator.unit.inlet_fluid
                    if hasattr(inlet, 'T') and inlet.T is not None:
                        physics_results['inlet_temperature_k'] = inlet.T
                    if hasattr(inlet, 'P') and inlet.P is not None:
                        physics_results['inlet_pressure_pa'] = inlet.P
                    if hasattr(inlet, 'H') and inlet.H is not None:
                        physics_results['inlet_enthalpy_j_kg'] = inlet.H
                
                if hasattr(workflow_instance.orchestrator.unit, 'outlet_fluid'):
                    outlet = workflow_instance.orchestrator.unit.outlet_fluid
                    if hasattr(outlet, 'T') and outlet.T is not None:
                        physics_results['outlet_temperature_k'] = outlet.T
                    if hasattr(outlet, 'P') and outlet.P is not None:
                        physics_results['outlet_pressure_pa'] = outlet.P
                    if hasattr(outlet, 'H') and outlet.H is not None:
                        physics_results['outlet_enthalpy_j_kg'] = outlet.H
            
            if hasattr(workflow_instance.orchestrator, 'graph') and hasattr(workflow_instance.orchestrator.graph, '_node'):
                for node_name, node_data in workflow_instance.orchestrator.graph._node.items():
                    if hasattr(node_data, 'inlet_fluid') and node_data.inlet_fluid:
                        inlet = node_data.inlet_fluid
                        if hasattr(inlet, 'T') and inlet.T is not None:
                            physics_results[f"node_{node_name}_inlet_temperature_k"] = inlet.T
                        if hasattr(inlet, 'P') and inlet.P is not None:
                            physics_results[f"node_{node_name}_inlet_pressure_pa"] = inlet.P
                        if hasattr(inlet, 'H') and inlet.H is not None:
                            physics_results[f"node_{node_name}_inlet_enthalpy_j_kg"] = inlet.H
                    
                    if hasattr(node_data, 'outlet_fluid') and node_data.outlet_fluid:
                        outlet = node_data.outlet_fluid
                        if hasattr(outlet, 'T') and outlet.T is not None:
                            physics_results[f"node_{node_name}_outlet_temperature_k"] = outlet.T
                        if hasattr(outlet, 'P') and outlet.P is not None:
                            physics_results[f"node_{node_name}_outlet_pressure_pa"] = outlet.P
                        if hasattr(outlet, 'H') and outlet.H is not None:
                            physics_results[f"node_{node_name}_outlet_enthalpy_j_kg"] = outlet.H
            
            # Sanitize physics data to handle NaN, inf, and other problematic values
            if physics_results:
                sanitized_physics = _sanitize_economic_data(physics_results)
                collection = self.db.collection('physics_data')
                doc = {
                    'user_id': self._current_user_id,
                    'simulation_id': self._current_simulation_id,
                    'timestamp': datetime.now().isoformat(),
                    'physics_results': physics_results
                }
                
                result = collection.insert(doc)
                logging.info(f"Successfully wrote physics data to ArangoDB, document ID: {result['_key']}")
            else:
                logging.warning("No physics results available")
                
        except Exception as e:
            logging.error(f"Failed to write physics data to ArangoDB: {e}")
            import traceback
            logging.error(f"Traceback: {traceback.format_exc()}")
    
    def check_status(self) -> Dict[str, Any]:
        """Check ArangoDB connection and collection status."""
        if not self.db:
            return {'status': 'disconnected', 'error': 'No database connection'}
        
        try:
            status = {
                'status': 'connected',
                'database': self.db.name,
                'collections': {},
                'indexes': {}
            }
            
            for collection_name in ['users', 'simulations', 'main_graph_data', 
                                  'power_plant_data', 'economic_data', 'physics_data']:
                if self.db.has_collection(collection_name):
                    collection = self.db.collection(collection_name)
                    status['collections'][collection_name] = {
                        'exists': True,
                        'count': collection.count()
                    }
                else:
                    status['collections'][collection_name] = {'exists': False}
            
            return status
            
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def get_data_summary(self) -> Dict[str, Any]:
        """Get summary of data in ArangoDB."""
        if not self.db:
            return {'error': 'No database connection'}
        
        try:
            summary = {}
            
            for collection_name in ['users', 'simulations', 'main_graph_data', 
                                  'power_plant_data', 'economic_data', 'physics_data']:
                if self.db.has_collection(collection_name):
                    collection = self.db.collection(collection_name)
                    summary[collection_name] = collection.count()
            
            if self._current_simulation_id:
                main_graph = self.db.collection('main_graph_data')
                query = '''
                FOR doc IN main_graph_data 
                FILTER doc.simulation_id == @sim_id 
                SORT doc.timestep 
                RETURN doc.timestep
                '''
                cursor = self.db.aql.execute(query, bind_vars={'sim_id': self._current_simulation_id})
                timesteps = list(cursor)
                
                if timesteps:
                    summary['current_simulation_timesteps'] = {
                        'min': min(timesteps),
                        'max': max(timesteps),
                        'count': len(timesteps)
                    }
            
            return summary
            
        except Exception as e:
            return {'error': str(e)} 