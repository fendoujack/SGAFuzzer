import os
import logging
from datetime import datetime
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class FuzzerConfig:
    graphql_endpoint: str = field(default=os.getenv("GRAPHQL_ENDPOINT", ""))
    is_url: bool = field(default=os.getenv("IS_URL", "true").lower() == "true")
    source_path: str = field(default=os.getenv("SOURCE_PATH", ""))
    

    auth_headers: dict = field(default_factory=lambda: {
        "Content-Type": "application/json"
    })
    
    openai_api_key: str = field(default="sk-HQAqdd6NG0ooI35F2wFVsF982owpy6SqTC3KjchL1dznJUNq")
    openai_base_url: str = field(default="https://api.chatanywhere.tech")
    openai_model: str = field(default="gpt-5-mini")
    
    log_level: str = field(default="DEBUG")
    log_dir: str = field(default="logs")
    report_dir: str = field(default="reports")
    
    max_tokens: int = field(default=5000)
    skip_operations: list = field(default_factory=lambda: ["tokensDeactivateAll"])

    def __post_init__(self):
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"graphql_debug_{self.timestamp}.log")
        self.error_log_file = os.path.join(self.log_dir, f"graphql_errors_{self.timestamp}.log")
        self.report_dir = os.path.join(self.report_dir, self.timestamp)
        self.custom_scalar_file = os.path.join(self.report_dir, "custom_scalar_values.json")
        
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(self.report_dir, exist_ok=True)
        os.makedirs(os.path.join(self.report_dir, "queries"), exist_ok=True)
        os.makedirs(os.path.join(self.report_dir, "mutations"), exist_ok=True)
        os.makedirs(os.path.join(self.report_dir, "responses"), exist_ok=True)
        os.makedirs(os.path.join(self.report_dir, "requests"), exist_ok=True)

    def setup_logging(self):
        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format='%(asctime)s %(levelname)s:%(message)s',
            handlers=[
                logging.FileHandler(self.log_file, mode='w', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        return logging.getLogger(__name__)
