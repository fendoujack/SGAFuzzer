import argparse
import logging
import traceback
from graphql import build_client_schema

from config import FuzzerConfig
from utils import is_valid_graphql_name
from gpt_integration import call_chatgpt_for_custom_scalars, save_custom_scalar_values
from schema_analyzer import fetch_introspection_data, find_custom_scalar_types
from fuzzer import original_operations, valid_fuzz, invalid_fuzz
from report import FuzzerReport

def main():
    parser = argparse.ArgumentParser(description="GraphQL Fuzzer - Automated GraphQL API Fuzz Testing")
    # 核心优化：endpoint 为必填，source 可选（默认等于 endpoint）
    parser.add_argument("--endpoint", required=True, help="GraphQL endpoint URL (for both introspection and execution)")
    parser.add_argument("--source", help="Custom introspection source (URL or local file, default: same as --endpoint)")
    parser.add_argument("--is-url", action="store_true", default=True, help="Treat source as URL (default: True)")
    parser.add_argument("--no-url", action="store_false", dest="is_url", help="Treat source as local file (only valid if --source is a file path)")
    

    parser.add_argument(
        "--auth-header", 
        action="append", 
        nargs=2, 
        metavar=("KEY", "VALUE"),
        help="Custom authentication header (key=value format, can specify multiple times). "
             "Example: --auth-header Private-Token glpat-y-Vrcxc5ZHCoz78xYEgA OR --auth-header Authorization 'Bearer xxx'"
    )

    args = parser.parse_args()


    source = args.source if args.source else args.endpoint

    if args.source and not args.is_url:
        is_url = False
    else:
        is_url = True


    auth_headers = {"Content-Type": "application/json"}

    if args.auth_header:
        for key, value in args.auth_header:
            auth_headers[key] = value


    config = FuzzerConfig(
        graphql_endpoint=args.endpoint,
        is_url=is_url,
        source_path=source,
        auth_headers=auth_headers
    )

    log = config.setup_logging()

    report = FuzzerReport()

    try:
        log.info(f"Fetching introspection data from: {source}")
        introspection_data = fetch_introspection_data(
            source=source,
            is_url=is_url,
            auth_headers=config.auth_headers
        )

        schema = build_client_schema(introspection_data['data'])
        log.info("Successfully built GraphQL schema")

        custom_scalars = find_custom_scalar_types(introspection_data)
        custom_scalar_values = {}

        if custom_scalars:
            log.info(f"Found custom scalars: {[s['name'] for s in custom_scalars]}")
            custom_scalar_values = call_chatgpt_for_custom_scalars(custom_scalars, config) or {}
            save_custom_scalar_values(custom_scalar_values, config.custom_scalar_file)
        else:
            log.info("No custom scalars found")

        query_type = schema.query_type
        mutation_type = schema.mutation_type

        if query_type:
            log.info("Processing query operations")
            original_operations(
                query_type, "query", config.graphql_endpoint, schema,
                config, report, custom_scalar_values
            )

        if mutation_type:
            log.info("Processing mutation operations")
            original_operations(
                mutation_type, "mutation", config.graphql_endpoint, schema,
                config, report, custom_scalar_values
            )

        log.info("Starting valid fuzzing")
        valid_fuzz(schema, config.graphql_endpoint, config, report, custom_scalar_values)

        log.info("Starting invalid fuzzing")
        if query_type:
            invalid_fuzz(query_type, "query", config.graphql_endpoint, schema, config, custom_scalar_values)
        if mutation_type:
            invalid_fuzz(mutation_type, "mutation", config.graphql_endpoint, schema, config, custom_scalar_values)

        report.generate_summary()

    except Exception as e:
        log.error(f"Fuzzing failed with error: {str(e)}")
        log.error(traceback.format_exc())
        exit(1)

if __name__ == "__main__":
    main()
