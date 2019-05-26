"""File downloader for the Virtual Campus of the Valladolid Unversity."""

import asyncio
import logging
import os
import time

from bs4 import BeautifulSoup
from colorama import init, Fore
from logging.handlers import RotatingFileHandler
from threading import current_thread

from ._requests import Downloader
from ._threading import run
from .credentials import Credentials
from .options import Options
from .subject import Subject
from .time_operations import seconds_to_str


if os.path.isdir('logs') is False:
    os.mkdir('logs')

if os.environ.get('TESTING') is None:
    should_roll_over = os.path.isfile('logs/vcd.log')

    fmt = "[%(asctime)s] %(levelname)s - %(threadName)s.%(module)s:%(lineno)s - %(message)s"
    handler = RotatingFileHandler(filename='logs/vcd.log', maxBytes=2_500_000,
                                  encoding='utf-8', backupCount=5)

    current_thread().setName('MT')

    if should_roll_over:
        handler.doRollover()

    logging.basicConfig(handlers=[handler, ], level=logging.DEBUG, format=fmt)

logging.getLogger('urllib3').setLevel(logging.ERROR)

logger = logging.getLogger(__name__)


# noinspection PyShadowingNames

async def find_subjects():
    async with Downloader() as downloader:
        await _find_subjects(downloader)


async def _find_subjects(downloader):
    """Starts finding subjects.

    Args:
        downloader (Downloader): custom session with retry control.

    Returns:

    """
    logger = logging.getLogger(__name__)
    logger.debug('Finding subjects')


    user = Credentials.get()

    await downloader.post(
        'https://campusvirtual.uva.es/login/index.php',
        data={'anchor': '', 'username': user.username, 'password': user.password})

    response = await downloader.get('https://campusvirtual.uva.es/my/')

    logger.debug('Returned primary response with code %d', response.status)

    response_text = await response.text()

    logger.debug('Login correct: %s', 'Vista general de cursos' in response_text)

    if 'Vista general de cursos' not in response_text:
        exit(Fore.RED + 'Login not correct' + Fore.RESET)

    soup = BeautifulSoup(response_text, 'html.parser')
    search = soup.findAll('div', {'class': 'course_title'})

    logger.debug('Found %d potential subjects', len(search))
    subjects = []

    for find in search:
        name = find.h2.a['title'].split(' (')[0]
        subject_url = find.h2.a['href']

        if 'grado' in name.lower():
            continue

        logger.debug('Assembling subject %r', name)
        subjects.append(Subject(name, subject_url, downloader))

    subjects.sort(key=lambda x: x.name)

    for i, _ in enumerate(subjects):
        await run(subjects[i])

    for subject in subjects:
        for link in subject.notes_links:
            await run(link)

    return subjects


def start(root_folder=None, nthreads=50, timeout=None):
    """Starts the app."""
    init()

    if root_folder:
        Options.set_root_folder(root_folder)

    if timeout:
        Options.set_timeout(timeout)

    initial_time = time.time()
    main_logger = logging.getLogger(__name__)
    main_logger.info('STARTING APP')

    main_logger.debug('Launching subjects finder')
    asyncio.run(find_subjects())

    final_time = time.time() - initial_time
    main_logger.info('VCD executed in %s', seconds_to_str(final_time))
