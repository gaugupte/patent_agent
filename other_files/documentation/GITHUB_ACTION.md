### `.github/workflows/ci.yml`

This is the **continuous integration (CI) workflow**. GitHub Actions runs it for pull requests and pushes to `main`; it can also be started manually or called by another workflow.

It has three jobs:

- **Frontend:** installs the React app’s dependencies and builds it.
- **Backend:** installs Python and test dependencies, checks Python syntax and Django configuration, runs pytest, and checks the deployment shell scripts’ syntax.
- **PowerShell:** parses the Windows data-preparation script to catch syntax errors.

CI checks the repository. It does not deploy to your server.

### `.github/workflows/deploy-production.yml`

This is the **production deployment workflow**. It is manually triggered and requires a confirmation input before proceeding. It calls CI first, so deployment proceeds only after those checks pass. Then it connects to the Civo VM over SSH and runs the release deployment script.

To use it, GitHub needs deployment secrets such as the VM’s address, SSH credentials, and application paths. Its SSH connection must also be allowed by the VM’s firewall. The workflow file defines the process; it does not run automatically until the changes are committed and pushed to GitHub.