import json
from openai import OpenAI, APIError
import logging

log = logging.getLogger(__name__)

def call_chatgpt_for_custom_scalars(custom_scalars: list, config) -> dict:
    """
    Request ChatGPT to generate valid sample values for custom GraphQL scalars
    :param custom_scalars: List of custom scalars [{name: str, description: str}]
    :param config: FuzzerConfig object with OpenAI settings
    :return: Dictionary of {scalar_name: sample_value} or None on failure
    """
    if not custom_scalars:
        log.info("No custom scalars found - skipping GPT request")
        return {}

    # Build prompt for GPT
    prompt = (
        "Please generate appropriate sample values for the following custom GraphQL scalar types. "
        "Return the result in strict JSON format **only**, without any explanations, comments, or extra text. "
        "Each scalar type should have a realistic value that matches its expected format or usage in a GraphQL API.\n\n"
        "If a value is explicitly described as 'None' or if no appropriate value can be determined, retain it as 'None' in the output.\n\n"
        "Examples:\n"
        "1. AbuseReportID: A unique identifier for an abuse report, should be a UUID (e.g., '123e4567-e89b-12d3-a456-426614174000').\n"
        "2. AchievementsAchievementID: A unique identifier for an achievement, should be an integer ID (e.g., '42').\n"
        "3. AiAgentID: A unique identifier for an AI agent, should be a string ID prefixed with 'agent-' (e.g., 'agent-001').\n"
        "4. BigInt: A large integer value (e.g., '9876543210123456789').\n"
        "5. Color: A hexadecimal color code (e.g., '#FF5733').\n\n"
        "Custom scalars to generate:\n"
    )

    for scalar in custom_scalars:
        prompt += f"{scalar['name']}: {scalar['description']}\n"

    prompt += "\nOutput format example:\n"
    prompt += '{\n  "AbuseReportID": "123e4567-e89b-12d3-a456-426614174000",\n  "AchievementsAchievementID": "42",\n  "AiAgentID": "agent-001"\n}\n'

    try:
        # Initialize OpenAI client
        client = OpenAI(
            api_key=config.openai_api_key,
            base_url=config.openai_base_url
        )

        # Call GPT API
        response = client.chat.completions.create(
            model=config.openai_model,
            messages=[
                {"role": "system", "content": "You are an assistant specialized in generating valid values for custom GraphQL scalar types."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=config.max_tokens
        )

        # Parse response
        gpt_response = response.choices[0].message.content.strip()
        return json.loads(gpt_response)

    except APIError as e:
        log.error(f"OpenAI API error: {str(e)}")
        return None
    except json.JSONDecodeError:
        log.error(f"Failed to parse GPT response as JSON: {gpt_response}")
        return None
    except Exception as e:
        log.error(f"Unexpected error calling GPT: {str(e)}")
        return None

def save_custom_scalar_values(custom_scalar_values: dict, file_path: str) -> None:
    """
    Save generated custom scalar values to file
    :param custom_scalar_values: Custom scalar values dict
    :param file_path: Output file path
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(custom_scalar_values, f, indent=2)
        log.info(f"Custom scalar values saved to {file_path}")
    except Exception as e:
        log.error(f"Failed to save custom scalar values: {str(e)}")