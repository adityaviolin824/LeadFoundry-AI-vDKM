import sys
import traceback
from typing import Optional, Any

from utils.logger import logging

logger = logging.getLogger(__name__)


def error_message_details(error: Any, error_detail: Optional[object] = None) -> str:
    """
    Build a one-line error message containing filename, line number, and the error string.

    Backwards-compatible behavior:
      - If error_detail is None, we default to the sys module internally.
      - If a caller passes the sys module (legacy pattern), we still accept it.
    Logic:
      1. Prefer traceback attached to the exception (error.__traceback__).
      2. Fallback to error_detail.exc_info() if provided/available.
      3. Extract the last traceback frame and return:
         "Error occured in python script name [<file>] line number [<lineno>] error message[<error>]"
    """
    try:
        ed = error_detail if error_detail is not None else sys

        tb = getattr(error, "__traceback__", None)

        file_name = "<unknown>"
        line_no = -1

        if tb is not None:
            frames = traceback.extract_tb(tb)
            if frames:
                last = frames[-1]
                file_name = last.filename
                line_no = last.lineno
        else:
            try:
                _, _, exc_tb = ed.exc_info()
                if exc_tb is not None:
                    try:
                        file_name = exc_tb.tb_frame.f_code.co_filename
                    except Exception:
                        file_name = "<unknown>"

                    try:
                        line_no = exc_tb.tb_lineno
                    except Exception:
                        line_no = -1
            except Exception:
                pass

        error_message = (
            "Error occured in python script name [{0}] line number [{1}] error message[{2}]"
        ).format(file_name, line_no, str(error))

        return error_message

    except Exception as e:
        logger.exception("error_message_details failed while formatting error: %r", error)
        return f"Error occured but formatting failed: {str(error)} (formatter error: {e})"


class CustomException(Exception):
    """
    CustomException wraps an underlying error and produces a rich, single-line
    diagnostic message.

    Usage (recommended):
        raise CustomException(e)

    Legacy/backwards-compatible usage:
        raise CustomException(e, error_detail=sys)

    Implementation notes:
      - We capture the formatted message at construction time so the exception
        carries the same string you expect from previous code.
      - We do not swallow the original exception; prefer raising with chaining:
          raise CustomException(e) from e
        This preserves the original traceback in logs while still giving the
        concise error_message when str() is called on the exception instance.
    """

    def __init__(self, error_message: Any, error_detail: Optional[object] = None):
        self.original = error_message
        msg = error_message_details(error_message, error_detail=error_detail)
        super().__init__(str(msg))
        self.error_message = msg

    def __str__(self) -> str:
        return self.error_message
