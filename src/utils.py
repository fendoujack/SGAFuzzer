import json
import random
from graphql import GraphQLScalarType, GraphQLEnumType

def is_valid_graphql_name(name: str) -> bool:
    """Validate if a string is a valid GraphQL operation name"""
    return name.isidentifier()

def extract_non_null_values(response: dict) -> dict:
    """
    Extract all non-null values and their paths from a nested dictionary/list
    :param response: Nested GraphQL response data
    :return: Dictionary of {path: non_null_value}
    """
    def parse_data(data, path=""):
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{path}.{key}" if path else key
                yield from parse_data(value, new_path)
        elif isinstance(data, list):
            for index, item in enumerate(data):
                new_path = f"{path}"  # Keep list path consistent
                yield from parse_data(item, new_path)
        else:
            if data is not None:
                yield (path, data)

    return dict(parse_data(response))

def generate_scalar_type(type_name: str, schema) -> str:
    """
    Determine scalar type category (standard/custom/enum)
    :param type_name: GraphQL type name
    :param schema: GraphQL schema object
    :return: Categorized type name (Int/Float/String/Boolean/ID/CustomScalar/Enum)
    """
    standard_scalars = {'Int', 'Float', 'String', 'Boolean', 'ID'}
    
    # Check standard scalars
    if type_name in standard_scalars:
        return type_name
    
    # Check enum types
    type_obj = schema.get_type(type_name)
    if isinstance(type_obj, GraphQLEnumType):
        return "Enum"
    
    # Check custom scalars
    if isinstance(type_obj, GraphQLScalarType):
        return "CustomScalar"
    
    return "CustomScalar"

def generate_random_scalar_value(scalar_type: str, schema=None, custom_scalar_values: dict = None) -> any:
    """
    Generate random valid values for GraphQL scalar types
    :param scalar_type: Scalar type name
    :param schema: GraphQL schema object (for custom scalars)
    :param custom_scalar_values: Pre-generated custom scalar values from GPT
    :return: Random valid value for the scalar type
    """
    if custom_scalar_values and scalar_type in custom_scalar_values:
        return custom_scalar_values[scalar_type]
    
    scalar_generators = {
        "Int": lambda: random.randint(1, 1000),
        "Float": lambda: random.uniform(1.0, 1000.0),
        "String": lambda: f"test_string_{random.randint(1000, 9999)}",
        "Boolean": lambda: random.choice([True, False]),
        "ID": lambda: f"id_{random.randint(100000, 999999)}",
        "Enum": lambda: random.choice(["ACTIVE", "INACTIVE", "PENDING"]),
        "CustomScalar": lambda: f"custom_scalar_{random.randint(1000, 9999)}"
    }
    
    return scalar_generators.get(scalar_type, scalar_generators["String"])()

def get_dependenced_parameters_value(arg_key: str, extensions: dict, data_result_all: dict) -> any:
    """
    Get dependent parameter values from previously successful responses
    :param arg_key: Parameter key to find dependencies for
    :param extensions: Field extensions with dependency info
    :param data_result_all: All non-null values from successful responses
    :return: Most common dependent value or None
    """
    if not extensions or 'dependencies_operatation' not in extensions:
        return None
    
    if arg_key not in extensions['dependencies_operatation']:
        return None
    
    dependence_paths = extensions['dependencies_operatation'][arg_key]
    path_values = {}
    
    for path in dependence_paths:
        if path in data_result_all:
            value = data_result_all[path]
            path_values[value] = path_values.get(value, 0) + 1
    
    if not path_values:
        return None
    
    # Return most frequent value
    max_count = max(path_values.values())
    most_common = [k for k, v in path_values.items() if v == max_count][0]
    return most_common

def save_json_to_file(data: dict, file_path: str) -> None:
    """
    Save dictionary to JSON file
    :param data: Data to save
    :param file_path: Output file path
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        raise Exception(f"Failed to save JSON to {file_path}: {str(e)}")