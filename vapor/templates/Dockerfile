FROM python:3.6

RUN curl -sSL https://raw.githubusercontent.com/sdispater/poetry/master/get-poetry.py | python
RUN /root/.poetry/bin/poetry config settings.virtualenvs.create false

RUN mkdir /app
WORKDIR /app

COPY vapor_pyproject.toml pyproject.toml
RUN /root/.poetry/bin/poetry install -n

{% for item in post_install %}
RUN {{ item }}
{% endfor %}

COPY ./main.py /app/main.py
CMD python3 main.py
