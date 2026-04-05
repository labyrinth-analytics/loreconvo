"""Unit tests for local_model_preprocess.py

Tests cover:
- load_templates() function
- get_template() function
- format_output() function
- parse_arguments() function
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import pytest

# Add scripts to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'scripts'))

from local_model_preprocess import (
    load_templates,
    get_template,
    parse_arguments,
    format_output,
)


class TestLoadTemplates:
    """Test template loading from YAML."""

    def test_load_templates_success(self):
        """Should load templates from YAML file."""
        templates = load_templates()
        assert isinstance(templates, dict)
        assert 'templates' in templates
        assert isinstance(templates['templates'], dict)

    def test_load_templates_contains_all_agents(self):
        """Should have templates for all four agents."""
        templates = load_templates()
        template_keys = templates['templates'].keys()

        # Should have at least one template per agent
        agents = {key.split('.')[0] for key in template_keys}
        assert 'meg' in agents
        assert 'brock' in agents
        assert 'scout' in agents
        assert 'jacqueline' in agents

    def test_load_templates_has_required_templates(self):
        """Should have all four required template combinations."""
        templates = load_templates()
        template_keys = set(templates['templates'].keys())

        required = {
            'meg.test_scenarios',
            'brock.file_screening',
            'scout.opportunity_filter',
            'jacqueline.metrics_extract',
        }
        assert required.issubset(template_keys)

    def test_meg_test_scenarios_template(self):
        """Should have meg test_scenarios template with correct fields."""
        templates = load_templates()
        template = templates['templates']['meg.test_scenarios']

        assert template['model'] == 'qwen3.5:9b'
        assert 'prompt' in template
        assert isinstance(template['prompt'], str)
        assert len(template['prompt']) > 0
        assert template['output_format'] == 'markdown'
        assert template['timeout'] == 30

    def test_meg_test_scenarios_prompt_content(self):
        """meg.test_scenarios prompt should contain QA-related keywords."""
        templates = load_templates()
        template = templates['templates']['meg.test_scenarios']
        prompt = template['prompt']

        # Check for key concepts in the prompt
        assert 'QA' in prompt or 'test' in prompt.lower()
        assert 'scenario' in prompt.lower()

    def test_brock_file_screening_template(self):
        """Should have brock file_screening template with correct fields."""
        templates = load_templates()
        template = templates['templates']['brock.file_screening']

        assert template['model'] == 'qwen3.5:9b'
        assert 'prompt' in template
        assert isinstance(template['prompt'], str)
        assert len(template['prompt']) > 0
        assert template['output_format'] == 'json'
        assert template['timeout'] == 30

    def test_brock_file_screening_prompt_content(self):
        """brock.file_screening prompt should contain security-related keywords."""
        templates = load_templates()
        template = templates['templates']['brock.file_screening']
        prompt = template['prompt']

        # Check for key security concepts
        assert 'security' in prompt.lower() or 'risk' in prompt.lower()

    def test_scout_opportunity_filter_template(self):
        """Should have scout opportunity_filter template with correct fields."""
        templates = load_templates()
        template = templates['templates']['scout.opportunity_filter']

        assert template['model'] == 'gemma4'
        assert 'prompt' in template
        assert isinstance(template['prompt'], str)
        assert len(template['prompt']) > 0
        assert template['output_format'] == 'json'
        assert template['timeout'] == 30

    def test_scout_opportunity_filter_prompt_content(self):
        """scout.opportunity_filter prompt should contain product-related keywords."""
        templates = load_templates()
        template = templates['templates']['scout.opportunity_filter']
        prompt = template['prompt']

        # Check for key product research concepts
        assert 'opportunity' in prompt.lower() or 'product' in prompt.lower()

    def test_jacqueline_metrics_extract_template(self):
        """Should have jacqueline metrics_extract template with correct fields."""
        templates = load_templates()
        template = templates['templates']['jacqueline.metrics_extract']

        assert template['model'] == 'qwen3.5:9b'
        assert 'prompt' in template
        assert isinstance(template['prompt'], str)
        assert len(template['prompt']) > 0
        assert template['output_format'] == 'json'
        assert template['timeout'] == 30

    def test_jacqueline_metrics_extract_prompt_content(self):
        """jacqueline.metrics_extract prompt should contain metrics-related keywords."""
        templates = load_templates()
        template = templates['templates']['jacqueline.metrics_extract']
        prompt = template['prompt']

        # Check for key PM/metrics concepts
        assert 'metric' in prompt.lower() or 'status' in prompt.lower()

    def test_load_templates_with_missing_file(self):
        """Should exit with code 2 if templates file not found."""
        with patch('local_model_preprocess.Path') as mock_path:
            mock_path.return_value.exists.return_value = False
            with pytest.raises(SystemExit) as exc_info:
                load_templates()
            assert exc_info.value.code == 2

    def test_load_templates_with_invalid_yaml(self):
        """Should exit with code 2 if YAML is invalid."""
        yaml_content = "invalid: yaml: content: [broken"

        with patch('builtins.open', mock_open(read_data=yaml_content)):
            with patch('local_model_preprocess.Path') as mock_path:
                mock_path.return_value.exists.return_value = True
                with pytest.raises(SystemExit) as exc_info:
                    load_templates()
                assert exc_info.value.code == 2

    def test_load_templates_with_missing_templates_key(self):
        """Should exit with code 2 if 'templates' key is missing."""
        yaml_content = "some_other_key: {}"

        with patch('builtins.open', mock_open(read_data=yaml_content)):
            with patch('local_model_preprocess.Path') as mock_path:
                mock_path.return_value.exists.return_value = True
                with pytest.raises(SystemExit) as exc_info:
                    load_templates()
                assert exc_info.value.code == 2


class TestGetTemplate:
    """Test template lookup."""

    def test_get_existing_template(self):
        """Should return template for valid agent/task."""
        templates = load_templates()
        template = get_template(templates, 'meg', 'test_scenarios')
        assert template is not None
        assert isinstance(template, dict)
        assert 'prompt' in template

    def test_get_template_meg_all_tasks(self):
        """Should find all meg templates."""
        templates = load_templates()
        template = get_template(templates, 'meg', 'test_scenarios')
        assert template is not None
        assert template['model'] == 'qwen3.5:9b'

    def test_get_template_brock_all_tasks(self):
        """Should find all brock templates."""
        templates = load_templates()
        template = get_template(templates, 'brock', 'file_screening')
        assert template is not None
        assert template['model'] == 'qwen3.5:9b'

    def test_get_template_scout_all_tasks(self):
        """Should find all scout templates."""
        templates = load_templates()
        template = get_template(templates, 'scout', 'opportunity_filter')
        assert template is not None
        assert template['model'] == 'gemma4'

    def test_get_template_jacqueline_all_tasks(self):
        """Should find all jacqueline templates."""
        templates = load_templates()
        template = get_template(templates, 'jacqueline', 'metrics_extract')
        assert template is not None
        assert template['model'] == 'qwen3.5:9b'

    def test_get_nonexistent_agent(self):
        """Should return None for unknown agent."""
        templates = load_templates()
        template = get_template(templates, 'unknown_agent', 'test_scenarios')
        assert template is None

    def test_get_nonexistent_task(self):
        """Should return None for unknown task."""
        templates = load_templates()
        template = get_template(templates, 'meg', 'unknown_task')
        assert template is None

    def test_get_both_nonexistent(self):
        """Should return None for both unknown agent and task."""
        templates = load_templates()
        template = get_template(templates, 'nonexistent', 'nonexistent')
        assert template is None

    def test_get_template_with_empty_templates_dict(self):
        """Should return None if templates dict is empty."""
        templates = {'templates': {}}
        template = get_template(templates, 'meg', 'test_scenarios')
        assert template is None

    def test_get_template_with_missing_templates_key(self):
        """Should return None if templates key is missing."""
        templates = {}
        template = get_template(templates, 'meg', 'test_scenarios')
        assert template is None


class TestFormatOutput:
    """Test output formatting."""

    def test_format_json_with_valid_json(self):
        """Should pass through valid JSON unchanged."""
        input_json = '{"test": "data", "number": 42}'
        output = format_output(input_json, 'json')
        assert output == input_json
        # Verify it's still valid JSON
        parsed = json.loads(output)
        assert parsed == {"test": "data", "number": 42}

    def test_format_json_with_array(self):
        """Should pass through valid JSON arrays unchanged."""
        input_json = '[1, 2, 3, 4, 5]'
        output = format_output(input_json, 'json')
        assert output == input_json
        parsed = json.loads(output)
        assert parsed == [1, 2, 3, 4, 5]

    def test_format_json_with_invalid_json_simple_text(self):
        """Should wrap invalid JSON in error response."""
        input_text = 'This is not JSON'
        output = format_output(input_text, 'json')
        parsed = json.loads(output)
        assert 'error' in parsed
        assert parsed['error'] == 'Ollama output not valid JSON'
        assert 'raw_output' in parsed

    def test_format_json_with_invalid_json_malformed(self):
        """Should wrap malformed JSON in error response."""
        input_text = '{"incomplete": '
        output = format_output(input_text, 'json')
        parsed = json.loads(output)
        assert 'error' in parsed

    def test_format_json_with_mixed_text_and_json(self):
        """Should extract JSON from text if possible."""
        input_text = 'Some prefix text\n{"extracted": "json"}\nSome suffix'
        output = format_output(input_text, 'json')
        parsed = json.loads(output)
        assert parsed == {"extracted": "json"}

    def test_format_json_with_wrapped_json(self):
        """Should extract JSON wrapped in text."""
        input_text = 'Analysis:\n{"result": "success"}\nEnd'
        output = format_output(input_text, 'json')
        parsed = json.loads(output)
        assert parsed == {"result": "success"}

    def test_format_json_with_nested_json(self):
        """Should handle nested JSON structures."""
        nested_json = '{"outer": {"inner": {"deep": "value"}}}'
        output = format_output(nested_json, 'json')
        parsed = json.loads(output)
        assert parsed['outer']['inner']['deep'] == 'value'

    def test_format_markdown_passthrough(self):
        """Should pass through markdown unchanged."""
        markdown_text = '# Heading\n\nSome **bold** text\n\n- List item\n'
        output = format_output(markdown_text, 'markdown')
        assert output == markdown_text

    def test_format_markdown_with_code_blocks(self):
        """Should preserve markdown code blocks."""
        markdown_with_code = '```python\nprint("hello")\n```\n'
        output = format_output(markdown_with_code, 'markdown')
        assert output == markdown_with_code

    def test_format_text_passthrough(self):
        """Should pass through plain text unchanged."""
        plain_text = 'This is just plain text with some words.'
        output = format_output(plain_text, 'text')
        assert output == plain_text

    def test_format_text_with_newlines(self):
        """Should preserve text with newlines."""
        multiline_text = 'Line 1\nLine 2\nLine 3\n'
        output = format_output(multiline_text, 'text')
        assert output == multiline_text

    def test_format_json_error_truncates_long_output(self):
        """Should truncate long raw_output in error response."""
        long_text = 'x' * 1000
        output = format_output(long_text, 'json')
        parsed = json.loads(output)
        assert len(parsed['raw_output']) <= 500

    def test_format_json_with_large_json_object(self):
        """Should handle large JSON objects."""
        large_json = json.dumps({f"key_{i}": f"value_{i}" for i in range(100)})
        output = format_output(large_json, 'json')
        parsed = json.loads(output)
        assert len(parsed) == 100

    def test_format_json_with_unicode_content(self):
        """Should handle JSON with Unicode content."""
        unicode_json = '{"text": "Unicode: [OK] test"}'
        output = format_output(unicode_json, 'json')
        parsed = json.loads(output)
        assert '[OK]' in parsed['text']

    def test_format_json_empty_string_input(self):
        """Should handle empty string input."""
        output = format_output('', 'json')
        parsed = json.loads(output)
        assert 'error' in parsed


class TestArgumentParsing:
    """Test CLI argument parsing."""

    def test_parse_required_arguments(self):
        """Should parse all required arguments."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b']
        ):
            args = parse_arguments()
            assert args.agent == 'meg'
            assert args.task == 'test_scenarios'
            assert args.input == 'file.txt'
            assert args.model == 'qwen3.5:9b'

    def test_parse_all_required_arguments_all_agents(self):
        """Should parse arguments for all agent types."""
        agents = ['meg', 'brock', 'scout', 'jacqueline']
        for agent in agents:
            with patch.object(
                sys, 'argv',
                ['script', '--agent', agent, '--task', 'some_task',
                 '--input', 'file.txt', '--model', 'qwen3.5:9b']
            ):
                args = parse_arguments()
                assert args.agent == agent

    def test_parse_optional_prompt_argument(self):
        """Should parse optional --prompt argument."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b',
             '--prompt', 'Custom prompt']
        ):
            args = parse_arguments()
            assert args.prompt == 'Custom prompt'

    def test_parse_optional_prompt_default_none(self):
        """Should default --prompt to None if not provided."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b']
        ):
            args = parse_arguments()
            assert args.prompt is None

    def test_parse_optional_timeout_argument(self):
        """Should parse optional --timeout argument."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b',
             '--timeout', '60']
        ):
            args = parse_arguments()
            assert args.timeout == 60

    def test_parse_optional_timeout_default(self):
        """Should default --timeout to 30 if not provided."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b']
        ):
            args = parse_arguments()
            assert args.timeout == 30

    def test_parse_optional_output_format_argument(self):
        """Should parse optional --output-format argument."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b',
             '--output-format', 'json']
        ):
            args = parse_arguments()
            assert args.output_format == 'json'

    def test_parse_optional_output_format_default(self):
        """Should default --output-format to 'text' if not provided."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b']
        ):
            args = parse_arguments()
            assert args.output_format == 'text'

    def test_parse_missing_required_agent(self):
        """Should reject missing --agent argument."""
        with patch.object(
            sys, 'argv',
            ['script', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b']
        ):
            with pytest.raises(SystemExit):
                parse_arguments()

    def test_parse_missing_required_task(self):
        """Should reject missing --task argument."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg',
             '--input', 'file.txt', '--model', 'qwen3.5:9b']
        ):
            with pytest.raises(SystemExit):
                parse_arguments()

    def test_parse_missing_required_input(self):
        """Should reject missing --input argument."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--model', 'qwen3.5:9b']
        ):
            with pytest.raises(SystemExit):
                parse_arguments()

    def test_parse_missing_required_model(self):
        """Should reject missing --model argument."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt']
        ):
            with pytest.raises(SystemExit):
                parse_arguments()

    def test_parse_invalid_model_choice(self):
        """Should reject invalid --model choices."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'invalid_model']
        ):
            with pytest.raises(SystemExit):
                parse_arguments()

    def test_parse_valid_model_choices(self):
        """Should accept all valid model choices."""
        valid_models = ['qwen3.5:9b', 'gemma4']
        for model in valid_models:
            with patch.object(
                sys, 'argv',
                ['script', '--agent', 'meg', '--task', 'test_scenarios',
                 '--input', 'file.txt', '--model', model]
            ):
                args = parse_arguments()
                assert args.model == model

    def test_parse_invalid_output_format_choice(self):
        """Should reject invalid --output-format choices."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b',
             '--output-format', 'invalid_format']
        ):
            with pytest.raises(SystemExit):
                parse_arguments()

    def test_parse_valid_output_format_choices(self):
        """Should accept all valid output format choices."""
        formats = ['json', 'markdown', 'text']
        for fmt in formats:
            with patch.object(
                sys, 'argv',
                ['script', '--agent', 'meg', '--task', 'test_scenarios',
                 '--input', 'file.txt', '--model', 'qwen3.5:9b',
                 '--output-format', fmt]
            ):
                args = parse_arguments()
                assert args.output_format == fmt

    def test_parse_timeout_as_integer(self):
        """Should parse timeout as integer."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b',
             '--timeout', '45']
        ):
            args = parse_arguments()
            assert isinstance(args.timeout, int)
            assert args.timeout == 45

    def test_parse_invalid_timeout_not_integer(self):
        """Should reject invalid timeout (not an integer)."""
        with patch.object(
            sys, 'argv',
            ['script', '--agent', 'meg', '--task', 'test_scenarios',
             '--input', 'file.txt', '--model', 'qwen3.5:9b',
             '--timeout', 'not_an_int']
        ):
            with pytest.raises(SystemExit):
                parse_arguments()


class TestCallOllama:
    """Test Ollama subprocess orchestration."""

    @patch('local_model_preprocess.subprocess.run')
    def test_call_ollama_success(self, mock_run):
        """Should return output on successful Ollama call."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Test output",
            stderr=""
        )

        from local_model_preprocess import call_ollama

        result = call_ollama('qwen3.5:9b', 'Test prompt', 'Test input', 30)
        assert result == "Test output"
        mock_run.assert_called_once()

    @patch('local_model_preprocess.subprocess.run')
    def test_call_ollama_timeout(self, mock_run):
        """Should return None on timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired('ollama', 30)

        from local_model_preprocess import call_ollama

        result = call_ollama('qwen3.5:9b', 'Test prompt', 'Test input', 30)
        assert result is None

    @patch('local_model_preprocess.subprocess.run')
    def test_call_ollama_not_found(self, mock_run):
        """Should return None if Ollama not found."""
        mock_run.side_effect = FileNotFoundError('ollama not found')

        from local_model_preprocess import call_ollama

        result = call_ollama('qwen3.5:9b', 'Test prompt', 'Test input', 30)
        assert result is None

    @patch('local_model_preprocess.subprocess.run')
    def test_call_ollama_nonzero_exit(self, mock_run):
        """Should return None if Ollama returns error."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Model not found"
        )

        from local_model_preprocess import call_ollama

        result = call_ollama('qwen3.5:9b', 'Test prompt', 'Test input', 30)
        assert result is None


class TestIntegration:
    """Integration tests with mocked Ollama."""

    @patch('local_model_preprocess.subprocess.run')
    def test_end_to_end_meg_test_scenarios(self, mock_run):
        """Should orchestrate meg test_scenarios end-to-end."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1. Test login\n2. Test invalid password",
            stderr=""
        )

        # Create a temporary input file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("File: auth.py\nChanged: login function")
            input_file = f.name

        try:
            with patch.object(sys, 'argv', [
                'script',
                '--agent', 'meg',
                '--task', 'test_scenarios',
                '--input', input_file,
                '--model', 'qwen3.5:9b'
            ]):
                from local_model_preprocess import main

                # Should return 0 on success
                with patch('builtins.print') as mock_print:
                    result = main()
                    assert result == 0
                    mock_print.assert_called_once()
        finally:
            Path(input_file).unlink()

    def test_missing_input_file_exits_with_2(self):
        """Should exit with code 2 if input file missing."""
        with patch.object(sys, 'argv', [
            'script',
            '--agent', 'meg',
            '--task', 'test_scenarios',
            '--input', '/nonexistent/file.txt',
            '--model', 'qwen3.5:9b'
        ]):
            from local_model_preprocess import main

            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 2

    @patch('local_model_preprocess.subprocess.run')
    def test_ollama_unavailable_exits_with_1(self, mock_run):
        """Should exit with code 1 if Ollama returns None."""
        mock_run.side_effect = FileNotFoundError('ollama not found')

        # Create a temporary input file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("File: auth.py\nChanged: login function")
            input_file = f.name

        try:
            with patch.object(sys, 'argv', [
                'script',
                '--agent', 'meg',
                '--task', 'test_scenarios',
                '--input', input_file,
                '--model', 'qwen3.5:9b'
            ]):
                from local_model_preprocess import main

                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
        finally:
            Path(input_file).unlink()

    def test_input_file_read_error_exits_with_2(self):
        """Should exit with code 2 if input file cannot be read."""
        # Create a file path we'll mock to fail on read
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            input_file = f.name

        try:
            with patch.object(sys, 'argv', [
                'script',
                '--agent', 'meg',
                '--task', 'test_scenarios',
                '--input', input_file,
                '--model', 'qwen3.5:9b'
            ]):
                from local_model_preprocess import main

                # Mock read_text to raise an exception
                with patch.object(Path, 'read_text', side_effect=IOError('Permission denied')):
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 2
        finally:
            Path(input_file).unlink()

    @patch('local_model_preprocess.subprocess.run')
    def test_custom_prompt_no_template_found(self, mock_run):
        """Should use custom prompt when template not found."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Custom output",
            stderr=""
        )

        # Create a temporary input file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test input")
            input_file = f.name

        try:
            with patch.object(sys, 'argv', [
                'script',
                '--agent', 'nonexistent_agent',
                '--task', 'nonexistent_task',
                '--input', input_file,
                '--model', 'qwen3.5:9b',
                '--prompt', 'Custom prompt text'
            ]):
                from local_model_preprocess import main

                with patch('builtins.print') as mock_print:
                    result = main()
                    assert result == 0
                    mock_print.assert_called_once()
        finally:
            Path(input_file).unlink()

    def test_no_template_no_custom_prompt_exits_with_2(self):
        """Should exit with code 2 if no template and no custom prompt."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test input")
            input_file = f.name

        try:
            with patch.object(sys, 'argv', [
                'script',
                '--agent', 'nonexistent_agent',
                '--task', 'nonexistent_task',
                '--input', input_file,
                '--model', 'qwen3.5:9b'
            ]):
                from local_model_preprocess import main

                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 2
        finally:
            Path(input_file).unlink()

    @patch('local_model_preprocess.subprocess.run')
    def test_generic_exception_in_call_ollama(self, mock_run):
        """Should return None on generic exception in call_ollama."""
        mock_run.side_effect = RuntimeError('Unexpected error')

        from local_model_preprocess import call_ollama

        result = call_ollama('qwen3.5:9b', 'Test prompt', 'Test input', 30)
        assert result is None
