import logging
import os
import shutil
from threading import current_thread

import pytest


def pytest_configure():
    os.environ['TESTING'] = '1'

    from vcd import Options, Credentials
    Options.set_root_folder('temp_tests')
    Credentials.path = 'test.' + Credentials.path

    fmt = "[%(asctime)s] %(levelname)s - %(threadName)s.%(module)s:%(lineno)s - %(message)s"
    handler = logging.FileHandler(filename='testing.log', encoding='utf-8')

    current_thread().setName('MT')

    logging.basicConfig(handlers=[handler, ], level=logging.DEBUG, format=fmt)
    logging.getLogger('urllib3').setLevel(logging.ERROR)


@pytest.fixture(scope='session', autouse=True)
def teardown_everything():
    yield

    from vcd import Credentials

    if os.path.isdir('temp_tests'):
        shutil.rmtree('temp_tests')

    logging.shutdown()

    if os.path.isfile('testing.log'):
        os.remove('testing.log')

    if os.path.isfile(Credentials.path):
        os.remove(Credentials.path)

    assert not os.path.isdir('temp_tests')
    assert not os.path.isfile('testing.log')
    assert not os.path.isfile(Credentials.path)
