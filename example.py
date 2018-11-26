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
