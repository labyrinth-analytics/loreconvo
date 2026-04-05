# Local Model Preprocessing

Internal agent infrastructure for local Ollama model orchestration.

## Overview

Agents call `local_model_preprocess.py` to offload cheap analysis/filtering tasks to local LLMs, reducing Claude API token usage. Preprocessing is optional and fails gracefully -- if Ollama is unavailable, agents continue without preprocessing.

## Files

- `local_model_preprocess.py` -- CLI script for Ollama orchestration
- `config/preprocess_templates.yaml` -- Task templates config (add new tasks here)

## Usage

```bash
python scripts/local_model_preprocess.py \
  --agent <agent_name> \
  --task <task_name> \
  --input <input_file> \
  --model {qwen3.5:9b|gemma4} \
  [--prompt <custom_prompt>] \
  [--timeout 30] \
  [--output-format {json|markdown|text}]
```

## Exit Codes

- `0`: Success (output returned to stdout)
- `1`: Ollama unavailable (agent continues without local preprocessing)
- `2`: Config error (missing template + no custom prompt, or missing input file)

## Examples

### Meg QA: Extract test scenarios

```bash
python scripts/local_model_preprocess.py \
  --agent meg \
  --task test_scenarios \
  --input changed_files.txt \
  --model qwen3.5:9b
```

Output: Markdown list of test scenarios

### Brock Security: Screen files

```bash
python scripts/local_model_preprocess.py \
  --agent brock \
  --task file_screening \
  --input all_changed_files.txt \
  --model qwen3.5:9b \
  --output-format json
```

Output: JSON with `{flagged: [...], safe: [...], reason: "..."}`

## Adding New Tasks

To add a new agent/task:

1. Edit `config/preprocess_templates.yaml`
2. Add entry under agent name:
   ```yaml
   newagent:
     newtask:
       model: qwen3.5:9b
       prompt: "Your instructions here..."
       output_format: json
   ```
3. Agent calls: `python scripts/local_model_preprocess.py --agent newagent --task newtask --input file.txt`
4. Done -- no script changes needed!

## Error Handling

All errors are graceful. If Ollama is unavailable, the script exits with code 1 and agents continue without preprocessing.

## Performance

- Qwen3.5:9b: ~10-30 seconds per call
- Gemma4: ~5-15 seconds per call
- Timeout: 30 seconds (configurable via `--timeout`)

## Testing

```bash
pytest tests/scripts/test_local_model_preprocess.py -v
```

## Architecture

The preprocessing system uses a template-based design:

1. **Template lookup** (`preprocess_templates.yaml`) -- defines model, prompt, and output format per agent/task combo
2. **Ollama connection** -- connects to local Ollama server (typically `http://localhost:11434`)
3. **Streaming execution** -- sends file input to the model and streams output line-by-line
4. **Format transformation** -- converts output to requested format (JSON, Markdown, or plain text)
5. **Graceful fallback** -- exits cleanly with code 1 if Ollama is unavailable

## Integration Points

Agents integrate preprocessing at the START of their review process:

- **Meg (QA):** Pre-analyze changed files to extract test scenarios before writing tests
- **Brock (Security):** Pre-screen all files to flag high-risk ones before deep review
- **Future agents:** Can add similar preprocessing steps without modifying the core script

For agent integration guidelines, see the agent prompt files in `docs/internal/other documentation/agent prompts/`.
