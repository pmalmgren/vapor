## vapor

`vapor` is a Python library that aims to make cloud and serverless development simple. It does this by turning functions into running servers.

The goal of `vapor` is to provide a tighter feedback loop that can be used to rapidly develop, prototype, and test cloud services and functions.

## Example: Word tokenization

### vapor.toml

```toml
[tool.vapor]

[environments]
    [environments.py3]
    configuration = "poetry"
    [tool.poetry.dependencies]
    python = ">=3.5"
    requests = "@2.20.1"
    nltk = "@3.3"
    beautifulsoup4 = "@4.6.3"

[execution]
    engine = "docker"
    mode = "parallel"
    [execution.configuration]
    base-dockerfile = "Dockerfile"
```

### words.py

```python
import asyncio

import vapor


def process_page(url=None):
    """parses, stems, and tokenizes the content of a specified URL"""
    from bs4 import BeautifulSoup
    import nltk
    import requests

    porter = nltk.PorterStemmer()

    result = requests.get(url)
    result.raise_for_status()

    soup = BeautifulSoup(result.text)
    tokens = nltk.word_tokenize(soup.text)

    return [porter.stem(token) for token in tokens]


async def main():
    tokenized_results = await vapor.gather(
        call_args=[
            {'url': 'https://en.wikipedia.org/wiki/Actor_model'},
            {'url': 'https://en.wikipedia.org/wiki/Python_(programming_language)'},
            {'url': 'https://en.wikipedia.org/wiki/Linear_logic'},
        ],
        fn=process_page,
        env='py3',
        post_install_items=['python -m nltk.downloader punkt'],
    )

    print(tokenized_results)


loop = asyncio.get_event_loop()
task = loop.create_task(main())
loop.run_until_complete(
    task
)
```

## Example: TDD with Helm

Oftentimes when developers build services with Kubernetes, Amazon Lambda, or inside any other cloud infrastructure, the feedback loop and developer experience is somewhat lacking. `vapor` can help here by providing `pytest` bindings which can help you programatically verify that things are working as expected.

*Note: You will need to make sure the `example-service` Helm chart is loaded into your cluster's Tiller instance for this example to work.*

### vapor.toml

```toml
[tool.vapor]

[environments]
    [environments.py3]
    configuration = "poetry"
    [tool.poetry.dependencies]
    python = ">=3.6"

[execution]
    engine = "helm"
    [execution.configuration]
        image-repo = "hub.docker.com"
        tag-prefix = "peterzap"
        kubernetes-host = "192.168.99.101"           # minikube ip
        service-type = "Ingress"                     # we can also expose NodePorts
        chart = "example-service"
        config-directory = "~/.vapor-chart-configs"  # the compiled chart configs go here
```

### test_helm_function.py

```python
import pytest

from vapor import bootstrap_synchronous, testing


def helm_function(name=''):
    return {
        'message': f'Hello {name}!'
    }


@pytest.fixture(scope='module')
def deployed_helm_chart(request):
    """Starts and loads the Helm chart"""
    helm_function = bootstrap_synchronous(
        fn=helm_function,
        env='py3',
        conf='vapor.toml',
    )

    def fin():
        helm_function.stop()

    request.addfinalizer(fin)
    return helm_function


def test_helm_chart_infra(deployed_helm_chart):
    """vapor bootstrap should create pods, a deployment, a service, and an ingress to access the service"""
    testing.assertPodsRunning(deployed_helm_chart.pods)
    testing.assertDeploymentsRunning(deployed_helm_chart.deployment)
    testing.assertServiceRunning(deployed_helm_chart.service)
    testing.assertIngressRunning(deployed_helm_chart.ingress)

def test_helm_function_response(deployed_helm_chart, event_loop):
    """the bootstrapped helm function should return the data"""
    resp = requests.get(deployed_helm_chart.host, data={'name': 'test client'})
    assert resp.status_code == 200
    assert resp.json['message'] == 'Hello test client!'
```

## How `vapor` works

`vapor` executes code in the cloud by using execution engines, which are defined as any computing envronment that can run Python code. The two cloud computing environments that `vapor` is designed to work with (at the moment) are Kubernetes and Docker.

The goal of `vapor` is to make executing code in a cloud computing environment as simple as possible. `vapor` relies on the environment, configuration files, a few templates, and the following assumptions:

1) A valid Python function,
2) A correctly-specified set of dependencies, and
3) Access to the desired execution engine (Docker or Kubernetes)

If these requirements are met, `vapor` will start servers, make the specified calls, and return the output. It will also generate artifacts, such as Dockerfiles, compiled docker images, and helm charts that can be used to deploy the service. The goal is to provide a tight feedback loop that can be used to rapidly develop, prototype, and test cloud services and functions.

## Execution engines

### Docker

### Kubernetes

### Helm Charts

### Amazon Lambda

### Google Cloud Functions

### Microsoft Azure Functions
