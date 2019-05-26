"""Multithreading workers for the vcd."""

import logging

from ._requests import DownloaderError
from .links import BaseLink
from .subject import Subject

logger = logging.getLogger(__name__)


async def run(anything):
    """Runs the thread"""
    if isinstance(anything, BaseLink):
        logger.debug('Found Link %r, processing', anything.name)
        try:
            await anything.download()
        except FileNotFoundError as ex:
            logger.exception('FileNotFoundError in url %s (%r)', anything.url, ex)
        except DownloaderError as ex:
            logger.exception('DownloaderError in url %s (%r)', anything.url, ex)

        logger.info('Completed work of Link %r', anything.name)

    elif isinstance(anything, Subject):
        logger.debug('Found Subject %r, processing', anything.name)
        try:
            await anything.find_links()
        except DownloaderError as ex:
            logger.exception('DownloaderError in subject %s (%r)', anything.name, ex)

        logger.info('Completed work of Subject %r', anything.name)
    elif anything is None:
        logger.info('Closing thread, received None')
        return
