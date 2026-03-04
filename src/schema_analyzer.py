import requests
import logging
from graphql import build_client_schema, get_introspection_query
from graphql_path_find import GraphQLPathFinder

log = logging.getLogger(__name__)

def fetch_introspection_data(source: str, is_url: bool, auth_headers: dict) -> dict:
    """
    Fetch GraphQL schema introspection data
    :param source: GraphQL endpoint URL or local JSON file path
    :param is_url: Whether source is a URL (True) or file (False)
    :param auth_headers: Request headers with authentication
    :return: Introspection data dictionary
    """
    if is_url:
        try:
            response = requests.post(
                source,
                json={'query': get_introspection_query()},
                headers=auth_headers
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch introspection data: {str(e)}")
    else:
        try:
            with open(source, 'r') as f:
                return json.load(f)
        except Exception as e:
            raise Exception(f"Failed to load local introspection file: {str(e)}")

def find_custom_scalar_types(introspection_data: dict) -> list:
    """
    Extract custom scalar types from introspection data (excluding standard scalars)
    :param introspection_data: GraphQL introspection response
    :return: List of custom scalars [{name: str, description: str}]
    """
    standard_scalars = {'Int', 'Float', 'String', 'Boolean', 'ID'}
    types = introspection_data['data']['__schema']['types']
    custom_scalars = []

    for gql_type in types:
        if gql_type['kind'] == 'SCALAR' and gql_type['name'] not in standard_scalars:
            custom_scalars.append({
                'name': gql_type['name'],
                'description': gql_type.get('description', 'no_description')
            })

    return custom_scalars

def process_dependencies(field, schema, path_finder: GraphQLPathFinder) -> None:
    """
    Process field dependencies and find paths to dependent objects
    :param field: GraphQLField object
    :param schema: GraphQLSchema object
    :param path_finder: GraphQLPathFinder instance
    """
    # Process non-null parameters
    if 'non_null_parameters' in field.extensions:
        for param in field.extensions['non_null_parameters']:
            _process_single_dependency(param, field, schema, path_finder)

    # Process least-one parameters
    if 'least_one_parameters' in field.extensions:
        for param in field.extensions['least_one_parameters']:
            _process_single_dependency(param, field, schema, path_finder)

def _process_single_dependency(param: str, field, schema, path_finder: GraphQLPathFinder) -> None:
    """Helper to process a single dependency parameter"""
    if param not in field.extensions.get('dependencies', {}):
        return

    dependent_object = field.extensions['dependencies'][param]
    if not dependent_object:
        return

    # Find paths to dependent object
    paths = path_finder.find_paths_to_object(dependent_object[0], dependent_object[1])
    formatted_paths = path_finder.format_paths(paths)
    compact_paths = path_finder.format_compact_paths(paths)

    # Update dependent operation extensions
    for path in formatted_paths:
        operation_full_name, _ = path.split('>', 1)
        dep_op_type_name, dep_op_name = operation_full_name.split('.')
        
        # Get dependent operation type (Query/Mutation)
        dep_op_type = (schema.query_type.fields.get(dep_op_name) 
                       if "Query" in dep_op_type_name 
                       else schema.mutation_type.fields.get(dep_op_name))
        
        if dep_op_type:
            if 'return_fields' not in dep_op_type.extensions:
                dep_op_type.extensions['return_fields'] = set()
            dep_op_type.extensions['return_fields'].add(path)

    # Update current field's dependency operations
    if 'dependencies_operatation' not in field.extensions:
        field.extensions['dependencies_operatation'] = {}
    field.extensions['dependencies_operatation'][param] = compact_paths