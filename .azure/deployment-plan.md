# Azure Deployment Plan

## Status

Ready for Validation

## Phase 1 Summary

### Mode

Modify existing Python Streamlit application for Azure App Service custom-container deployment.

### Current Application

- Entry point: `streamlit_app.py`
- Runtime: Python Streamlit application with LangChain and Azure OpenAI integration
- Database access: `pyodbc` with SQL Server / Fabric Warehouse via ODBC Driver 18
- Existing CI/CD: GitHub Actions workflow for source-based Azure Web App deploy

### Key Findings

- The application test suite passes locally.
- The repository already documents Azure App Service hosting.
- Native SQL dependencies make source-based Linux App Service deployment less reliable.
- A custom container is the safest Azure App Service target because it can pin Python and install ODBC Driver 18.

### Selected Deployment Recipe

- Hosting target: Azure App Service for Containers on Linux
- Packaging: Docker image
- Deployment style: Repository prepares container assets and deployment guidance; Azure resource provisioning remains a separate step.

### Planned Artifacts

- Root `Dockerfile` for Streamlit app runtime
- Root `.dockerignore`
- Startup command or entrypoint handling for Azure App Service container runtime
- Updated deployment documentation in `README.md`
- Updated GitHub Actions workflow aligned to container/App Service deployment expectations

### Required Azure Configuration

- App Service for Linux configured for a custom container image
- Container registry available for image storage
- App settings populated from production environment values
- Secrets configured for Azure OpenAI, SQL connection, and optional Graph mail features

### Risks / Constraints

- Runtime requires `msodbcsql18` and unixODBC libraries in the container image.
- Production networking and identity configuration depend on the target Azure environment.
- Existing publish-profile workflow is oriented to source deployment and should not remain the primary deployment path.

## Execution Plan

1. Add container build assets for the Streamlit application.
2. Update deployment workflow/documentation to describe container-based App Service deployment.
3. Run focused validation for Docker-related artifacts plus existing Python test coverage.
4. Mark plan ready for validation after changes are complete.

## Validation Proof

- `python -m pytest tests/test_env.py tests/test_config.py -q` -> passed
- `python -m pytest tests -q` -> passed (85 tests)
- Workspace diagnostics for changed files -> no errors
- `docker build -t python-for-ai:local .` -> not run because Docker is not installed in this environment
