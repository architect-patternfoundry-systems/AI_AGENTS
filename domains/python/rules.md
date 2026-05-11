# Python Domain Rules

Rules and patterns specific to Python development in this workspace.

## Project Structure
- `src/` - Source code
- `tests/` - Test files
- `requirements.txt` - Dependencies
- `setup.py` or `pyproject.toml` - Package configuration
- `.venv/` - Virtual environment (gitignored)

## Code Style
- Follow PEP 8 style guide
- Use black for code formatting
- Use isort for import sorting
- Use flake8 for linting
- Use mypy for type checking (if applicable)

## Dependencies
- Pin dependency versions in requirements.txt
- Use virtual environments for isolation
- Regularly update dependencies for security patches
- Document dependency decisions

## Testing
- Use pytest for testing
- Write unit tests for all functions
- Use fixtures for test data
- Maintain test coverage >80%

## Virtual Environments
- Use `python -m venv .venv` for creation
- Activate with `source .venv/bin/activate`
- Never commit .venv directory
- Document required Python version

## Environment Variables
- Use python-dotenv for environment variable management
- Never commit .env files with secrets
- Provide .env.example as template
- Use environment-specific configurations