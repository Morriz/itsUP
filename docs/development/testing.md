# Testing Guide

Testing strategies and practices for itsup infrastructure code.

## Testing Overview

**Framework**: Python `unittest` module

**Test Location**: `lib/*_test.py` files (co-located with modules)

**Run Command**: `bin/test.sh`

**Coverage**: Unit tests for core library modules (data, deploy, upstream).

## Running Tests

### All Tests

```bash
bin/test.sh
```

**What it does**:
- Discovers all `*_test.py` files in `lib/` directory
- Runs all test cases
- Reports pass/fail and any errors

### Specific Test File

```bash
python -m unittest lib.data_test
```

### Specific Test Case

```bash
python -m unittest lib.data_test.TestLoadProject
```

### Specific Test Method

```bash
python -m unittest lib.data_test.TestLoadProject.test_load_project
```

### Verbose Output

```bash
python -m unittest -v lib.data_test
```

## Writing Tests

### Test File Structure

```python
# lib/module_test.py
import unittest
from lib.module import function_to_test

class TestFunctionName(unittest.TestCase):
    """Test cases for function_to_test"""

    def setUp(self):
        """Run before each test method"""
        self.test_data = {...}

    def tearDown(self):
        """Run after each test method"""
        # Cleanup if needed

    def test_basic_case(self):
        """Test description"""
        result = function_to_test(input_data)
        self.assertEqual(result, expected)

    def test_edge_case(self):
        """Test edge case"""
        with self.assertRaises(ValueError):
            function_to_test(invalid_input)

if __name__ == '__main__':
    unittest.main()
```

### Test Naming Conventions

**Test Files**: `{module}_test.py` (e.g., `data_test.py` for `data.py`)

**Test Classes**: `Test{FunctionName}` (e.g., `TestLoadProject`)

**Test Methods**: `test_{what_it_tests}` (e.g., `test_load_project_with_valid_config`)

**Examples**:
```python
class TestLoadProject(unittest.TestCase):
    def test_load_project_success(self):
        """Should load valid project config"""
        pass

    def test_load_project_missing_file(self):
        """Should raise error when file missing"""
        pass

    def test_load_project_invalid_yaml(self):
        """Should raise error on invalid YAML"""
        pass
```

## Test Patterns

### Testing Pure Functions

**Function**:
```python
# lib/data.py
def get_trusted_ips(router_ip: str) -> list[str]:
    """Build trusted IPs list - Docker networks + router subnet"""
    parts = router_ip.split(".")
    subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    return ["172.0.0.0/8", subnet]
```

**Test**:
```python
# lib/data_test.py
class TestGetTrustedIps(unittest.TestCase):
    def test_get_trusted_ips(self):
        """Should return Docker range + router subnet"""
        result = get_trusted_ips("192.168.1.1")
        expected = ["172.0.0.0/8", "192.168.1.0/24"]
        self.assertEqual(result, expected)

    def test_get_trusted_ips_different_subnet(self):
        """Should work with different subnet"""
        result = get_trusted_ips("10.0.0.1")
        expected = ["172.0.0.0/8", "10.0.0.0/24"]
        self.assertEqual(result, expected)
```

### Testing File Operations

**Use temporary files**:
```python
import tempfile
import os

class TestWriteUpstream(unittest.TestCase):
    def setUp(self):
        """Create temp directory"""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Cleanup temp directory"""
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_write_upstream(self):
        """Should write docker-compose.yml"""
        output_path = os.path.join(self.temp_dir, "docker-compose.yml")
        write_upstream("test-project", output_path)
        self.assertTrue(os.path.exists(output_path))
        with open(output_path) as f:
            content = f.read()
            self.assertIn("traefik.enable=true", content)
```

### Testing Exceptions

```python
class TestLoadProject(unittest.TestCase):
    def test_load_project_not_found(self):
        """Should raise FileNotFoundError for missing project"""
        with self.assertRaises(FileNotFoundError):
            load_project("nonexistent-project")

    def test_load_project_invalid_yaml(self):
        """Should raise yaml.YAMLError for invalid YAML"""
        # Create temp file with invalid YAML
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("invalid: yaml: syntax:")
            temp_path = f.name

        try:
            with self.assertRaises(yaml.YAMLError):
                load_project_from_path(temp_path)
        finally:
            os.unlink(temp_path)
```

### Mocking External Dependencies

**Using unittest.mock**:
```python
from unittest.mock import patch, MagicMock

class TestDeployUpstream(unittest.TestCase):
    @patch('lib.deploy.subprocess.run')
    def test_deploy_calls_docker_compose(self, mock_run):
        """Should call docker compose up -d"""
        deploy_upstream_project("test-project")

        # Verify subprocess.run was called with correct command
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertIn('docker', call_args)
        self.assertIn('compose', call_args)
        self.assertIn('up', call_args)
        self.assertIn('-d', call_args)

    @patch('lib.deploy.get_env_with_secrets')
    def test_deploy_loads_secrets(self, mock_get_env):
        """Should load secrets for deployment"""
        mock_get_env.return_value = {"KEY": "value"}
        deploy_upstream_project("test-project")
        mock_get_env.assert_called_once_with("test-project")
```

### Testing Configuration Loading

```python
class TestLoadProject(unittest.TestCase):
    def setUp(self):
        """Create test project structure"""
        self.temp_dir = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.temp_dir, "projects", "test-project")
        os.makedirs(self.project_dir)

        # Create test docker-compose.yml
        compose_path = os.path.join(self.project_dir, "docker-compose.yml")
        with open(compose_path, 'w') as f:
            f.write("""
services:
  web:
    image: nginx:latest
""")

        # Create test ingress.yml
        ingress_path = os.path.join(self.project_dir, "ingress.yml")
        with open(ingress_path, 'w') as f:
            f.write("""
enabled: true
ingress:
  - service: web
    domain: test.example.com
    port: 80
    router: http
""")

    def test_load_project(self):
        """Should load project config"""
        # Temporarily override projects path
        with patch('lib.data.PROJECTS_DIR', self.temp_dir + '/projects'):
            compose, ingress = load_project("test-project")

        self.assertIsNotNone(compose)
        self.assertEqual(compose['services']['web']['image'], 'nginx:latest')
        self.assertTrue(ingress['enabled'])
        self.assertEqual(ingress['ingress'][0]['domain'], 'test.example.com')
```

## Test Coverage

### Current Coverage

**lib/data.py**: Configuration loading, templates
- ✅ `get_trusted_ips()`
- ✅ `load_project()`
- ⚠️ Template rendering (partial)

**lib/deploy.py**: Deployment logic
- ⚠️ Smart rollout (needs more tests)
- ⚠️ Change detection

**lib/upstream.py**: Label injection
- ✅ `inject_traefik_labels()`
- ✅ HTTP router labels
- ✅ TCP router labels

**Note**: ✅ = well tested, ⚠️ = partially tested, ❌ = not tested

### Measuring Coverage

**Install coverage.py**:
```bash
pip install coverage
```

**Run with coverage**:
```bash
coverage run -m unittest discover -s lib -p "*_test.py"
coverage report
coverage html  # Generate HTML report
```

**View HTML report**:
```bash
firefox htmlcov/index.html
```

## Integration Testing

### Manual Integration Tests

**Test full deployment workflow**:
```bash
# 1. Create test project
mkdir -p projects/test-app
cat > projects/test-app/docker-compose.yml <<EOF
services:
  web:
    image: nginx:alpine
    networks:
      - proxynet
networks:
  proxynet:
    external: true
EOF

cat > projects/test-app/ingress.yml <<EOF
enabled: true
ingress:
  - service: web
    domain: test-app.srv.instrukt.ai
    port: 80
    router: http
EOF

# 2. Deploy
itsup apply test-app

# 3. Verify
itsup svc test-app ps
curl https://test-app.srv.instrukt.ai

# 4. Cleanup
itsup svc test-app down
rm -rf projects/test-app upstream/test-app
```

### Automated Integration Tests (Future)

**Potential structure**:
```python
# tests/integration/test_deployment.py
class TestDeploymentWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Setup test infrastructure"""
        # Start DNS and Proxy
        subprocess.run(["itsup", "dns", "up"], check=True)
        subprocess.run(["itsup", "proxy", "up"], check=True)

    @classmethod
    def tearDownClass(cls):
        """Cleanup test infrastructure"""
        subprocess.run(["itsup", "down"], check=True)

    def test_deploy_simple_app(self):
        """Should deploy and access simple nginx app"""
        # Create test project
        # Deploy
        # Verify
        # Cleanup
```

## Testing Best Practices

### General Principles

1. **Test one thing per test**: Each test method should verify one behavior
2. **Use descriptive names**: Test name should describe what it tests
3. **Arrange-Act-Assert**: Structure tests clearly (setup → action → verify)
4. **Avoid test interdependence**: Tests should run independently
5. **Clean up after tests**: Use `tearDown()` to cleanup resources

### Specific Guidelines

**Do**:
- Test edge cases and error conditions
- Use temporary files/directories for file operations
- Mock external dependencies (network, filesystem, subprocess)
- Test both success and failure paths
- Use meaningful assertion messages

**Don't**:
- Test implementation details (test behavior, not internals)
- Write flaky tests (tests that fail randomly)
- Depend on external services (use mocks)
- Hard-code paths (use temp directories)
- Leave resources uncleaned (use tearDown)

### Example: Good vs Bad Test

**Bad**:
```python
def test_function(self):
    """Test the function"""
    result = my_function()
    # No clear assertion
    self.assertTrue(result)
```

**Good**:
```python
def test_function_returns_valid_config(self):
    """Should return dict with required keys"""
    result = my_function()
    self.assertIsInstance(result, dict)
    self.assertIn('router_ip', result)
    self.assertIn('trusted_ips', result)
```

## Pre-Commit Testing

### Git Hook

**Create `.git/hooks/pre-commit`**:
```bash
#!/bin/bash

# Format code
echo "Formatting code..."
bin/format.sh

# Lint code
echo "Linting code..."
bin/lint.sh
if [ $? -ne 0 ]; then
  echo "Linting failed! Fix errors before committing."
  exit 1
fi

# Run tests
echo "Running tests..."
bin/test.sh
if [ $? -ne 0 ]; then
  echo "Tests failed! Fix tests before committing."
  exit 1
fi

echo "All checks passed!"
```

**Make executable**:
```bash
chmod +x .git/hooks/pre-commit
```

## Continuous Integration (CI)

### GitHub Actions Example

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run tests
        run: bin/test.sh

      - name: Run linter
        run: bin/lint.sh
```

## Debugging Tests

### Print Debugging

```python
def test_something(self):
    """Test with debug output"""
    result = function_under_test()
    print(f"Result: {result}")  # Will show if test fails
    self.assertEqual(result, expected)
```

**Run with print output**:
```bash
python -m unittest -v lib.module_test 2>&1
```

### Using pdb (Python Debugger)

```python
def test_something(self):
    """Test with debugger"""
    import pdb; pdb.set_trace()  # Breakpoint
    result = function_under_test()
    self.assertEqual(result, expected)
```

**Run test** (will drop into debugger):
```bash
python -m unittest lib.module_test.TestClass.test_something
```

### Logging in Tests

```python
import logging

class TestSomething(unittest.TestCase):
    def setUp(self):
        """Enable debug logging"""
        logging.basicConfig(level=logging.DEBUG)

    def test_with_logging(self):
        """Test with debug output"""
        result = function_under_test()
        logging.debug(f"Result: {result}")
        self.assertEqual(result, expected)
```

## Testing Docker Operations

### Using Docker SDK

**For testing Docker operations without subprocess**:

```python
import docker

class TestDockerOperations(unittest.TestCase):
    def setUp(self):
        """Setup Docker client"""
        self.client = docker.from_env()

    def test_container_exists(self):
        """Should find running container"""
        containers = self.client.containers.list(
            filters={"name": "test-container"}
        )
        self.assertEqual(len(containers), 1)

    def test_network_exists(self):
        """Should find proxynet network"""
        networks = self.client.networks.list(names=["proxynet"])
        self.assertEqual(len(networks), 1)
```

### Mocking Docker Operations

```python
from unittest.mock import Mock, patch

class TestDeployment(unittest.TestCase):
    @patch('docker.from_env')
    def test_deploy_creates_container(self, mock_docker):
        """Should create container via Docker SDK"""
        mock_client = Mock()
        mock_docker.return_value = mock_client

        deploy_function()

        # Verify container creation was called
        mock_client.containers.run.assert_called_once()
```

## Performance Testing

### Timing Tests

```python
import time

class TestPerformance(unittest.TestCase):
    def test_load_project_performance(self):
        """Should load project in < 100ms"""
        start = time.time()
        load_project("test-project")
        duration = time.time() - start

        self.assertLess(duration, 0.1, "Loading took too long")
```

### Load Testing (Future)

**For API load testing**:
```python
# tests/load/test_api_load.py
import locust

class APIUser(locust.HttpUser):
    @task
    def get_projects(self):
        self.client.get("/projects")

    @task
    def deploy_project(self):
        self.client.post("/projects/test/deploy")
```

**Run**:
```bash
locust -f tests/load/test_api_load.py --host http://localhost:8080
```

## Future Testing Improvements

- **Increase coverage**: Aim for 80%+ test coverage
- **Integration tests**: Automated full-stack tests
- **Contract tests**: Verify API contracts
- **Property-based testing**: Use hypothesis for edge case discovery
- **Mutation testing**: Verify test quality with mutmut
- **Performance regression testing**: Track performance over time
- **Security testing**: Automated security scans (bandit, safety)
