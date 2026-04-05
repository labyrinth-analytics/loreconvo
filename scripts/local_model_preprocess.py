#!/usr/bin/env python3
"""
Local model preprocessing orchestrator.

Coordinates Ollama subprocess calls for agent preprocessing tasks.
Config-driven via YAML templates. Supports any agent/task combination.

Usage:
    python3 scripts/local_model_preprocess.py --agent meg --task test_scenarios \
        --input code.py --model qwen3.5:9b

Templates are loaded from scripts/config/preprocess_templates.yaml.
Ollama must be running and have required models available.

Exit codes:
    0: Success (result printed to stdout)
    1: Ollama unavailable (graceful fallback)
    2: Config/arg error (template not found + no custom prompt, or input file missing)
"""

import argparse
import json
import logging
import re
import subprocess
import sys
import yaml
from pathlib import Path
from typing import Optional, Dict, Any


# Configure logging to stderr
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s: %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        argparse.Namespace with parsed arguments
    """
    parser = argparse.ArgumentParser(
        description='Local model preprocessing orchestrator for agent tasks',
        epilog='Templates are loaded from scripts/config/preprocess_templates.yaml'
    )

    parser.add_argument(
        '--agent',
        required=True,
        type=str,
        help='Agent name (e.g., meg, brock, scout)'
    )
    parser.add_argument(
        '--task',
        required=True,
        type=str,
        help='Task name (e.g., test_scenarios, file_screening)'
    )
    parser.add_argument(
        '--input',
        required=True,
        type=str,
        help='Path to input file to preprocess'
    )
    parser.add_argument(
        '--model',
        required=True,
        choices=['qwen3.5:9b', 'gemma4'],
        help='Ollama model to use'
    )
    parser.add_argument(
        '--prompt',
        required=False,
        type=str,
        help='Custom prompt (used if template not found)'
    )
    parser.add_argument(
        '--timeout',
        required=False,
        type=int,
        default=30,
        help='Ollama call timeout in seconds (default: 30)'
    )
    parser.add_argument(
        '--output-format',
        required=False,
        choices=['json', 'markdown', 'text'],
        default='text',
        help='Output format (default: text)'
    )

    return parser.parse_args()


def load_templates() -> Dict[str, Any]:
    """
    Load YAML templates from scripts/config/preprocess_templates.yaml.

    Returns:
        Dict with 'templates' key containing all template definitions.

    Raises:
        SystemExit(2): If templates file not found or invalid YAML.
    """
    config_path = Path(__file__).parent / 'config' / 'preprocess_templates.yaml'

    if not config_path.exists():
        logger.error(f'Templates file not found: {config_path}')
        sys.exit(2)

    try:
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or 'templates' not in data:
            logger.error('Templates file missing required "templates" key')
            sys.exit(2)
        return data
    except yaml.YAMLError as e:
        logger.error(f'Failed to parse templates YAML: {e}')
        sys.exit(2)


def get_template(templates: Dict[str, Any], agent: str, task: str) -> Optional[Dict[str, Any]]:
    """
    Look up template for agent:task pair.

    Args:
        templates: Dict from load_templates()
        agent: Agent name (e.g., 'meg')
        task: Task name (e.g., 'test_scenarios')

    Returns:
        Template dict if found, None otherwise.
    """
    key = f'{agent}.{task}'
    return templates.get('templates', {}).get(key)


def call_ollama(
    model: str,
    prompt: str,
    input_content: str,
    timeout: int
) -> Optional[str]:
    """
    Call Ollama subprocess with prompt and input.

    Args:
        model: Model name (e.g., 'qwen3.5:9b', 'gemma4')
        prompt: System prompt template
        input_content: Input file content
        timeout: Call timeout in seconds

    Returns:
        Model output as string, or None if Ollama unavailable or timeout.
    """
    # Combine prompt and input
    full_prompt = f"{prompt}\n\nInput:\n{input_content}"

    try:
        # Call ollama via subprocess
        result = subprocess.run(
            ['ollama', 'run', model],
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            logger.warning(f'Ollama returned non-zero exit code: {result.returncode}')
            return None

        return result.stdout.strip()

    except subprocess.TimeoutExpired:
        logger.warning(f'Ollama call timed out after {timeout}s')
        return None
    except FileNotFoundError:
        logger.warning('Ollama not found in PATH')
        return None
    except Exception as e:
        logger.warning(f'Ollama call failed: {e}')
        return None


def format_output(result: str, output_format: str) -> str:
    """
    Format output based on requested format.

    Args:
        result: Raw output from Ollama
        output_format: Desired format ('json', 'markdown', 'text')

    Returns:
        Formatted output as string.
    """
    if output_format == 'json':
        try:
            # Try to parse as JSON, return as-is if valid
            json.loads(result)
            return result
        except json.JSONDecodeError:
            # If not valid JSON, try to extract JSON from result
            # Look for {...} or [...] patterns, trying greedy first for better matches
            json_match = re.search(r'({.*}|\[.*\])', result, re.DOTALL)
            if json_match:
                extracted = json_match.group(1)
                # Try to parse the extracted content to verify it's valid
                try:
                    json.loads(extracted)
                    return extracted
                except json.JSONDecodeError:
                    # If extracted text is not valid, fall through to error
                    pass
            # If no valid JSON found, wrap result as error
            return json.dumps({
                'error': 'Ollama output not valid JSON',
                'raw_output': result[:500]
            })

    elif output_format == 'markdown':
        # Markdown can just pass through (Ollama often returns markdown naturally)
        return result

    else:  # 'text'
        # Plain text -- just return as-is
        return result


def main() -> int:
    """
    Main orchestration function.

    Returns:
        Exit code (0 = success, 1 = Ollama unavailable, 2 = config error)
    """
    # Parse arguments
    args = parse_arguments()

    # Load templates
    templates = load_templates()

    # Try to get template for agent:task
    template = get_template(templates, args.agent, args.task)

    if template:
        # Use template values, allow CLI args to override
        prompt = args.prompt or template.get('prompt', '')
        model = args.model  # --model is required, always use CLI arg
        output_format = template.get('output_format', args.output_format)
        timeout = template.get('timeout', args.timeout)
    else:
        # No template found
        if not args.prompt:
            logger.error(
                f'Template not found for {args.agent}.{args.task} and no --prompt provided'
            )
            sys.exit(2)
        prompt = args.prompt
        model = args.model
        output_format = args.output_format
        timeout = args.timeout

    # Read input file
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f'Input file not found: {input_path}')
        sys.exit(2)

    try:
        input_content = input_path.read_text()
    except Exception as e:
        logger.error(f'Failed to read input file: {e}')
        sys.exit(2)

    # Call Ollama
    result = call_ollama(model, prompt, input_content, timeout)

    if result is None:
        logger.error('Ollama preprocessing failed or timed out')
        sys.exit(1)

    # Format output
    formatted = format_output(result, output_format)

    # Print to stdout
    print(formatted)

    return 0


if __name__ == '__main__':
    sys.exit(main())
