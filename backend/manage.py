#!/usr/bin/env python
import os
import sys

from app.debug_logger import debug_log

def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'app.settings')
    #region agent log H1_manage_start
    debug_log(
        hypothesisId="H1",
        runId="pre-diagnose",
        location="manage.py:main",
        message="Starting Django management command",
        data={"argv": sys.argv},
    )
    #endregion
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    try:
        execute_from_command_line(sys.argv)
    except Exception as exc:
        #region agent log H1_manage_exception
        debug_log(
            hypothesisId="H1",
            runId="pre-diagnose",
            location="manage.py:execute_from_command_line",
            message="execute_from_command_line failed",
            data={"exc_type": type(exc).__name__, "error": str(exc)[:500]},
        )
        #endregion
        raise

if __name__ == '__main__':
    main()