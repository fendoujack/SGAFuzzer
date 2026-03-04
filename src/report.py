import logging

log = logging.getLogger(__name__)

class FuzzerReport:
    """Class to track and generate fuzzing reports"""
    def __init__(self):
        self.success_operations = set()
        self.no_data_return_operations = set()
        self.unsuccess_operations = set()
        self.internal_server_error = {}
        self.is_deprecated = set()
        self.dependent_parameters_errors = {}
        self.permission_errors = {}
        self.failed_parameters_operations = {}
        self.random_success_operations = {}
        self.data_result_all = {}

    def generate_summary(self):
        """Generate and log a summary report"""
        log.info("------------------------ Fuzzing Report ------------------------")
        log.info(f"No data return operations count: {len(self.no_data_return_operations)}")
        log.info(f"Successful operations count: {len(self.success_operations)}")
        log.info(f"Unsuccessful operations count: {len(self.unsuccess_operations)}")
        log.info(f"Internal server error operations count: {len(self.internal_server_error)}")
        
        log.info(f"\nNo data return operations: {self.no_data_return_operations}")
        log.info(f"Successful operations: {self.success_operations}")
        log.info(f"Unsuccessful operations: {self.unsuccess_operations}")
        log.info(f"Internal server error operations: {self.internal_server_error.keys()}")
        log.info("---------------------------------------------------------------")

    def add_success_operation(self, operation_name: str):
        """Add operation to successful operations set"""
        self.success_operations.add(operation_name)
        self.unsuccess_operations.discard(operation_name)
        self.no_data_return_operations.discard(operation_name)

    def add_no_data_operation(self, operation_name: str):
        """Add operation to no-data-return set"""
        self.no_data_return_operations.add(operation_name)

    def add_failed_operation(self, operation_name: str):
        """Add operation to unsuccessful operations set"""
        self.unsuccess_operations.add(operation_name)

    def add_internal_error(self, operation_name: str, error: str):
        """Add operation with internal server error"""
        self.internal_server_error[operation_name] = error