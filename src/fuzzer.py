import copy
import logging
import requests
from utils import generate_scalar_type, get_dependenced_parameters_value, generate_random_scalar_value, is_valid_graphql_name
from schema_analyzer import process_dependencies
from graphql_path_find import GraphQLPathFinder
from graphql import build_client_schema, get_introspection_query, GraphQLInputObjectType, GraphQLObjectType, GraphQLNonNull, GraphQLScalarType, GraphQLEnumType, GraphQLUnionType, GraphQLInterfaceType

log = logging.getLogger(__name__)

def execute_operation(
    op_type_name: str, 
    op_name: str, 
    op_string: str, 
    variables: dict, 
    endpoint: str, 
    schema, 
    attempt: int, 
    auth_headers: dict,
    literal: bool = False
) -> tuple[dict, int]:
    """
    Execute GraphQL operation and return response
    :param op_type_name: Operation type (query/mutation)
    :param op_name: Operation name
    :param op_string: GraphQL operation string
    :param variables: Operation variables
    :param endpoint: GraphQL endpoint
    :param schema: GraphQL schema
    :param attempt: Retry attempt number
    :param auth_headers: Request authentication headers
    :param literal: Whether to use literal values
    :return: (response_dict, status_code)
    """
    try:
        payload = {'query': op_string, 'variables': variables}
        response = requests.post(
            endpoint,
            json=payload,
            headers=auth_headers,
            timeout=30
        )
        return response.json(), response.status_code
    except Exception as e:
        log.error(f"Failed to execute {op_type_name}.{op_name} (attempt {attempt}): {str(e)}")
        return {}, 500

def generate_variables(
    schema, 
    variables: dict, 
    extensions: dict = None, 
    valid_value: bool = True, 
    type_name: str = None, 
    invalid_value: any = None,
    custom_scalar_values: dict = None
) -> tuple[dict, bool]:
    """
    Generate valid/invalid variables for GraphQL operations
    :param schema: GraphQL schema object
    :param variables: Base variables dict
    :param extensions: Field extensions with dependency info
    :param valid_value: Generate valid values (True) or invalid (False)
    :param type_name: Target type for invalid value generation
    :param invalid_value: Invalid value to inject
    :param custom_scalar_values: Pre-generated custom scalar values
    :return: (generated_variables, has_placeholder_replaced)
    """
    has_placeholder_replaced = False
    if not variables:
        return {}, has_placeholder_replaced

    for var_name, var_value in variables.items():
        # Handle list values
        if isinstance(var_value, list):
            for item in var_value:
                if isinstance(item, dict):
                    _, item_replaced = generate_variables(
                        schema, item, extensions, valid_value, type_name, invalid_value, custom_scalar_values
                    )
                    has_placeholder_replaced = has_placeholder_replaced or item_replaced
        
        # Handle nested dict values
        elif isinstance(var_value, dict):
            _, item_replaced = generate_variables(
                schema, var_value, extensions, valid_value, type_name, invalid_value, custom_scalar_values
            )
            has_placeholder_replaced = has_placeholder_replaced or item_replaced
        
        # Handle placeholder values (e.g., $param(Int)!)
        elif isinstance(var_value, str) and '$' in var_value:
            var_value_key = var_value.replace('$', '')
            clean_type = var_value_key.replace('!', '')
            
            # Extract type from placeholder (e.g., param(Int) -> Int)
            last_bracket = clean_type.rfind(')')
            if last_bracket != -1:
                scalar_type = clean_type[clean_type.rfind('(', 0, last_bracket) + 1:last_bracket]
                
                # Handle list types (e.g., [Int] -> Int)
                if scalar_type.startswith('[') and scalar_type.endswith(']'):
                    scalar_type = scalar_type[1:-1]
                    var_list = True
                else:
                    var_list = False

                if valid_value:
                    # Generate valid value (use dependency first, then random)
                    value = get_dependenced_parameters_value(
                        var_value_key, extensions, custom_scalar_values
                    ) or generate_random_scalar_value(
                        scalar_type, schema, custom_scalar_values
                    )
                    
                    if var_list:
                        variables[var_name] = [value]
                    else:
                        variables[var_name] = value
                else:
                    # Generate invalid value
                    if generate_scalar_type(scalar_type, schema) == type_name:
                        has_placeholder_replaced = True
                        if var_list:
                            variables[var_name] = [invalid_value]
                        else:
                            variables[var_name] = invalid_value
                    else:
                        # Fallback to valid value for other types
                        value = get_dependenced_parameters_value(
                            var_value_key, extensions, custom_scalar_values
                        ) or generate_random_scalar_value(
                            scalar_type, schema, custom_scalar_values
                        )
                        if var_list:
                            variables[var_name] = [value]
                        else:
                            variables[var_name] = value

    return variables, has_placeholder_replaced

def generate_optional_variables(
    schema, 
    variables: dict, 
    extensions: dict = None, 
    valid_value: bool = False, 
    invalid_value: bool = False,
    custom_scalar_values: dict = None
) -> list:
    """
    Generate optional variables with valid/invalid test cases
    :param schema: GraphQL schema object
    :param variables: Base variables dict
    :param extensions: Field extensions with dependency info
    :param valid_value: Generate valid test cases
    :param invalid_value: Generate invalid test cases
    :param custom_scalar_values: Pre-generated custom scalar values
    :return: List of test case variables
    """
    variables_list = []
    # Test cases for different scalar types
    test_cases = {
        "Int": ["invalid_value", -2147483648, 2147483647, "\u0000"],
        "Float": ["invalid_value", -1e308, 1e308, "\u0000"],
        "String": ["<script>alert(1)</script>", "' OR 1=1 --", 12345, True, "", "\u0000"],
        "ID": ["' OR 1=1 --", "<script>alert(1)</script>", 2147483647, "", "\u0000"],
        "CustomScalar": ["' OR 1=1 --", "<script>alert(1)</script>", 2147483647, "", "\u0000"],
        "Enum": ["", 2147483647, "\u0000"],
        "Boolean": ["true' OR 1=1 --", "\u0000"]
    }

    for type_name in test_cases:
        # Generate valid test cases
        if valid_value:
            test_vars = copy.deepcopy(variables)
            test_vars, replaced = generate_optional_variables_by_type(
                schema, test_vars, type_name, "Valid", extensions, custom_scalar_values
            )
            if replaced:
                variables_list.append(test_vars)
        
        # Generate invalid test cases
        if invalid_value:
            for test_value in test_cases[type_name]:
                test_vars = copy.deepcopy(variables)
                test_vars, replaced = generate_optional_variables_by_type(
                    schema, test_vars, type_name, test_value, extensions, custom_scalar_values
                )
                if replaced:
                    variables_list.append(test_vars)

    return variables_list

def generate_optional_variables_by_type(
    schema, 
    variables: dict, 
    type_name: str = None, 
    type_value: any = None, 
    extensions: dict = None,
    custom_scalar_values: dict = None
) -> tuple[dict, bool]:
    """
    Generate optional variables for a specific type
    :param schema: GraphQL schema object
    :param variables: Base variables dict
    :param type_name: Target type to modify
    :param type_value: Value to inject for the target type
    :param extensions: Field extensions with dependency info
    :param custom_scalar_values: Pre-generated custom scalar values
    :return: (modified_variables, has_placeholder_replaced)
    """
    if not variables:
        return None, False

    has_placeholder_replaced = False

    for var_name, var_value in variables.items():
        # Recursively handle lists
        if isinstance(var_value, list):
            for item in var_value:
                if isinstance(item, dict):
                    _, item_replaced = generate_optional_variables_by_type(
                        schema, item, type_name, type_value, extensions, custom_scalar_values
                    )
                    has_placeholder_replaced = has_placeholder_replaced or item_replaced
        
        # Recursively handle dicts
        if isinstance(var_value, dict):
            _, item_replaced = generate_optional_variables_by_type(
                schema, var_value, type_name, type_value, extensions, custom_scalar_values
            )
            has_placeholder_replaced = has_placeholder_replaced or item_replaced

        # Handle placeholder values (e.g., #param(Int)!)
        if isinstance(var_value, str) and '#' in var_value:
            clean_value = var_value.replace('#', '')
            var_value_key = clean_value
            
            # Extract type from placeholder
            last_bracket = clean_value.rfind(')')
            if last_bracket != -1:
                var_type = clean_value[clean_value.rfind('(', 0, last_bracket) + 1:last_bracket]
                non_null = var_type[-1] == '!'
                var_type = var_type.replace('!', '')

                # Handle list types
                if var_type.startswith('[') and var_type.endswith(']'):
                    inner_type = var_type[1:-1]
                    if generate_scalar_type(inner_type, schema) == type_name:
                        has_placeholder_replaced = True
                        if type_value == 'Valid':
                            value = get_dependenced_parameters_value(
                                var_value_key, extensions, custom_scalar_values
                            ) or generate_random_scalar_value(
                                inner_type, schema, custom_scalar_values
                            )
                            variables[var_name] = [value]
                        else:
                            variables[var_name] = [type_value]
                    else:
                        # Use valid value for non-null types
                        if non_null:
                            value = get_dependenced_parameters_value(
                                var_value_key, extensions, custom_scalar_values
                            ) or generate_random_scalar_value(
                                inner_type, schema, custom_scalar_values
                            )
                            variables[var_name] = [value]
                        else:
                            variables[var_name] = [None]
                else:
                    # Handle scalar types
                    if generate_scalar_type(var_type, schema) == type_name:
                        has_placeholder_replaced = True
                        if type_value == 'Valid':
                            value = get_dependenced_parameters_value(
                                var_value_key, extensions, custom_scalar_values
                            ) or generate_random_scalar_value(
                                var_type, schema, custom_scalar_values
                            )
                            variables[var_name] = value
                        else:
                            variables[var_name] = type_value
                    else:
                        # Use valid value for non-null types
                        if non_null:
                            value = get_dependenced_parameters_value(
                                var_value_key, extensions, custom_scalar_values
                            ) or generate_random_scalar_value(
                                var_type, schema, custom_scalar_values
                            )
                            variables[var_name] = value
                        else:
                            variables[var_name] = None

    return variables, has_placeholder_replaced

def original_operations(
    operation_type, 
    operation_type_name: str, 
    endpoint: str, 
    schema, 
    config, 
    report,
    custom_scalar_values: dict
) -> None:
    """
    Execute original (non-fuzzed) GraphQL operations to establish baseline
    :param operation_type: Query/Mutation type object
    :param operation_type_name: "query" or "mutation"
    :param endpoint: GraphQL endpoint
    :param schema: GraphQL schema object
    :param config: FuzzerConfig object
    :param report: FuzzerReport object
    :param custom_scalar_values: Pre-generated custom scalar values
    """
    for field_name, field in operation_type.fields.items():
        # Skip invalid names and excluded operations
        if not is_valid_graphql_name(field_name) or field_name in config.skip_operations:
            continue

        operation_name = f"{operation_type_name}.{field_name}"
        report.add_no_data_operation(operation_name)
        report.add_failed_operation(operation_name)

        # Mark deprecated operations
        if field.deprecation_reason is not None:
            report.is_deprecated.add(operation_name)

        # Get parameter dependencies
        from dependent import get_operation_parameters_sources
        field.extensions['dependencies'] = get_operation_parameters_sources(schema, field_name)

        # Generate operation string (original function implementation assumed)
        operation_string_results = generate_operation_string(
            operation_type_name, field_name, field, include_optional_parameters=False
        )

        for operation_string, un_variables in operation_string_results:
            variables = copy.deepcopy(un_variables)
            request_variables, _ = generate_variables(
                schema, variables, field.extensions, custom_scalar_values=custom_scalar_values
            )

            # Execute operation
            response, status_code = execute_operation(
                operation_type_name, field_name, operation_string, 
                request_variables, endpoint, schema, 1, config.auth_headers
            )
            
            log.info(
                f"Response for {field_name} (Status Code: {status_code}): "
                f"{response if len(str(response)) < 2000 else 'Response too large'}"
            )

        # Process dependencies
        path_finder = GraphQLPathFinder(schema)
        process_dependencies(field, schema, path_finder)

def valid_fuzz(
    schema, 
    endpoint: str, 
    config, 
    report,
    custom_scalar_values: dict
) -> None:
    """
    Execute valid fuzzing (valid values) on successful operations
    :param schema: GraphQL schema object
    :param endpoint: GraphQL endpoint
    :param config: FuzzerConfig object
    :param report: FuzzerReport object
    :param custom_scalar_values: Pre-generated custom scalar values
    """
    for success_op in report.success_operations:
        op_type_name, op_name = success_op.split('.')
        op_type = (schema.query_type.fields.get(op_name) 
                   if op_type_name == "query" 
                   else schema.mutation_type.fields.get(op_name))
        
        if not op_type:
            continue

        # Generate base operation string
        op_string_results = generate_operation_string(
            op_type_name, op_name, op_type, 
            include_optional_parameters=True, specify=True, random_fuzz=False, random_field=False
        )
        op_string, variables = op_string_results[0]
        vars_copy = copy.deepcopy(variables)

        # Generate valid variables
        request_vars, _ = generate_variables(
            schema, vars_copy, op_type.extensions, custom_scalar_values=custom_scalar_values
        )

        # Execute base operation
        response, status_code = execute_operation(
            op_type_name, op_name, op_string, request_vars, 
            endpoint, schema, 1, config.auth_headers
        )

        # Extract non-null values
        if 'data' in response:
            from utils import extract_non_null_values
            data_result = extract_non_null_values(response['data'])
            if data_result:
                report.data_result_all.update(data_result)
                report.add_success_operation(success_op)
                log.info(f"Successfully executed valid fuzz on: {op_name}")

        # Generate fuzzed valid variables
        op_string_results = generate_operation_string(
            op_type_name, op_name, op_type,
            include_optional_parameters=True, specify=True, random_fuzz=True, random_field=False
        )
        op_string, variables = op_string_results[0]
        vars_copy = copy.deepcopy(variables)
        request_vars, _ = generate_variables(
            schema, vars_copy, op_type.extensions, custom_scalar_values=custom_scalar_values
        )

        # Generate optional valid variables
        optional_vars = copy.deepcopy(request_vars)
        test_vars = generate_optional_variables(
            schema, optional_vars, op_type.extensions, 
            valid_value=True, invalid_value=False, custom_scalar_values=custom_scalar_values
        )

        # Execute with optional variables
        for test_var in test_vars:
            response, status_code = execute_operation(
                op_type_name, op_name, op_string, test_var,
                endpoint, schema, 1, config.auth_headers
            )
            if 'data' in response:
                data_result = extract_non_null_values(response['data'])
                if data_result:
                    report.data_result_all.update(data_result)
                    report.add_success_operation(success_op)
                    log.info(f"Successfully executed optional valid fuzz on: {op_name}")

    # Process no-data operations with optional variables
    with_optional_variables_request(schema, endpoint, config, report, custom_scalar_values)

def invalid_fuzz(
    operation_type, 
    operation_type_name: str, 
    endpoint: str, 
    schema, 
    config,
    custom_scalar_values: dict
) -> None:
    """
    Execute invalid fuzzing (malicious/invalid values) on operations
    :param operation_type: Query/Mutation type object
    :param operation_type_name: "query" or "mutation"
    :param endpoint: GraphQL endpoint
    :param schema: GraphQL schema object
    :param config: FuzzerConfig object
    :param custom_scalar_values: Pre-generated custom scalar values
    """
    for field_name, field in operation_type.fields.items():
        # Skip invalid names and excluded operations
        if not is_valid_graphql_name(field_name) or field_name in config.skip_operations:
            continue

        # Generate base operation string
        op_string_results = generate_operation_string(
            operation_type_name, field_name, field, include_optional_parameters=False
        )

        # Test invalid base variables
        for op_string, un_variables in op_string_results:
            fuzz_vars = copy.deepcopy(un_variables)
            invalid_vars = generate_variables_invalid(
                schema, fuzz_vars, field.extensions, custom_scalar_values=custom_scalar_values
            )

            for invalid_var in invalid_vars:
                response, status_code = execute_operation(
                    operation_type_name, field_name, op_string, invalid_var,
                    endpoint, schema, 1, config.auth_headers, literal=True
                )
                log.info(
                    f"Invalid fuzz response for {field_name} (Status Code: {status_code}): {response}"
                )

        # Test invalid optional variables
        op_string_results = generate_operation_string(
            operation_type_name, field_name, field,
            include_optional_parameters=True, specify=True, random_fuzz=True
        )

        for op_string, un_variables in op_string_results:
            vars_copy = copy.deepcopy(un_variables)
            request_vars, _ = generate_variables(
                schema, vars_copy, field.extensions, custom_scalar_values=custom_scalar_values
            )
            fuzz_vars = copy.deepcopy(request_vars)

            # Generate invalid optional variables
            invalid_optional_vars = generate_optional_variables(
                schema, fuzz_vars, field.extensions,
                valid_value=False, invalid_value=True, custom_scalar_values=custom_scalar_values
            )

            for invalid_var in invalid_optional_vars:
                response, status_code = execute_operation(
                    operation_type_name, field_name, op_string, invalid_var,
                    endpoint, schema, 1, config.auth_headers, literal=True
                )
                log.info(
                    f"Invalid optional fuzz response for {field_name} (Status Code: {status_code}): {response}"
                )

def with_optional_variables_request(
    schema, 
    endpoint: str, 
    config, 
    report,
    custom_scalar_values: dict
) -> None:
    """
    Retry no-data operations with optional variables
    :param schema: GraphQL schema object
    :param endpoint: GraphQL endpoint
    :param config: FuzzerConfig object
    :param report: FuzzerReport object
    :param custom_scalar_values: Pre-generated custom scalar values
    """
    initial_count = len(report.no_data_return_operations)
    log.info(f"Processing no-data operations (count: {initial_count})")

    # Iterate over copy to avoid modification issues
    for op_name in report.no_data_return_operations.copy():
        op_type_name, op_field_name = op_name.split('.')
        op_type = (schema.query_type.fields.get(op_field_name) 
                   if op_type_name == "query" 
                   else schema.mutation_type.fields.get(op_field_name))

        if not op_type:
            continue

        # Generate operation string
        op_string_results = generate_operation_string(
            op_type_name, op_field_name, op_type,
            include_optional_parameters=True, specify=True, random_fuzz=True, random_field=False
        )
        op_string, variables = op_string_results[0]
        vars_copy = copy.deepcopy(variables)

        # Generate variables
        request_vars, _ = generate_variables(
            schema, vars_copy, op_type.extensions, custom_scalar_values=custom_scalar_values
        )

        # Generate optional valid variables
        optional_vars = copy.deepcopy(request_vars)
        test_vars = generate_optional_variables(
            schema, optional_vars, op_type.extensions,
            valid_value=True, invalid_value=False, custom_scalar_values=custom_scalar_values
        )

        # Execute with optional variables
        for test_var in test_vars:
            response, status_code = execute_operation(
                op_type_name, op_field_name, op_string, test_var,
                endpoint, schema, 1, config.auth_headers
            )
            if 'data' in response:
                from utils import extract_non_null_values
                data_result = extract_non_null_values(response['data'])
                if data_result:
                    report.data_result_all.update(data_result)
                    report.no_data_return_operations.discard(op_name)
                    report.add_success_operation(op_name)
                    log.info(f"Recovered no-data operation: {op_field_name}")

    # Recursively process remaining no-data operations if progress was made
    if len(report.no_data_return_operations) < initial_count:
        log.info(f"Continuing processing (remaining no-data ops: {len(report.no_data_return_operations)})")
        with_optional_variables_request(schema, endpoint, config, report, custom_scalar_values)

def generate_operation_string(operation_type, operation_name, field, include_optional_parameters,  specify =False , random_fuzz = False, random_field = True):
    """
    General function to generate query or mutation operation strings
    :param operation_type: 'query' or 'mutation'
    :param operation_name: Operation name
    :param field: GraphQL field information
    :return: Generated operation string and variables
    """
    non_null_parameters={}
    operation_results = []
    base_type = get_base_type(field.type)
    fields_arg_string = None
    fields_variables = None
    field_path = None
    if 'return_fields' in field.extensions:
        field_path = field.extensions['return_fields']

    if field_path and not random_field:
        fields_structure = build_field_structure(field_path)  
        fields_string = format_field_structure(fields_structure)
    else:
        fields_string, fields_variables, fields_arg_string = generate_valid_field_structure(base_type, random_field)

    if random_fuzz and specify:
        args_result,  non_null_parameters = generate_args_string(field.args, include_optional_parameters, specify, field.extensions, random_fuzz)
        #log.info(f"second_variables :  {field.extensions}.......{args_result}")
    elif specify:
        args_result,  non_null_parameters = generate_args_string(field.args, include_optional_parameters, specify, field.extensions)
    else:
        args_result,  non_null_parameters = generate_args_string(field.args, include_optional_parameters)
        
        #add extensions
    if not include_optional_parameters:
        #log.info(f"Adding non_null_parameters to field.extensions: {non_null_parameters}")
        field.extensions['non_null_parameters'] = non_null_parameters

    for args_string, variables in args_result:

        if fields_arg_string:
            args_string += fields_arg_string

        # Generate operation header based on whether there are parameters
        if args_string.strip():
            operation_header = f"{operation_type} {operation_name}({args_string})"
        else:
            operation_header = f"{operation_type} {operation_name}"

        # Generate operation body based on whether there are variables
        if variables:
            args_vars = ", ".join(f"{arg_name}: ${arg_name}" for arg_name in variables.keys())
            operation_body = f"{operation_name}({args_vars})"
        else:
            operation_body = f"{operation_name}"

        # Construct complete GraphQL operation string
        if fields_string.strip():
            # If there are subfields, generate a query body containing the subfields
            operation = f"{operation_header} {{\n  {operation_body} {{\n    {fields_string}\n  }}\n}}"
        else:

            operation = f"{operation_header} {{\n  {operation_body}\n}}"

        if fields_variables:
            variables.update(fields_variables)
        
        operation_results.append((operation, variables))

    return operation_results
    
def generate_optional_variables(schema, variables, extensions = None, valid_value = False,  invalid_value = False):

    variables_list = []
    test_cases = {
        "Int": ["invalid_value", -2147483648, 2147483647, "\u0000"],
        "Float": ["invalid_value", -1e308, 1e308, "\u0000"], 
        "String": ["<script>alert(1)</script>", "' OR 1=1 --", 12345, True, "", "\u0000"], 
        "ID": ["' OR 1=1 --", "<script>alert(1)</script>", 2147483647, "", "\u0000"], 
        "CustomScalar": ["' OR 1=1 --", "<script>alert(1)</script>", 2147483647, "", "\u0000"], 
        "Enum": ["", 2147483647, "\u0000"],  
        "Boolean": ["true' OR 1=1 --", "\u0000"]
    } 

    for type_name in test_cases:
        if valid_value:
            Original_variables = {}
            Original_variables = copy.deepcopy(variables)
            test_variables, has_placeholder_replaced = generate_optional_variables_by_type(schema, Original_variables, type_name, "Valid", extensions)
            if has_placeholder_replaced:
                variables_list.append(test_variables)            
        if invalid_value:    
            for type_value in test_cases[type_name]:
                Original_variables = {}
                Original_variables = copy.deepcopy(variables)
                log.info(f"Original type_name and value: {type_name}...............{type_value}")
                test_variables, has_placeholder_replaced = generate_optional_variables_by_type(schema, Original_variables, type_name, type_value, extensions)
                if has_placeholder_replaced:
                    variables_list.append(test_variables)

    return variables_list
    
def get_base_type(param_type):
    while hasattr(param_type, 'of_type'):
        param_type = param_type.of_type
    return param_type    

def generate_valid_field_structure(field_type,indent_level=2):
    """
    A simple field structure generator that recursively searches for scalar fields.
    :param field_type: GraphQL type object.
    :return: Field structure string and necessary variables.
    """
    field_strings = []
    variables = {}
    args_strings = ""
    indent = '  ' * indent_level

    if isinstance(field_type, GraphQLUnionType):
        for possible_type in field_type.types:
            subfield_string, subvariables, sub_args_strings = generate_valid_field_structure(possible_type, indent_level + 1)
            if subfield_string.strip():
                field_strings.append(f"{indent}... on {possible_type.name} {{\n{subfield_string}\n{indent}}}")
                variables.update(subvariables)
                args_strings += sub_args_strings
        return "\n".join(field_strings), variables, args_strings

        # Interface 
    if isinstance(field_type, GraphQLInterfaceType):
        # generate Interface public fields
        for field_name, field in field_type.fields.items():
            base_type = get_base_type(field.type)
            if isinstance(base_type, GraphQLScalarType):
                field_strings.append(f"{indent}{field_name}")
                return "\n".join(field_strings), variables, args_strings
            
    if isinstance(field_type, GraphQLScalarType):
        return "\n".join(field_strings), variables, args_strings
    
    if isinstance(field_type, GraphQLObjectType):


        # Prioritize searching for scalar fields
        for field_name, field in field_type.fields.items():
            base_type = get_base_type(field.type)
            if isinstance(base_type, GraphQLScalarType):
                field_strings.append(f"{indent}{field_name}")
                return "\n".join(field_strings), variables, args_strings

        # If there are no scalar fields, try to find object fields that don't require arguments
        for field_name, field in field_type.fields.items():
            base_type = get_base_type(field.type)
            if isinstance(base_type, GraphQLObjectType) and not field.args:
                subfield_string, subvariables, sub_args_strings = generate_valid_field_structure(base_type, indent_level + 1)
                if subfield_string.strip():
                    variables.update(subvariables)
                    args_strings += sub_args_strings
                    field_strings.append(f"{indent}{field_name} {{\n{subfield_string}\n{indent}}}") 
                    return "\n".join(field_strings), variables, args_strings

        # If all object fields require arguments, randomly select an object field
        for field_name, field in field_type.fields.items():
            base_type = get_base_type(field.type)
            if isinstance(base_type, GraphQLObjectType):
                # Generate random values for parameters
                current_args_string_results, _ = generate_args_string(field.args, True)
                current_args_string, variables = current_args_string_results[0]
                subfield_string, subvariables, sub_args_strings = generate_valid_field_structure(base_type, indent_level + 1)
                variables.update(variables)
                args_strings += current_args_string
                if subfield_string.strip():
                    variables.update(subvariables)
                    args_strings += sub_args_strings
                    args_vars = ", ".join(f"{arg_name}: ${arg_name}" for arg_name in variables.keys())
                    field_strings.append(f"{indent}{field_name}({args_vars}) {{\n{subfield_string}\n{indent}}}") 
                    return "\n".join(field_strings), variables, args_strings
                
        for field_name, field in field_type.fields.items():
            base_type = get_base_type(field.type)   
            if isinstance(base_type, GraphQLUnionType):  # Union 
                for possible_type in base_type.types:
                    subfield_string, subvariables, sub_args_strings = generate_valid_field_structure(possible_type, indent_level + 1)
                    if subfield_string.strip():
                        field_strings.append(f"{indent}... on {possible_type.name} {{\n{subfield_string}\n{indent}}}")
                        variables.update(subvariables)
                        args_strings += sub_args_strings
                return "\n".join(field_strings), variables, args_strings
    

    log.warning(f"No valid fields found for type: {field_type}")
    return "", {}, ""


def generate_args_string(args, include_optional_parameters, specify = False, extensions = None, random_fuzz = False):
    all_results = []
    args_strings = []
    variables = {}
    first_last_present = False
    non_null_parameters = {}
    combination_args_strings = []
    combination_variables = {}
    optional_variables = {}
    optional_args_strings = []


    for arg_name, arg in args.items():
        try:
            arg_type = resolve_type(arg.type)
            arg_key = f"{arg_name}({arg_type})" 
            current_arg_string = f"${arg_name}: {arg_type}"

            # Ignore repeated first/last and certain other pagination arguments
            if arg_name in ["last"]:
                continue

            if arg_name in ["after", "before"]:
                continue

            if arg_name == "first":
                value = 1
                variables[arg_name] = value
                args_strings.append(current_arg_string)
                non_null_parameters[arg_key] = None

                continue 

            # Skip optional parameters if INCLUDE_OPTIONAL_PARAMETERS is not set
            if not isinstance(arg.type, GraphQLNonNull) and not include_optional_parameters:
                continue 

            if isinstance(arg.type, GraphQLNonNull):
                arg_type_input = arg.type.of_type
            else:
                arg_type_input = arg.type

            # Generate values for input arguments
            if isinstance(arg_type_input, GraphQLInputObjectType):
                input_fields_string, input_values, input_non_null_parameters, input_optional_values = generate_input_fields_string(arg_type_input, include_optional_parameters, arg_key, specify, extensions, random_fuzz)
                if input_values or isinstance(arg.type, GraphQLNonNull):
                    variables[arg_name] = input_values
                    args_strings.append(current_arg_string)
                if input_optional_values and random_fuzz:
                    optional_variables[arg_name] = input_optional_values
                    optional_args_strings.append(current_arg_string)
                
                non_null_parameters = non_null_parameters | input_non_null_parameters
            
            elif isinstance(arg_type_input, GraphQLList):
                list_item_type = arg_type_input.of_type
                if isinstance(list_item_type, GraphQLNonNull):
                    list_item_type = list_item_type.of_type  
                if isinstance(list_item_type, GraphQLInputObjectType):
                    input_fields_string, input_values, input_non_null_parameters, input_optional_values = generate_input_fields_string(list_item_type, include_optional_parameters, arg_key, specify, extensions, random_fuzz)
                    if input_values or isinstance(arg.type, GraphQLNonNull):
                        variables[arg_name] = [input_values]
                        args_strings.append(current_arg_string)

                    if input_optional_values and random_fuzz:
                        optional_variables[arg_name] = [input_optional_values]
                        optional_args_strings.append(current_arg_string)

                    
                    non_null_parameters = non_null_parameters | input_non_null_parameters
                else:
                    if specify and extensions:

                        least_one_parameters = extensions.get('least_one_parameters', {})
                        if least_one_parameters:
                            least_one_parameters = select_parameter_based_on_priority(least_one_parameters)

                        if arg_key not in extensions['non_null_parameters'] and arg_key not in least_one_parameters :
                            if random_fuzz:
                                value = '#' + arg_key
                                optional_variables[arg_name] = value
                                optional_args_strings.append(current_arg_string)


                            continue
                    value = '$' + arg_key
                    variables[arg_name] = value
                    args_strings.append(current_arg_string)
                    non_null_parameters[arg_key] = None                        
                 

            else:

                if specify and extensions:
                    least_one_parameters = extensions.get('least_one_parameters', {})
                    if least_one_parameters:
                        least_one_parameters = select_parameter_based_on_priority(least_one_parameters)

                    if arg_key not in extensions['non_null_parameters'] and arg_key not in least_one_parameters :

                        if random_fuzz:
                            value = '#' + arg_key
                            optional_variables[arg_name] = value
                            optional_args_strings.append(current_arg_string)
                        
                        continue
                    

                value = '$' + arg_key
                variables[arg_name] = value
                args_strings.append(current_arg_string)
                non_null_parameters[arg_key] = None

    

        except Exception as e:
            log.error("Error   argument string for '%s': %s", arg_name, str(e))
        
    return_args_strings = ", ".join(args_strings)
    all_results.append((return_args_strings, variables))
    if random_fuzz and optional_variables:
       
       #log.info(f"second_variables_detail :  {variables}.......{optional_variables}")
       #optional_variables.update(variables)
       optional_variables = merge_dicts_recursive(optional_variables, variables)
       #log.info(f"second_variables_detail :  {variables}.......{optional_variables}")
       combined_args_strings = list(set(args_strings + optional_args_strings))
       return_combined_args_strings = ", ".join(combined_args_strings)
       combined_all_results = []
       combined_all_results.append((return_combined_args_strings, optional_variables))
       return combined_all_results, non_null_parameters

    return all_results, non_null_parameters

