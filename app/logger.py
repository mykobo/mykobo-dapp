import curses
import logging
import logging.handlers
import sys

from flask import has_request_context, request
__all__ = ["get_stream_handler"]

from app.util import retrieve_ip_address


def _stderr_supports_color():
    try:
        if hasattr(sys.stderr, "isatty") and sys.stderr.isatty():
            if curses:
                curses.setupterm()
                if curses.tigetnum("colors") > 0:
                    return True
    except Exception:
        # Very broad exception handling because it's always better to
        # fall back to non-colored logs than to break at startup.
        pass
    return False


class LogFormatter(logging.Formatter):
    DEFAULT_FORMAT = "[%(asctime)s %(module)s:%(lineno)d] | [%(levelname)s] | [%(remote_addr)s] %(message)s"
    DEFAULT_DATE_FORMAT = "%B %d, %Y %H:%M:%S %Z"
    DEFAULT_COLORS = {
        logging.DEBUG: 4,  # Blue
        logging.INFO: 2,  # Green
        logging.WARNING: 3,  # Yellow
        logging.ERROR: 1,  # Red
    }

    def __init__(
        self,
        fmt=DEFAULT_FORMAT,
        datefmt=DEFAULT_DATE_FORMAT,
        style="%",
        color=True,
        colors=DEFAULT_COLORS,
    ):

        logging.Formatter.__init__(self, datefmt=datefmt)
        self._fmt = fmt

        self._colors = {}
        if color and _stderr_supports_color():
            if curses is not None:
                fg_color = curses.tigetstr("setaf") or curses.tigetstr("setf") or ""
                if (3, 0) < sys.version_info < (3, 2, 3):
                    fg_color = str(fg_color, "ascii")

                for levelno, code in colors.items():
                    self._colors[levelno] = str(curses.tparm(fg_color, code), "ascii")
                self._normal = str(curses.tigetstr("sgr0"), "ascii")
            else:
                # If curses is not present (currently we'll only get here for
                # colorama on windows), assume hard-coded ANSI color codes.
                for levelno, code in colors.items():
                    self._colors[levelno] = "\033[2;3%dm" % code
                self._normal = "\033[0m"
        else:
            self._normal = ""

    def format(self, record):
        try:
            record.message = record.getMessage()
        except Exception as e:
            record.message = "Bad message (%r): %r" % (e, record.__dict__)

        if has_request_context():
            record.url = request.url
            record.remote_addr = retrieve_ip_address(request)
        else:
            record.url = None
            record.remote_addr = None

        record.asctime = self.formatTime(record, self.datefmt)

        if record.levelno in self._colors:
            record.color = self._colors[record.levelno]
            record.end_color = self._normal
        else:
            record.color = record.end_color = ""

        formatted = self._fmt % record.__dict__

        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            lines = [formatted.rstrip()]
            lines.extend(ln for ln in record.exc_text.split("\n"))
            formatted = "\n".join(lines)

        return formatted.replace("\n", "\n    ")


def get_stream_handler():
    handler = logging.StreamHandler()
    handler.setFormatter(LogFormatter())
    return handler
