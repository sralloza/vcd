"""Contains the links that can be downloaded."""

import os
import random
from queue import Queue

from bs4 import BeautifulSoup
from requests import Response

from vcd._requests import Downloader
from vcd.filecache import REAL_FILE_CACHE
from vcd.globals import get_logger, FILENAME_PATTERN, ROOT_FOLDER
from vcd.results import Results

DOWNLOADS_LOGGER = get_logger(name='downloads', log_format='%(message)s', filename='downloads.log')


# pylint: disable=too-many-instance-attributes
# pylint: disable=too-many-arguments
# pylint: disable=too-many-return-statements

class BaseLink:
    """Base class for Links."""

    def __init__(self, name, url, subject, downloader, queue):
        """
        Args:
            name (str): name of the url.
            url (str): URL of the url.
            subject (vcd.subject.Subject): subject of the url.
            downloader (vcd.requests.Downloader): downloader to download resources.
            queue (Queue): queue to controll threads.
        """

        self.name = name
        self.url = url
        self.subject = subject
        self.downloader = downloader
        self.queue = queue

        self.response: Response = None
        self.soup: BeautifulSoup = None
        self.filepath: str = None
        self.method = 'GET'
        self.post_data = None
        self.redirect_url = None
        self.subfolder = None
        self.logger = get_logger(__name__)
        self.logger.debug('Created %s(name=%r, url=%r, subject=%r)',
                          self.__class__.__name__, self.name, self.url, self.subject.name)

    def set_post_data(self, value):
        """Sets the post data.

        Args:
            value (dict): post data.

        """
        self.logger.debug('Set post data: %r (%r)', value, self.name)
        self.post_data = value

    def set_subfolder(self, value):
        """Sets the subfolder.

        Args:
            value (str): subfolder name.

        """
        self.logger.debug('Set subfolder: %r (%r)', value, self.name)
        self.subfolder = value

    @staticmethod
    def _process_filename(filepath: str):
        """Quits some characters from the filename that can not be in a filepath.

        Args:
            filepath (st): filepath to process.

        Returns:
            str: filepath processed.

        """
        return filepath.replace(':', '').replace('"', '').replace('/', '-').strip()

    def _get_ext_from_request(self):
        """Returns the extension of the filename of the response, got from the Content-Dispotition
        HTTP header.

        Returns:
            str: the extension.

        Raises:
            KeyError. if the request does not contain a file (no Content-Diposition header).

        """
        try:
            return FILENAME_PATTERN.search(
                self.response.headers['Content-Disposition']).group(1).split('.')[-1]
        except KeyError:
            self.logger.critical('Request does not contain a file (name=%r, url=%r,headers=%r)',
                                 self.name, self.url, self.response.headers)
            return 'unknown'

    def make_request(self):
        """Makes the request for the Link."""

        self.logger.debug('Making request')

        if self.method is None:
            raise NotImplementedError
        elif self.method == 'GET':
            self.response = self.downloader.get(self.redirect_url or self.url)

        elif self.method == 'POST':
            self.response = self.downloader.post(self.redirect_url or self.url, data=self.post_data)
        else:
            raise RuntimeError(f'Invalid method: {self.method}')

        self.logger.debug('Response obtained (%s | %s) [%d]', self.method,
                          self.response.request.method, self.response.status_code)

        if self.response.status_code == 408:
            self.logger.warning('Received response with code 408, retrying')
            return self.make_request()

    def process_request_bs4(self):
        """Parses the response with BeautifulSoup with the html parser."""

        self.soup = BeautifulSoup(self.response.text, 'html.parser')
        self.logger.debug('Response parsed')

    def autoset_filepath(self):
        """Determines the filepath of the Link."""

        if self.filepath is not None:
            self.logger.debug('Filepath is setted, skipping (%s)', self.filepath)
            return

        if self.response is None:
            raise RuntimeError('Request not launched')

        filename = self._process_filename(self.name) + '.' + self._get_ext_from_request()

        if self.subfolder is not None:
            filename = os.path.join(self.subfolder, filename)

        self.filepath = os.path.join(self.subject.name, filename)

        self.filepath = os.path.join(ROOT_FOLDER, self.filepath).replace('\\', '/')

        self.logger.debug('Set filepath: %r', self.filepath)

    def download(self):
        """Abstract method to download the Link. Must be overridden by subclasses."""
        self.logger.debug('Called download() but it was not implemented')
        raise NotImplementedError

    def save_response_content(self):
        """Saves the response content to the disk."""
        if self.filepath is None:
            self.autoset_filepath()

        self.subject.create_folder()

        if self.filepath in REAL_FILE_CACHE:
            if REAL_FILE_CACHE[self.filepath] == len(self.response.content):
                self.logger.debug('File found in cache: Same content (%d)',
                                  len(self.response.content))
                return

            self.logger.debug('File found in cache: Different content (%d --> %d)',
                              REAL_FILE_CACHE[self.filepath], len(self.response.content))
            Results.print_updated(f'File updated: {self.filepath}')
        else:
            self.logger.debug('File added to cache: %s [%d]', self.filepath,
                              len(self.response.content))
            REAL_FILE_CACHE[self.filepath] = len(self.response.content)
            Results.print_new(f'New file: {self.filepath}')

        try:
            with open(self.filepath, 'wb') as file_handler:
                file_handler.write(self.response.content)
            self.logger.debug('File downloaded and saved: %s', self.filepath)
            DOWNLOADS_LOGGER.info('Downloaded %s -- %s', self.subject.name,
                                  os.path.basename(self.filepath))
        except PermissionError:
            self.logger.warning('File couldn\'t be downloaded due to permission error: %s',
                                os.path.basename(self.filepath))
            self.logger.warning('Permission error %s -- %s', self.subject.name,
                                os.path.basename(self.filepath))


class Resource(BaseLink):
    """Representation of a resource."""

    def __init__(self, name, url, subject, downloader: Downloader, queue: Queue):
        super().__init__(name, url, subject, downloader, queue)
        self.resource_type = 'unknown'

    def set_resource_type(self, new):
        """Sets a new resource type.

        Args:
            new (str): new resource type.
        """
        self.logger.debug('Set resource type: %r', new)
        self.resource_type = new

        if self.resource_type == 'html':
            self.process_request_bs4()

    def download(self):
        """Downloads the resource."""
        self.logger.debug('Downloading resource %s', self.name)
        self.make_request()

        if self.response.status_code == 404:
            self.logger.error('status code of 404 in url %r [%r]', self.url, self.name)
            return None

        if 'application/pdf' in self.response.headers['Content-Type']:
            self.set_resource_type('pdf')
            return self.save_response_content()

        if 'officedocument.wordprocessingml.document' in self.response.headers['Content-Type']:
            self.set_resource_type('word')
            return self.save_response_content()

        if 'officedocument.spreadsheetml.sheet' in self.response.headers['Content-Type']:
            self.set_resource_type('excel')
            return self.save_response_content()

        if 'officedocument.presentationml.slideshow' in self.response.headers['Content-Type']:
            self.set_resource_type('power-point')
            return self.save_response_content()

        if 'msword' in self.response.headers['Content-Type']:
            self.set_resource_type('word')
            return self.save_response_content()

        if 'application/zip' in self.response.headers['Content-Type']:
            self.set_resource_type('zip')
            return self.save_response_content()

        if 'application/g-zip' in self.response.headers['Content-Type']:
            self.set_resource_type('gzip')
            return self.save_response_content()

        if 'application/x-7z-compressed' in self.response.headers['Content-Type']:
            self.set_resource_type('7zip')
            return self.save_response_content()

        if 'text/plain' in self.response.headers['Content-Type']:
            self.set_resource_type('plain')
            return self.save_response_content()

        if 'application/octet-stream' in self.response.headers['Content-Type']:
            self.set_resource_type('octect-stream')
            return self.save_response_content()

        if 'image/jpeg' in self.response.headers['Content-Type']:
            self.set_resource_type('jpeg')
            return self.save_response_content()

        if 'text/html' in self.response.headers['Content-Type']:
            self.set_resource_type('html')
            return self.parse_html()

        if self.response.status_code % 300 < 100:
            self.url = self.response.headers['Location']
            self.logger.warning('Redirecting to %r', self.url)
            return self.download()

        self.logger.error('Content not identified: %r (code=%s, header=%r)',
                          self.url, self.response.status_code, self.response.headers)
        return None

    def parse_html(self):
        """Parses a HTML response."""
        self.set_resource_type('html')
        self.logger.debug('Parsing HTML (%r)', self.url)
        resource = self.soup.find('object', {'id': 'resourceobject'})
        name = self.soup.find('div', {'role': 'main'}).h2.text

        try:
            resource = Resource(name, resource['data'], self.subject, self.downloader, self.queue)
            self.logger.debug('Created resource from HTML: %r, %s', resource.name, resource.url)
            self.subject.queue.put(resource)
            return
        except TypeError:
            pass

        try:
            resource = self.soup.find('iframe', {'id': 'resourceobject'})
            resource = Resource(name, resource['src'], self.subject, self.downloader, self.queue)
            self.logger.debug('Created resource from HTML: %r, %s', resource.name, resource.url)
            self.subject.queue.put(resource)
            return
        except TypeError:
            random_name = str(random.randint(0, 1000))
            self.logger.exception('HTML ERROR (ID=%s)', random_name)
            self.logger.error('ERROR LINK: %s', self.url)
            self.logger.error('ERROR HEADS: %s', self.response.headers)

            with open(random_name + '.html', 'wb') as file_handler:
                file_handler.write(self.response.content)


class Folder(BaseLink):
    """Representation of a folder."""

    def make_subfolder(self):
        """Makes a subfolder to save the folder's links."""
        folder = os.path.join(ROOT_FOLDER, self.subject.name, self.name).replace('\\', '/')
        if os.path.isdir(folder) is False:
            self.logger.debug('Created folder: %s', folder)
            os.mkdir(folder)

    def download(self):
        """Downloads the folder."""
        self.logger.debug('Downloading folder %s', self.name)
        self.make_request()
        self.process_request_bs4()
        self.make_subfolder()

        containers = self.soup.findAll('span', {'class': 'fp-filename-icon'})

        for container in containers:
            try:
                url = container.a['href']
                resource = Resource(os.path.splitext(container.a.text)[0],
                                    url, self.subject, self.downloader, self.queue)
                resource.set_subfolder(self.name)
                self.logger.debug('Created resource from folder: %r, %s',
                                  resource.name, resource.url)
                self.queue.put(resource)

            except TypeError:
                continue


class Forum(BaseLink):
    """Representation of a Forum link."""

    def download(self):
        """Downloads the resources found in the forum hierarchy."""
        self.logger.debug('Downloading forum %s', self.name)
        self.make_request()
        self.process_request_bs4()

        if 'view.php' in self.url:
            self.logger.debug('Forum is type list of themes')
            themes = self.soup.findAll('td', {'class': 'topic starter'})

            for theme in themes:
                forum = Forum(theme.text, theme.a['href'], self.subject, self.downloader,
                              self.queue)
                self.logger.debug('Created forum from forum: %r, %s', forum.name, forum.url)
                self.queue.put(forum)

        elif 'discuss.php' in self.url:
            self.logger.debug('Forum is a theme discussion')
            attachments = self.soup.findAll('div', {'class': 'attachments'})

            for attachment in attachments:
                try:
                    resource = Resource(os.path.splitext(attachment.text)[0], attachment.a['href'],
                                        self.subject, self.downloader, self.queue)
                    self.logger.debug('Created resource from forum: %r, %s', resource.name,
                                      resource.url)
                    self.queue.put(resource)
                except TypeError:
                    continue
        else:
            self.logger.critical('Unkown url for forum %r. Vars: %r', self.url, vars())
            raise RuntimeError(f'Unknown url for forum: {self.url}')


class Delivery(BaseLink):
    """Representation of a delivery link."""

    def download(self):
        """Downloads the resources found in the delivery."""
        self.logger.debug('Downloading delivery %s', self.name)
        self.make_request()
        self.process_request_bs4()

        links = []
        containers = self.soup.findAll('a', {'target': '_blank'})

        for container in containers:
            resource = Resource(os.path.splitext(container.text)[0], container['href'],
                                self.subject, self.downloader, self.queue)
            self.logger.debug('Created resource from delivery: %r, %s', resource.name,
                              resource.url)
            links.append(resource)

        names = [link.name for link in links]
        dupes = {x for x in names if names.count(x) > 1}
        dupes_counters = {x: 1 for x in dupes}

        if dupes:
            for i, _ in enumerate(links):
                if links[i].name in dupes:
                    name = links[i].name
                    links[i].name += '_' + str(dupes_counters[name])
                    dupes_counters[name] += 1
                    self.logger.debug('Changed name %r -> %r', name, links[i].name)

        for link in links:
            self.queue.put(link)