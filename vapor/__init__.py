__version__ = '0.0.1'

import asyncio
import inspect
import hashlib
import os
import time
import typing
from aiohttp import ClientSession, TCPConnector
from shutil import copyfile

import docker
import toml
from jinja2 import Template
from kubernetes import client, config

from .types import DeployedService


TMP_DIR_ROOT = os.path.expanduser('~/.bffs')
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates')
DEFAULT_PORT = '9999/tcp'
MAIN_PY = """
from starlette.endpoints import HTTPEndpoint
from starlette.routing import Route, Router
from starlette.responses import JSONResponse
import uvicorn

KWARGS = {kwargs}

def unpack_kwargs(request, kwargs):
    return {{
        kwarg: request.query_params.get(kwarg)
        for kwarg in kwargs
    }}

{fn}

class vaporEndpoint(HTTPEndpoint):
    async def get(self, request):
        fn_kwargs = unpack_kwargs(request, KWARGS)
        fn_result = {fn_name}(**fn_kwargs)
        return JSONResponse({{
            'result': fn_result
        }})


app = Router([
    Route('/', endpoint=vaporEndpoint, methods=['GET']),
])

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=9999)
"""


async def fetch(url, session, params):
    async with session.get(url, params=params) as response:
        return await response.text()


async def execute_with_docker(client, image_tag, call_args, docker_host='localhost'):
    print('Looking for containers.')
    containers = client.containers.list(filters={'ancestor': image_tag})
    if not containers:
        print('No containers found, creating them now.')
        for _ in enumerate(call_args):
            containers.append(
                client.containers.run(image_tag, ports={DEFAULT_PORT: 0}, detach=True)
            )
    else:
        print(f'Discovered {len(containers)} running containers: {containers}')

    print('Executing requests.')
    async def fetch_all():
        async with ClientSession(connector=TCPConnector(verify_ssl=False)) as session:
            tasks = []
            for idx, arg in enumerate(call_args):
                container = containers[
                    idx % len(containers)
                ]
                port = container.attrs['NetworkSettings']['Ports'][DEFAULT_PORT][0]['HostPort']
                url = f'http://{docker_host}:{port}/'
                task = asyncio.ensure_future(fetch(url, session, arg))
                tasks.append(task)

            responses = await asyncio.gather(*tasks)
            return responses

    return await fetch_all()


def deployment_is_ready(deployment: client.ExtensionsV1beta1Deployment) -> bool:
    status = deployment.status
    if (status.updated_replicas == deployment.spec.replicas and
    status.replicas == deployment.spec.replicas and
    status.available_replicas == deployment.spec.replicas and
    status.observed_generation >= deployment.metadata.generation):
        return True


def deploy_and_wait_until_ready(api_instance, deployment_name, image_tag, namespace, timeout=60):
    container = client.V1Container(
        name=f'{deployment_name}',
        image=f'{image_tag}',
        ports=[client.V1ContainerPort(container_port=9999)]
    )
    # Create and configurate a spec section
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={'app': f'{deployment_name}'}),
        spec=client.V1PodSpec(containers=[container])
    )
    # Create the specification of deployment
    spec = client.ExtensionsV1beta1DeploymentSpec(
        replicas=3,
        template=template
    )
    # Instantiate the deployment object
    deployment_body = client.ExtensionsV1beta1Deployment(
        api_version='extensions/v1beta1',
        kind='Deployment',
        metadata=client.V1ObjectMeta(name=f'{deployment_name}'),
        spec=spec
    )
    api_response = api_instance.create_namespaced_deployment(
        body=deployment_body,
        namespace=namespace
    )
    print(f'Deployment created. status={api_response.status}')
    start = time.time()
    while time.time() - start < timeout:
        time.sleep(1)
        response = api_instance.read_namespaced_deployment_status(deployment_name, namespace)
        if deployment_is_ready(response):
            return True
        else:
            print(f'[updated_replicas:{response.status.updated_replicas},replicas:{response.status.replicas}'
                  f',available_replicas:{response.status.available_replicas},observed_generation:{response.status.observed_generation}] waiting...')

    raise RuntimeError(f'Waiting timeout for deployment {deployment_name}')


def expose_service(api_instance, service_name, namespace, service_type):
    service_body = client.V1Service(
        metadata=client.V1ObjectMeta(name=f'{service_name}'),
        spec=client.V1ServiceSpec(
            type='NodePort',
            selector={'app': f'{service_name}'},
            ports=[client.V1ServicePort(
                protocol='TCP',
                port=9999,
                name=f'{service_name}',
            )]
        )
    )
    service = api_instance.create_namespaced_service(
        namespace=namespace,
        body=service_body,
    )
    return service


def build_ingress(beta_api_instance, service_name, namespace, ingress_host=None):
    path = client.V1beta1HTTPIngressPath(
        path=f'/{service_name}',
        backend=client.V1beta1IngressBackend(
            service_name=service_name,
            service_port=9999,
        )
    )
    ingress_body = client.V1beta1Ingress(
        metadata=client.V1ObjectMeta(
            name=f'{service_name}-external',
            annotations={'nginx.ingress.kubernetes.io/rewrite-target': '/'}
        ),
        spec=client.V1beta1IngressSpec(
            rules=[client.V1beta1IngressRule(
                http=client.V1beta1HTTPIngressRuleValue(
                    paths=[path],
                ),
            )]
        )
    )
    if ingress_host:
        ingress_body = client.V1beta1Ingress(
            metadata=client.V1ObjectMeta(
                name=f'{service_name}-external',
            ),
            spec=client.V1beta1IngressSpec(
                rules=[client.V1beta1IngressRule(
                    host=ingress_host,
                    http=client.V1beta1HTTPIngressRuleValue(
                        paths=[path],
                    ),
                )]
            )
        )
    beta_api_instance.create_namespaced_ingress(
        namespace, ingress_body
    )


async def execute_with_k8s(image_tag, call_args, fn_name, namespace='default', kubernetes_host=None, service_type='NodePort', ingress_host=None):
    config.load_kube_config()
    api_instance = client.ExtensionsV1beta1Api()
    api_instance_2 = client.CoreV1Api()
    fn_name = fn_name.replace('_', '-')
    kubernetes_host = kubernetes_host or fn_name

    deployments = api_instance.list_namespaced_deployment(namespace=namespace)
    existing_deployment = False
    if len(deployments.items) > 0:
        for deployment in deployments.items:
            image_match = False
            deployment_ready = False
            running_containers = deployment.spec.template.spec.containers
            if len(running_containers) > 0:
                for container in running_containers:
                    if container.image == image_tag:
                        image_match = True
            status_conditions = deployment.status.conditions
            if len(status_conditions) > 0:
                if status_conditions[0].status == 'True':
                    deployment_ready = True

            if image_match and deployment_ready:
                print(f'Found existing deployment {deployment.metadata.name} with {deployment.status.replicas} containers.')
                existing_deployment = True
                break

    if not existing_deployment:
        deploy_and_wait_until_ready(api_instance, fn_name, image_tag, namespace)

    services = api_instance_2.list_namespaced_service(namespace=namespace)
    existing_service = False
    if len(services.items) > 0:
        for service in services.items:
            if service.metadata.name == fn_name:
                print(f'Found existing service: {fn_name}')
                existing_service = True
                break

    if not existing_service:
        service = expose_service(api_instance_2, fn_name, namespace, service_type)

    if service_type == 'Ingress':
        ingress = api_instance.list_namespaced_ingress(namespace)
        existing_ingress = False
        if len(ingress.items) > 0:
            for ingress in ingress.items:
                if ingress.metadata.name == f'{fn_name}-external':
                    existing_ingress = True

        if not existing_ingress:
            build_ingress(api_instance, fn_name, namespace, ingress_host=ingress_host)

    node_port = service.spec.ports[0].node_port
    url = f'http://{kubernetes_host}:{node_port}/'
    if service_type == 'Ingress':
        url = f'https://{kubernetes_host}/{fn_name}'

    print('Executing requests.')
    async def fetch_all():
        async with ClientSession(connector=TCPConnector(verify_ssl=False)) as session:
            tasks = []
            for arg in call_args:
                task = asyncio.ensure_future(fetch(url, session, arg))
                tasks.append(task)

            responses = await asyncio.gather(*tasks)
            return responses

    return await fetch_all()


async def execute_with_helm(image_tag: str, call_args: str, fn_name: str, config_directory: str, chart: str):
    return await None


async def gather(call_args=None, fn=None, env=None, post_install_items=None):
    with open('vapor.toml') as vapor_conf:
        parsed_toml = toml.loads(vapor_conf.read())

    if env not in parsed_toml.get('environments'):
        raise AssertionError('env not found in vapor.toml')

    try:
        os.stat(TMP_DIR_ROOT)
    except FileNotFoundError:
        os.mkdir(TMP_DIR_ROOT)

    dependencies = parsed_toml.get('environments').get(env).get('dependencies')
    python_version = dependencies.pop('python')  # TODO: Do something with the Python version?

    fn_src = inspect.getsource(fn)
    fn_hash = hashlib.md5(fn_src.encode()).hexdigest()
    dir_name = f'{TMP_DIR_ROOT}/{fn.__name__}-{fn_hash}'
    build_image = False

    try:
        os.stat(dir_name)
    except FileNotFoundError:
        os.mkdir(dir_name)
        build_image = True

    client = docker.from_env()
    tag_prefix = parsed_toml.get('execution').get('configuration').get('tag-prefix')
    image_tag =f'{tag_prefix}/{fn.__name__}-{fn_hash}'

    if build_image:
        compiled_main_py = MAIN_PY.format(
            kwargs=['url'],
            fn=fn_src,
            fn_name=fn.__name__,
        )
        with open(f'{TEMPLATES_DIR}/Dockerfile', 'r') as template_file:
            dockerfile_template = Template(template_file.read())

        with open(f'{TEMPLATES_DIR}/vapor_pyproject.toml', 'r') as poetry_file:
            poetry_template = Template(poetry_file.read())

        rendered_poetry_config = poetry_template.render(dependencies=dependencies)
        rendered_template = dockerfile_template.render(post_install=post_install_items)

        with open(f'{dir_name}/Dockerfile', 'w') as dockerfile:
            dockerfile.write(rendered_template)
        with open(f'{dir_name}/main.py', 'w') as main_py:
            main_py.write(compiled_main_py)
        with open(f'{dir_name}/vapor_pyproject.toml', 'w') as vapor_pyproject:
            vapor_pyproject.write(rendered_poetry_config)

        response = [line for line in client.api.build(path=dir_name, rm=True, tag=image_tag)]
        print(response)

        for line in client.images.push(f'{image_tag}', stream=True):
            print(line)

    if parsed_toml.get('execution').get('engine') == 'docker':
        docker_host = parsed_toml.get('execution').get('configuration').get('docker-host')
        return await execute_with_docker(client, image_tag, call_args, docker_host=docker_host)

    if parsed_toml.get('execution').get('engine') == 'k8s':
        kubernetes_host = parsed_toml.get('execution').get('configuration').get('kubernetes-host')
        namespace = parsed_toml.get('execution').get('configuration').get('namespace') or 'default'
        service_type = parsed_toml.get('execution').get('configuration').get('service-type')
        ingress_host = parsed_toml.get('execution').get('configuration').get('ingress-host')
        return await execute_with_k8s(
            image_tag, call_args, fn.__name__, kubernetes_host=kubernetes_host, namespace=namespace, service_type=service_type, ingress_host=ingress_host
        )

    if parsed_toml.get('execution').get('engine') == 'helm':
        config_directory = parsed_toml.get('execution').get('configuration').get('config-directory')
        chart = parsed_toml.get('execution').get('configuration').get('chart')
        ingress_host = parsed_toml.get('execution').get('configuration').get('ingress-host')
        return await execute_with_helm(
            image_tag, call_args, fn.__name__, config_directory, chart
        )


def bootstrap(fn: typing.Callable[[str], typing.Dict[str, str]], conf: str = 'vapor.toml') -> DeployedService:
    return DeployedService()
