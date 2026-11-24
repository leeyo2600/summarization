"""Single entry point for the local HTML/Flask app."""
import sys
from portable_runtime import main, startup_message

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        startup_message('law_summary could not start: ' + str(error))
        raise SystemExit(1)
