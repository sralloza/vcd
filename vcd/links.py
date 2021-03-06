"""Contains the links that can be downloaded."""
import logging
import os
import random
import unidecode
import warnings

from _sha1 import sha1
from queue import Queue

from bs4 import BeautifulSoup
from requests import Response

from ._requests import Downloader
from .alias import Alias
from .filecache import REAL_FILE_CACHE
from .options import Options
from .results import Results
from .utils import secure_filename


class DownloadsRecorder:
    _downloads_record_path = os.path.join(Options.ROOT_FOLDER, 'downloads.log')

    @staticmethod
    def write(something: str, *args):
        with open(DownloadsRecorder._downloads_record_path, 'at') as fh:
            fh.write(something % args + '\n')


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

        self.name = name.strip()
        self.url = url
        self.subject = subject
        self.downloader = downloader
        self.queue = queue

        self.response: Response = None
        self.soup: BeautifulSoup = None
        self.filepath: str = None
        self.redirect_url = None
        self.response_name = None
        self.subfolders = []

        self.logger = logging.getLogger(__name__)
        self.logger.debug('Created %s(name=%r, url=%r, subject=%r)',
                          self.__class__.__name__, self.name, self.url, self.subject.name)

    @property
    def content_disposition(self):
        if self.response is None:
            raise RuntimeError('Response not made yet')

        return unidecode.unidecode(self.response.headers['Content-Disposition'])

    def append_subfolder(self, dirname):
        dirname = secure_filename(dirname)
        return self.subfolders.append(dirname)

    def insert_subfolder(self, index, dirname):
        dirname = secure_filename(dirname)
        return self.subfolders.insert(index, dirname)

    def create_subfolder(self):
        """Creates the subfolder, if it is configured."""
        self.create_subject_folder()

        if not self.filepath:
            self.autoset_filepath()

        folder = os.path.normpath(os.path.dirname(self.filepath))

        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
            self.logger.debug('Created subfolder %r', folder)
        else:
            self.logger.debug('Subfolder already exists %r', folder)

    @staticmethod
    def _process_filename(filepath: str):
        """Quits some characters from the filename that can not be in a filepath.

        Args:
            filepath (st): filepath to process.

        Returns:
            str: filepath processed.

        """

        filepath = filepath.replace('>', ' mayor que ')
        filepath = filepath.replace('<', ' menor que ')

        return filepath

    # @staticmethod
    def _filename_to_ext(self, filename):
        """Returns the extension given a filename."""
        if filename.count('.') == 0:
            return 'ukn'
        return filename.split('.')[-1].lower()

    def _get_ext_from_response(self):
        """Returns the extension of the filename of the response, got from the Content-Dispotition
        HTTP header.

        Returns:
            str: the extension.

        """

        if self.response_name is not None:
            return self._filename_to_ext(self.response_name)

        try:
            # unidecode.unidecode is used to remove accents.
            self.response_name = Options.FILENAME_PATTERN.search(self.content_disposition).group(1)
            return self._filename_to_ext(self.response_name)
        except KeyError:
            pass

        self.response_name = os.path.basename(self.url)
        return self._filename_to_ext(self.response_name) or 'ukn'

    def create_subject_folder(self):
        """Creates the subject's principal folder."""
        return self.subject.create_folder()

    def make_request(self):
        """Makes the request for the Link."""

        self.logger.debug('Making request')

        self.response = self.downloader.get(self.redirect_url or self.url, timeout=Options.TIMEOUT)

        self.logger.debug('Response obtained [%d]', self.response.status_code)

        if self.response.status_code == 408:
            self.logger.warning('Received response with code 408, retrying')
            return self.make_request()

    def close_connection(self):
        warnings.warn('Since streams are not used, this method should not be called',
                      DeprecationWarning)
        self.logger.debug('Closing connection')
        self.response.close()

    def process_request_bs4(self):
        """Parses the response with BeautifulSoup with the html parser."""

        self.logger.debug('Parsing response (bs4)')
        self.soup = BeautifulSoup(self.response.text, 'html.parser')
        self.logger.debug('Response parsed (bs4)')

    def autoset_filepath(self):
        """Determines the filepath of the Link."""

        if self.filepath is not None:
            self.logger.debug('Filepath is setted, skipping (%s)', self.filepath)
            return

        if self.response is None:
            raise RuntimeError('Request not launched')

        filename = self._process_filename(self.name) + '.' + self._get_ext_from_response()
        filename = secure_filename(filename)

        # if self.subfolder is not None:
        #     filename = os.path.join(self.subfolder, filename)

        if self.subfolders:
            filename = os.path.join(*self.subfolders, filename)

        self.filepath = os.path.join(self.subject.folder, filename)

        self.filepath = os.path.normpath(os.path.join(Options.ROOT_FOLDER, self.filepath))

        self.filepath = Alias.real_to_alias(sha1(self.url.encode()).hexdigest(), self.filepath)

        self.logger.debug('Set filepath: %r', self.filepath)

    def download(self):
        """Abstract method to download the Link. Must be overridden by subclasses."""
        self.logger.debug('Called download() but it was not implemented')
        raise NotImplementedError

    def get_header_length(self):
        try:
            return int(self.response.headers['Content-Length'])
        except KeyError:
            return len(self.response.content)

    @property
    def content_type(self):
        if 'Content-Type' in self.response.headers:
            return self.response.headers['Content-Type']

        return None

    def save_response_content(self):
        """Saves the response content to the disk."""
        if self.filepath is None:
            self.autoset_filepath()

        self.create_subject_folder()
        self.create_subfolder()

        self.logger.debug('filepath in REAL_FILE_CACHE: %s', self.filepath in REAL_FILE_CACHE)

        if self.filepath in REAL_FILE_CACHE:
            if REAL_FILE_CACHE[self.filepath] == self.get_header_length():
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
            DownloadsRecorder.write('Downloaded %s -- %s', self.subject.name,
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

        if 'application/pdf' in self.content_type:
            self.set_resource_type('pdf')
            return self.save_response_content()

        if 'officedocument.wordprocessingml.document' in self.content_type:
            self.set_resource_type('word')
            return self.save_response_content()

        if 'officedocument.spreadsheetml.sheet' in self.content_type:
            self.set_resource_type('excel')
            return self.save_response_content()

        if 'officedocument.presentationml.slideshow' in self.content_type:
            self.set_resource_type('power-point')
            return self.save_response_content()

        if 'presentationml.presentation' in self.content_type:
            self.set_resource_type('power-point')
            return self.save_response_content()

        if 'powerpoint' in self.content_type:
            self.set_resource_type('power-point')
            return self.save_response_content()

        if 'msword' in self.content_type:
            self.set_resource_type('word')
            return self.save_response_content()

        if 'application/zip' in self.content_type:
            self.set_resource_type('zip')
            return self.save_response_content()

        if 'application/g-zip' in self.content_type:
            self.set_resource_type('gzip')
            return self.save_response_content()

        if 'application/x-7z-compressed' in self.content_type:
            self.set_resource_type('7zip')
            return self.save_response_content()

        if 'x-rar-compressed' in self.content_type:
            self.set_resource_type('rar')
            return self.save_response_content()

        if 'text/plain' in self.content_type:
            self.set_resource_type('plain')
            return self.save_response_content()

        if 'application/json' in self.content_type:
            self.set_resource_type('json')
            return self.save_response_content()

        if 'application/octet-stream' in self.content_type:
            self.set_resource_type('octect-stream')
            return self.save_response_content()

        if 'image/jpeg' in self.content_type:
            self.set_resource_type('jpeg')
            return self.save_response_content()

        if 'image/png' in self.content_type:
            self.set_resource_type('png')
            return self.save_response_content()

        if 'video/mp4' in self.content_type:
            self.set_resource_type('mp4')
            return self.save_response_content()

        if 'video/x-ms-wm' in self.content_type:
            self.set_resource_type('avi')
            return self.save_response_content()

        if 'text/html' in self.content_type:
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
            pass

        try:
            resource = self.soup.find('div', {'class': 'resourceworkaround'})
            resource = Resource(name, resource.a['href'], self.subject, self.downloader, self.queue)
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

    def make_folder(self):
        """Makes a subfolder to save the folder's links."""
        self.append_subfolder(self.name)
        self.create_subject_folder()
        self.create_subfolder()

    def download(self):
        """Downloads the folder."""
        self.logger.debug('Downloading folder %s', self.name)
        self.make_request()
        self.process_request_bs4()
        self.make_folder()

        containers = self.soup.findAll('span', {'class': 'fp-filename-icon'})

        for container in containers:
            try:
                url = container.a['href']
                resource = Resource(os.path.splitext(container.a.text)[0],
                                    url, self.subject, self.downloader, self.queue)
                resource.subfolders = self.subfolders

                self.logger.debug('Created resource from folder: %r, %s',
                                  resource.name, resource.url)
                self.queue.put(resource)

            except TypeError:
                continue


class Forum(BaseLink):
    """Representation of a Forum link."""

    BASE_DIR = 'foros'

    def download(self):
        """Downloads the resources found in the forum hierarchy."""
        self.logger.debug('Downloading forum %s', self.name)
        self.make_request()
        self.process_request_bs4()

        if len(self.subfolders) == 0 and Options.FORUMS_SUBFOLDERS:
            self.append_subfolder('foros')
        self.append_subfolder(self.name)

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
            images = self.soup.findAll('div', {'class': 'attachedimages'})

            for attachment in attachments:
                try:
                    # TODO PROBABLY FIXME, LIKE IMAGES
                    resource = Resource(os.path.splitext(attachment.text)[0], attachment.a['href'],
                                        self.subject, self.downloader, self.queue)
                    resource.subfolders = self.subfolders

                    self.logger.debug('Created resource from forum: %r, %s', resource.name,
                                      resource.url)
                    self.queue.put(resource)
                except TypeError:
                    pass

            for image_container in images:
                real_images = image_container.findAll('img')
                for image in real_images:
                    try:
                        url = image['href']
                    except KeyError:
                        url = image['src']

                    resource = Resource(
                        os.path.splitext(url.split('/')[-1])[0],
                        url, self.subject, self.downloader, self.queue)
                    resource.subfolders = self.subfolders

                    self.logger.debug('Created resource (image) from forum: %r, %s',
                                      resource.name, resource.url)
                    self.queue.put(resource)

        else:
            self.logger.critical('Unkown url for forum %r. Vars: %r', self.url, vars())
            raise RuntimeError(f'Unknown url for forum: {self.url}')


class Delivery(BaseLink):
    """Representation of a delivery link."""

    def make_subfolder(self):
        """Makes a subfolder to save the folder's links."""
        self.append_subfolder(self.name)
        self.create_subject_folder()
        self.create_subfolder()

    def download(self):
        """Downloads the resources found in the delivery."""
        self.logger.debug('Downloading delivery %s', self.name)
        self.make_request()
        self.process_request_bs4()
        self.make_subfolder()

        links = []
        containers = self.soup.findAll('a', {'target': '_blank'})

        for container in containers:
            resource = Resource(os.path.splitext(container.text)[0], container['href'],
                                self.subject, self.downloader, self.queue)
            resource.subfolders = self.subfolders

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
