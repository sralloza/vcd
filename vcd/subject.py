"""Contains all related to subjects."""

import logging
import os
from _sha1 import sha1
from threading import Lock

from bs4 import BeautifulSoup
from requests import Response

from .options import Options

from vcd.alias import Alias
from vcd.links import BaseLink, Resource, Delivery, Forum, Folder


class Subject:
    """Representation of a subject."""

    def __init__(self, name, url, downloader):
        """

        Args:
            name (str): name of the subject.
            url (str): url of the subject.
            downloader (Downloader): downloader to download files.
        """

        if ' ' in name:
            name = name.capitalize()

        self.name = Alias.real_to_alias(sha1(url.encode()).hexdigest(), name)
        self.url = url
        self.downloader = downloader

        self.response: Response = None
        self.soup: BeautifulSoup = None
        self.notes_links = []
        self.folder_lock = Lock()
        self.hasfolder = False
        self.foldername = os.path.join(Options.ROOT_FOLDER, self.name)
        self.logger = logging.getLogger(__name__)

        self.logger.debug('Created Subject(name=%r, url=%r)',
                          self.name, self.url)

    def __repr__(self):
        return f'Subject(name={self.name!r}, url={self.url!r}, ' \
            f'{len(self.notes_links)} notes links)'

    def __str__(self):
        return f'{self.name}'

    async def make_request(self):
        """Makes the primary request."""
        self.logger.debug('Making subject request')
        self.response = await self.downloader.get(self.url)
        self.soup = BeautifulSoup(await self.response.text(), 'html.parser')

        self.logger.debug('Response obtained [%d]', self.response.status)
        self.logger.debug('Response parsed')

    def create_folder(self):
        """Creates the folder named as self."""
        if self.hasfolder is False:
            self.logger.debug('Creating folder %r', self.name)
            with self.folder_lock:
                if os.path.isdir(self.foldername) is False:
                    os.mkdir(self.foldername)
            self.hasfolder = True
        else:
            self.logger.debug('Folder already exists: %r', self.name)

    def add_link(self, url: BaseLink):
        """Adds a note url to the list."""
        self.logger.debug('Adding url: %s', url.name)
        self.notes_links.append(url)

    async def find_links(self):
        """Finds the links downloading the primary page."""
        self.logger.debug('Finding links of %s', self.name)
        await self.make_request()

        _ = [x.extract() for x in self.soup.findAll('span', {'class': 'accesshide'})]
        _ = [x.extract() for x in self.soup.findAll('div', {'class': 'mod-indent'})]

        search = self.soup.findAll('div', {'class', 'activityinstance'})

        for find in search:
            try:
                name = find.a.span.text
                url = find.a['href']

                if 'resource' in url:
                    self.logger.debug('Created Resource (subject search): %r, %s', name, url)
                    self.add_link(Resource(name, url, self, self.downloader))
                elif 'folder' in url:
                    self.logger.debug('Created Folder (subject search): %r, %s', name, url)
                    self.add_link(Folder(name, url, self, self.downloader))
                elif 'forum' in url:
                    self.logger.debug('Created Forum (subject search): %r, %s', name, url)
                    self.add_link(Forum(name, url, self, self.downloader))
                elif 'assign' in url:
                    self.logger.debug('Created Delivery (subject search): %r, %s', name, url)
                    self.add_link(Delivery(name, url, self, self.downloader))

            except AttributeError:
                pass

        self.logger.debug('Downloading files for subject %r', self.name)
