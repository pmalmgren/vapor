## vapor

vapor is a Python library that aims to make distributed programming simple.

## `vapor.toml`

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
    base-dockerfile: "Dockerfile"
```

## `main.py`

```python
import asyncio
from vapor import run_remotely

async def main():

    @run_remotely(env='python3', keyed_arg='url')
    async def process_page(url):
        """parses, stems, and tokenizes the content of a specified URL"""
        from bs4 import BeautifulSoup
        import nltk
        import requests

        porter = nltk.PorterStemmer()

        result = requests.get(url)
        result.raise_for_status()

        raw = BeautifulSoup(response.text)
        tokens = word_tokenize(raw)

        return [porter.stem(token) for token in tokens]

    tokenized_results = await asyncio.gather(
        process_page('https://en.wikipedia.org/wiki/Actor_model'),
        process_page('https://en.wikipedia.org/wiki/Python_(programming_language)'),
        process_page('https://en.wikipedia.org/wiki/Linear_logic'),
    )

    print(tokenized_results)
```

```
$ ./main.py
...
Magic happens
```

## How the example works

  1. vapor bootstraps an execution environment by building a Docker image
  2. vapor provisions and installs all dependencies using Poetry
  3. vapor launches Docker containers
  4. Application code is shipped to
  5. Results are gathered and sent back to the application

## Execution engines

### Docker

### Kubernetes
