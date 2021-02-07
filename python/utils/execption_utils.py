"""This Module provides static/class execptions helper methods.

Classes:
    ExceptionUtils
"""
import logging
import sys
import os

from typing import List

LOGGER = logging.getLogger("sppmon")

class ExceptionUtils:
    """Wrapper for static/class exception helper methods.

    Attributes:
        stored_errors - List with all error messages occured

    Methods:
        error_message - Prints and saves a error message without raising anything.
        exception_info - saves and debugs errors, printing a customized exception instead of the whole trace.

    """

    stored_errors: List[str] = []
    """List with all error messages occured"""

    @classmethod
    def error_message(cls, message: str):
        """Prints and saves a error message without raising anything.

        Arguments:
            message {str} -- message to be displayed and saved.
        """
        #LOGGER.info(message)
        LOGGER.error(message)
        cls.stored_errors.append(message)

    @classmethod
    def exception_info(cls, error: Exception, extra_message: str = None) -> None:
        """saves and debugs errors, printing a customized exception instead of the whole trace.

        Specify a extra message if you want to also print something instead of only logging the exception.

        Arguments:
            error {Exception} -- Any exception raised which was not on purpose

        Keyword Arguments:
            extra_message {str} -- Extra message to be saved and displayed (default: {None})
        """
        error_type, error_2, trace_back = sys.exc_info()
        if(trace_back):
            file_name = os.path.split(trace_back.tb_frame.f_code.co_filename)[1]
            line_number = trace_back.tb_lineno
        else:
            file_name = "unable to resolve traceback"
            line_number = -1

        if(error != error_2):
            LOGGER.error("two different error messages somehow, be aware some data migth be corrupt")

        cls.stored_errors.extend(error.args) # save error message

        LOGGER.error(f"Exception in FILE: {file_name}, Line: {line_number}, Exception: {error_type}")
        LOGGER.error(f"Exception Message: {error.args[0]}")
        if(error.args[1:]):
            LOGGER.error(f"Exception args: {error.args[1:]}")

        if(extra_message):
            #LOGGER.info(extra_message)
            LOGGER.error(extra_message)
            cls.stored_errors.append(extra_message)
