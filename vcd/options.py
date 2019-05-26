import os
import re
from configparser import ConfigParser, NoSectionError

from colorama import Fore, init

init()


class OptionError(Exception):
    """Option error."""


class Options:
    _CONFIG_PATH = os.path.expanduser('~') + '/vcd-config.ini'
    PRODUCTION = False
    FILENAME_PATTERN = re.compile('filename=\"?([\w. ]*)\"?')
    ROOT_FOLDER = 'D:/sistema/desktop/-vi3'
    TIMEOUT = 30

    @staticmethod
    def create_root_folder():
        if os.path.isdir(Options.ROOT_FOLDER) is False:
            os.mkdir(Options.ROOT_FOLDER)

    @staticmethod
    def set_root_folder(root_folder):
        Options.ROOT_FOLDER = root_folder
        Options.create_root_folder()

    @staticmethod
    def set_timeout(timeout: int):
        if not isinstance(timeout, int):
            raise TypeError(f'Timeout must be int, not {type(timeout).__name__}')

        Options.TIMEOUT = timeout

    @staticmethod
    def load_config():
        config = ConfigParser()
        config.read(Options._CONFIG_PATH)
        try:
            root_folder = config.get('OPTIONS', 'ROOT_FOLDER')
            timeout = config.get('OPTIONS', 'TIMEOUT')
        except NoSectionError:
            config['OPTIONS'] = {'ROOT_FOLDER': 'ROOT_FOLDER_PATH', 'TIMEOUT': 30}
            with open(Options._CONFIG_PATH, 'wt', encoding='utf-8') as fh:
                config.write(fh)

            return exit(Fore.RED + 'Invalid Options' + Fore.RESET)

        Options.set_root_folder(root_folder)
        Options.set_timeout(int(timeout))


Options.load_config()
Options.create_root_folder()
